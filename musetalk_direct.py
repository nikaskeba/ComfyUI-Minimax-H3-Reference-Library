"""MuseTalk inference directly from ComfyUI image and audio tensors."""
import math
import sys
from pathlib import Path

import cv2
import numpy as np
import torch
from scipy.signal import resample_poly

import comfy.utils
from comfy_api.latest import io


def mono_audio(audio):
    waveform = audio["waveform"]
    if waveform.ndim != 3 or waveform.shape[0] != 1 or waveform.shape[-1] == 0:
        raise ValueError("MuseTalk expects one nonempty AUDIO clip shaped [1, channels, samples].")
    samples = waveform[0].detach().float().cpu().mean(dim=0).numpy()
    rate = int(audio["sample_rate"])
    if rate != 16000:
        divisor = math.gcd(rate, 16000)
        samples = resample_poly(samples, 16000 // divisor, rate // divisor)
    return np.ascontiguousarray(samples, dtype=np.float32)


class MuseTalkRunDirect(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="MuseTalkRunDirect", display_name="MuseTalk Run (Images + Audio)", category="MuseTalk",
                         inputs=[io.Image.Input("images"), io.Audio.Input("audio"),
                                 io.Float.Input("fps", default=25, min=1, max=240),
                                 io.Int.Input("bbox_shift", default=0, min=-1000, max=1000),
                                 io.Int.Input("batch_size", default=8, min=1, max=128)],
                         outputs=[io.Image.Output("images")])

    @classmethod
    def execute(cls, images, audio, fps=25, bbox_shift=0, batch_size=8):
        backend = Path(__file__).resolve().parent.parent / "ComfyUI-MuseTalk"
        if not (backend / "musetalk").is_dir():
            raise RuntimeError("Install ComfyUI-MuseTalk beside the Skeba nodes; it supplies the MuseTalk inference backend.")
        if str(backend) not in sys.path:
            sys.path.insert(0, str(backend))
        # MuseTalk's optional backends initialize models when imported.
        from musetalk.utils.utils import load_all_model
        from musetalk.utils.preprocessing import get_landmark_and_bbox_frames, coord_placeholder
        from musetalk.utils.blending import get_image

        samples = mono_audio(audio)
        if len(images) == 0:
            raise ValueError("MuseTalk needs at least one source image.")
        frames = [cv2.cvtColor(frame, cv2.COLOR_RGB2BGR) for frame in
                  (images[..., :3].detach().float().cpu().clamp(0, 1).numpy() * 255).round().astype(np.uint8)]
        coords, frames = get_landmark_and_bbox_frames(frames, bbox_shift)
        processor, vae, unet, pe = load_all_model()
        features = processor.audio2feat(samples)
        count = max(1, round(len(samples) * fps / 16000))
        # Use MuseTalk's feature slicing with an exact audio-derived frame count.
        chunks = [processor.get_sliced_feature(features, i, fps=fps)[0] for i in range(count)]
        latents = {}
        for i, (bbox, frame) in enumerate(zip(coords, frames)):
            if tuple(bbox) == coord_placeholder:
                continue
            x1, y1, x2, y2 = map(int, bbox)
            x1, x2 = max(0, x1), min(frame.shape[1], x2)
            y1, y2 = max(0, y1), min(frame.shape[0], y2)
            if x2 <= x1 or y2 <= y1:
                continue
            coords[i] = (x1, y1, x2, y2)
            crop = cv2.resize(frame[y1:y2, x1:x2], (256, 256), interpolation=cv2.INTER_LANCZOS4)
            latents[i] = vae.get_latents_for_unet(crop)
        if not latents:
            raise ValueError("MuseTalk could not detect a usable face in the source images.")
        cycle = list(range(len(frames))) + list(range(len(frames) - 1, -1, -1))
        indices = [cycle[i % len(cycle)] for i in range(count)]
        output = [None] * count
        pending = [i for i, source in enumerate(indices) if source in latents]
        timestep = torch.tensor([0], device=unet.device)
        progress = comfy.utils.ProgressBar(count)
        for i, source in enumerate(indices):
            if source not in latents:
                output[i] = torch.from_numpy(cv2.cvtColor(frames[source], cv2.COLOR_BGR2RGB)).float() / 255
                progress.update(1)
        for start in range(0, len(pending), batch_size):
            positions = pending[start:start + batch_size]
            batch = torch.cat([latents[indices[i]] for i in positions])
            conditioning = pe(torch.from_numpy(np.stack([chunks[i] for i in positions])).to(unet.device))
            prediction = unet.model(batch, timestep, encoder_hidden_states=conditioning).sample
            for position, face in zip(positions, vae.decode_latents(prediction)):
                source = indices[position]
                x1, y1, x2, y2 = coords[source]
                face = cv2.resize(face.astype(np.uint8), (x2 - x1, y2 - y1))
                composite = get_image(frames[source].copy(), face, coords[source])
                output[position] = torch.from_numpy(cv2.cvtColor(composite, cv2.COLOR_BGR2RGB)).float() / 255
                progress.update(1)
        return io.NodeOutput(torch.stack(output))

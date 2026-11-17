"""Direct IMAGE output for the installed RunningHub SoulX-FlashHead backend."""

from collections import deque
from pathlib import Path
import importlib
import sys
import tempfile

import numpy as np
import torch
from PIL import Image
import yaml


def _backend():
    for module in tuple(sys.modules.values()):
        module_path = getattr(module, "__file__", None)
        if (module_path and Path(module_path).name == "nodes.py"
                and Path(module_path).parent.name == "ComfyUI_RH_FlashHead"
                and hasattr(module, "run_pipeline")):
            return module
    try:
        module = importlib.import_module("ComfyUI_RH_FlashHead.nodes")
    except Exception as exc:
        raise RuntimeError(
            "SKEBA FlashHead Frames requires the installed ComfyUI_RH_FlashHead pack "
            "and its dependencies. Restart ComfyUI after installing it."
        ) from exc
    return module


def _frames_from_chunks(chunks):
    if not chunks:
        raise ValueError("FlashHead produced no frames. Provide enough audio for one generation chunk.")
    frames = torch.cat([chunk.detach().to(device="cpu", dtype=torch.float32) for chunk in chunks], dim=0)
    if frames.ndim != 4 or frames.shape[-1] != 3:
        raise ValueError(f"FlashHead returned unexpected frame shape {tuple(frames.shape)}; expected [N,H,W,3].")
    return (frames / 255.0).clamp(0.0, 1.0)


def _matching_audio(audio, frame_count, fps):
    waveform = audio["waveform"]
    sample_rate = int(audio["sample_rate"])
    if waveform.ndim != 3 or waveform.shape[0] != 1 or sample_rate <= 0:
        raise ValueError("FlashHead audio must be a single ComfyUI AUDIO batch with a valid sample rate.")
    samples = min(waveform.shape[-1], round(frame_count * sample_rate / fps))
    return {"waveform": waveform[..., :samples].clone(), "sample_rate": sample_rate}


class SkebaFlashHeadFrames:
    """Run the upstream FlashHead pipeline and return its frames before MP4 encoding."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "pipeline": ("RH_FlashHead_Pipeline",),
                "ref_audio": ("AUDIO",),
                "avatar_image": ("IMAGE",),
                "seed": ("INT", {"default": 42, "min": 0, "max": 0xffffffffffffffff}),
            },
            "optional": {
                "width": ("INT", {"default": 512, "min": 64, "max": 2048, "step": 8}),
                "height": ("INT", {"default": 512, "min": 64, "max": 2048, "step": 8}),
            },
        }

    RETURN_TYPES = ("IMAGE", "AUDIO", "FLOAT")
    RETURN_NAMES = ("frames", "audio", "fps")
    FUNCTION = "sample"
    CATEGORY = "Skeba AI Nodes/Avatar"

    def sample(self, pipeline, ref_audio, avatar_image, seed, width=512, height=512):
        backend = _backend()
        config_path = Path(backend.__file__).resolve().parent / "flash_head" / "configs" / "infer_params.yaml"
        with config_path.open("r", encoding="utf-8") as handle:
            params = yaml.safe_load(handle)

        waveform = ref_audio["waveform"]
        source_rate = int(ref_audio["sample_rate"])
        if waveform.ndim != 3 or waveform.shape[0] != 1 or waveform.shape[-1] == 0 or source_rate <= 0:
            raise ValueError("Connect a nonempty, single-batch AUDIO input to FlashHead.")
        if avatar_image.ndim != 4 or avatar_image.shape[0] < 1 or avatar_image.shape[-1] < 3:
            raise ValueError("Connect an IMAGE containing at least one RGB frame to FlashHead.")

        motion_frames = (params["motion_frames_latent_num"] - 1) * pipeline.config.vae_stride[0] + 1
        params["motion_frames_num"] = motion_frames
        params["width"], params["height"] = int(width), int(height)
        params["sample_steps"] = 20 if pipeline.model_type == "pretrained" else 4
        fps = int(params["tgt_fps"])
        sample_rate = int(params["sample_rate"])
        chunk_frames = int(params["frame_num"]) - motion_frames
        chunk_samples = chunk_frames * sample_rate // fps
        if chunk_frames <= 0 or chunk_samples <= 0:
            raise ValueError("FlashHead inference config has an invalid audio/video chunk length.")

        mono = waveform[0].detach().float().mean(dim=0).cpu().numpy()
        resampled = backend.librosa.resample(mono, orig_sr=source_rate, target_sr=sample_rate)
        chunk_count = len(resampled) // chunk_samples
        if chunk_count == 0:
            minimum = chunk_samples / sample_rate
            raise ValueError(f"FlashHead needs at least {minimum:.2f} seconds of audio for one chunk.")

        first_frame = (avatar_image[0, ..., :3].detach().float().cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            image_path = Path(tmp.name)
        try:
            Image.fromarray(first_frame, mode="RGB").save(image_path)
            pipeline.prepare_params(
                cond_image_path_or_dir=str(image_path),
                target_size=(params["height"], params["width"]),
                frame_num=params["frame_num"],
                motion_frames_num=motion_frames,
                sampling_steps=params["sample_steps"],
                seed=int(seed) ^ (2 ** 32),
                shift=params["sample_shift"],
                color_correction_strength=params["color_correction_strength"],
                use_face_crop=False,
            )

            cache_samples = sample_rate * int(params["cached_audio_duration"])
            audio_window = deque([0.0] * cache_samples, maxlen=cache_samples)
            audio_end = int(params["cached_audio_duration"]) * fps
            audio_start = audio_end - int(params["frame_num"])
            progress = backend.comfy.utils.ProgressBar(chunk_count)
            chunks = []
            for index in range(chunk_count):
                audio_window.extend(resampled[index * chunk_samples:(index + 1) * chunk_samples].tolist())
                embedding = backend.get_audio_embedding(
                    pipeline, np.asarray(audio_window), audio_start, audio_end, infer_params=params
                )
                chunks.append(backend.run_pipeline(pipeline, embedding))
                progress.update(1)
        finally:
            image_path.unlink(missing_ok=True)

        frames = _frames_from_chunks(chunks)
        return (frames, _matching_audio(ref_audio, frames.shape[0], fps), float(fps))

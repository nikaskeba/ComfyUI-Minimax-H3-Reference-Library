"""Read boundary media from the last completed clip, including its saved edits."""
import math

import torch


class SkebaH3LastRenderedContext:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "context_length": (["5", "22", "39", "56"], {"default": "22"}),
            "include_audio": ("BOOLEAN", {"default": True}),
            "bypass": ("BOOLEAN", {"default": False}),
        }, "optional": {
            "accumulation": ("ACCUMULATION", {"tooltip": "Connect the loop's incoming accumulation, before appending the current clip. Reads only the last completed clip."}),
            "video": ("VIDEO", {"tooltip": "Optional explicit previous video; takes priority over accumulation."}),
        }}

    RETURN_TYPES = ("IMAGE", "AUDIO", "BOOLEAN", "INT")
    RETURN_NAMES = ("context_frames", "context_audio", "bypass", "frame_count")
    FUNCTION = "load"
    CATEGORY = "Skeba AI Nodes - Motion Context"
    DESCRIPTION = "Extract the last rendered clip's tail at 24 fps for Motion Context or an AV Connector. Empty accumulation returns bypass=True. Does not load a latent cache."

    def load(self, context_length="22", include_audio=True, bypass=False, accumulation=None, video=None):
        if bypass:
            return (None, None, True, 0)
        if video is None:
            clips = (accumulation or {}).get("accum", [])
            video = clips[-1] if clips else None
        if video is None:
            return (None, None, True, 0)
        parts = video.get_components()
        frames = parts.images
        fps = float(parts.frame_rate)
        if not math.isfinite(fps) or fps <= 0:
            raise ValueError("Last Rendered Context: video frame rate must be positive.")
        duration = len(frames) / fps
        available = math.floor(duration * 24 + 1e-7)
        count = max((n for n in (5, 22, 39, 56) if n <= int(context_length) and n <= available), default=0)
        if not count:
            return (None, None, True, 0)
        start = duration - count / 24
        if fps == 24:
            tail = frames[-count:].clone()
        else:
            # Sample the same time interval at H3's 24 fps without resizing/cropping.
            indices = torch.floor((start + torch.arange(count, device=frames.device, dtype=torch.float64) / 24) * fps).long()
            tail = frames[indices.clamp(0, len(frames)-1)].clone()
        audio = None
        if include_audio and parts.audio is not None:
            source = parts.audio
            rate = int(source["sample_rate"])
            waveform = source["waveform"]
            begin = round(start * rate)
            end = round(duration * rate)
            if waveform.shape[-1] > begin:
                audio = {**source, "waveform": waveform[..., begin:end].clone()}
        return (tail, audio, False, count)

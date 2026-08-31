import math

import torch

from comfy_api.latest import InputImpl, Types


class CombineVideoClipsNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "accumulation": ("ACCUMULATION", {"forceInput": True}),
            }
        }

    RETURN_TYPES = ("VIDEO", "INT",)
    RETURN_NAMES = ("video", "clip_count",)
    FUNCTION = "combine"
    CATEGORY = "Skeba AI Nodes - Utilities"

    def combine(self, accumulation):
        videos = accumulation.get("accum", [])
        if not videos:
            raise ValueError("No video clips were accumulated.")

        components = [video.get_components() for video in videos]
        frame_rate = components[0].frame_rate
        bit_depth = videos[0].get_bit_depth()
        first_shape = components[0].images.shape[1:]

        for index, (video, clip) in enumerate(zip(videos, components), start=1):
            if clip.frame_rate != frame_rate:
                raise ValueError(f"Clip {index} has a different frame rate.")
            if clip.images.shape[1:] != first_shape:
                raise ValueError(f"Clip {index} has different image dimensions.")
            if video.get_bit_depth() != bit_depth:
                raise ValueError(f"Clip {index} has a different bit depth.")

        images = torch.cat([clip.images for clip in components], dim=0)
        audio = self._combine_audio(components, frame_rate)
        video = InputImpl.VideoFromComponents(
            Types.VideoComponents(images=images, audio=audio, frame_rate=frame_rate),
            bit_depth=bit_depth,
        )
        return (video, len(videos))

    @staticmethod
    def _combine_audio(components, frame_rate):
        if all(clip.audio is None for clip in components):
            return None
        if any(clip.audio is None for clip in components):
            raise ValueError("Every accumulated clip must either have audio or omit audio.")

        sample_rate = int(components[0].audio["sample_rate"])
        waveforms = []
        channel_shape = components[0].audio["waveform"].shape[:-1]

        for index, clip in enumerate(components, start=1):
            clip_sample_rate = int(clip.audio["sample_rate"])
            waveform = clip.audio["waveform"]
            if clip_sample_rate != sample_rate:
                raise ValueError(f"Clip {index} has a different audio sample rate.")
            if waveform.shape[:-1] != channel_shape:
                raise ValueError(f"Clip {index} has a different audio channel layout.")

            sample_count = math.ceil((sample_rate / frame_rate) * clip.images.shape[0])
            waveforms.append(waveform[..., :sample_count])

        return {
            "waveform": torch.cat(waveforms, dim=-1),
            "sample_rate": sample_rate,
        }



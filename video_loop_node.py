import math

import torch
import torchaudio

from comfy_api.latest import InputImpl, Types


class CombineVideoClipsNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "accumulation": ("ACCUMULATION", {"forceInput": True}),
            },
            "optional": {
                "starting_video": ("VIDEO", {"tooltip": "Video placed before the accumulated clips; resized to fit with black bars if needed."}),
                "ending_video": ("VIDEO", {"tooltip": "Video placed after the accumulated clips; resized to fit with black bars if needed."}),
            },
        }

    RETURN_TYPES = ("VIDEO", "INT",)
    RETURN_NAMES = ("video", "clip_count",)
    FUNCTION = "combine"
    CATEGORY = "Skeba AI Nodes - Utilities"

    def combine(self, accumulation, starting_video=None, ending_video=None):
        videos = list(accumulation.get("accum", []))
        target_index = int(starting_video is not None) if videos else 0
        if starting_video is not None:
            videos.insert(0, starting_video)
        if ending_video is not None:
            videos.append(ending_video)
        if not videos:
            raise ValueError("No video clips were accumulated.")

        components = [video.get_components() for video in videos]
        frame_rate = components[target_index].frame_rate
        bit_depth = videos[target_index].get_bit_depth()
        first_shape = components[target_index].images.shape[1:]
        bookend_indices = set()
        if starting_video is not None:
            bookend_indices.add(0)
        if ending_video is not None:
            bookend_indices.add(len(videos) - 1)
        for index in bookend_indices:
            clip = components[index]
            if clip.images.shape[1:3] != first_shape[:2]:
                height, width = first_shape[:2]
                source_h, source_w = clip.images.shape[1:3]
                scale = min(width / source_w, height / source_h)
                resized_w = max(1, min(width, round(source_w * scale)))
                resized_h = max(1, min(height, round(source_h * scale)))
                resized = torch.nn.functional.interpolate(
                    clip.images.movedim(-1, 1), size=(resized_h, resized_w),
                    mode="bilinear", align_corners=False, antialias=True)
                left = (width - resized_w) // 2
                top = (height - resized_h) // 2
                resized = torch.nn.functional.pad(resized, (
                    left, width - resized_w - left, top, height - resized_h - top))
                components[index] = Types.VideoComponents(
                    images=resized.movedim(1, -1), audio=clip.audio,
                    frame_rate=clip.frame_rate)

        for index, (video, clip) in enumerate(zip(videos, components), start=1):
            if clip.frame_rate != frame_rate:
                raise ValueError(f"Clip {index} has a different frame rate.")
            if clip.images.shape[1:] != first_shape:
                raise ValueError(f"Clip {index} has different image dimensions.")
            if video.get_bit_depth() != bit_depth:
                raise ValueError(f"Clip {index} has a different bit depth.")

        images = torch.cat([clip.images for clip in components], dim=0)
        accumulated_components = components[target_index:target_index + len(accumulation.get("accum", []))]
        reference_audio = next((clip.audio for clip in accumulated_components if clip.audio is not None), None)
        audio = self._combine_audio(components, frame_rate, reference_audio)
        video = InputImpl.VideoFromComponents(
            Types.VideoComponents(images=images, audio=audio, frame_rate=frame_rate),
            bit_depth=bit_depth,
        )
        return (video, len(videos))

    @staticmethod
    def _combine_audio(components, frame_rate, reference_audio=None):
        if all(clip.audio is None for clip in components):
            return None
        if reference_audio is None:
            reference_audio = next(clip.audio for clip in components if clip.audio is not None)
        reference_waveform = reference_audio["waveform"]
        sample_rate = int(reference_audio["sample_rate"])
        waveforms = []
        channel_shape = reference_waveform.shape[:-1]

        for index, clip in enumerate(components, start=1):
            sample_count = math.ceil((sample_rate / frame_rate) * clip.images.shape[0])
            if clip.audio is None:
                waveforms.append(reference_waveform.new_zeros((*channel_shape, sample_count)))
                continue
            clip_sample_rate = int(clip.audio["sample_rate"])
            waveform = clip.audio["waveform"]
            if clip_sample_rate != sample_rate:
                waveform = torchaudio.functional.resample(waveform, clip_sample_rate, sample_rate)
            if waveform.shape[:-1] != channel_shape:
                raise ValueError(f"Clip {index} has a different audio channel layout.")

            waveform = waveform[..., :sample_count]
            if waveform.shape[-1] < sample_count:
                padding = waveform.new_zeros((*channel_shape, sample_count - waveform.shape[-1]))
                waveform = torch.cat([waveform, padding], dim=-1)
            waveforms.append(waveform)

        return {
            "waveform": torch.cat(waveforms, dim=-1),
            "sample_rate": sample_rate,
        }



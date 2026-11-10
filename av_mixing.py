"""Per-prompt media windows and exact delivery lengths for AV mixing."""

import math
from pathlib import Path

import torch
import torch.nn.functional as F
import folder_paths
from comfy_api.latest import io

from .h3_inpaint_source_loop import (
    _AUDIO_EXTENSIONS, _VIDEO_EXTENSIONS, _decode_audio_window, _decode_window,
    _normalized_video_frame_count, _prompt_seconds, _video_size,
)


def media_files(extensions):
    root = Path(folder_paths.get_input_directory())
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*")
                  if p.is_file() and p.suffix.lower() in extensions)


def media_path(name, extensions):
    root = Path(folder_paths.get_input_directory()).resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root) or not path.is_file() or path.suffix.lower() not in extensions:
        raise ValueError("Select an existing media file inside ComfyUI/input.")
    return path


def mixing_window(prompts, current_prompt, default_duration, start_seconds, context_frames=0, settling_frames=0):
    items = [item.strip() for item in prompts.split("|") if item.strip()]
    index = current_prompt - 1
    if not 0 <= index < len(items):
        raise ValueError("Connect the loop's current prompt number and the same full prompt list to Mixing Source.")
    lengths = [max(1, round(_prompt_seconds(item, default_duration) * 24)) for item in items]
    count = lengths[index]
    head = context_frames + settling_frames
    cursor = round(start_seconds * 24) + sum(lengths[:index])
    return cursor - head, count, head, sum(lengths[:index])


class SkebaH3MixingSource(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="SkebaH3MixingSource", display_name="SKEBA H3 AV Mixing Source Window",
                         category="Skeba/Video", inputs=[
            io.Combo.Input("video", options=media_files(_VIDEO_EXTENSIONS) or ["Upload a video"]),
            io.Float.Input("start_seconds", default=0, min=0, max=1000000, step=1/24),
            io.Combo.Input("audio_source", options=["video audio", "custom audio"]),
            io.Combo.Input("custom_audio", options=["(none)"] + media_files(_AUDIO_EXTENSIONS)),
            io.Float.Input("custom_audio_start_seconds", default=0, min=0, max=1000000, step=1/24),
            io.String.Input("prompts", default="Prompt 1 | Prompt 2", multiline=True),
            io.Int.Input("current_prompt", default=1, min=1),
            io.Float.Input("default_duration", default=8, min=1/24, max=10000),
            io.Int.Input("render_frames", default=192, min=1),
            io.Int.Input("context_frames", default=0, min=0),
            io.Int.Input("settling_frames", default=0, min=0),
        ], outputs=[io.Image.Output("video"), io.Audio.Output("audio"),
                    io.Float.Output("render_seconds"), io.Int.Output("delivery_frames"),
                    io.String.Output("status"), io.Float.Output("edit_offset_seconds")])

    @classmethod
    def execute(cls, video, start_seconds, audio_source, custom_audio,
                custom_audio_start_seconds, prompts, current_prompt, default_duration, render_frames, context_frames=0, settling_frames=0):
        if not math.isfinite(start_seconds) or start_seconds < 0:
            raise ValueError("Video start must be a nonnegative number of seconds.")
        path = media_path(video, _VIDEO_EXTENSIONS)
        start, count, head, elapsed = mixing_window(prompts, current_prompt, default_duration, start_seconds, context_frames, settling_frames)
        stat = path.stat()
        total = _normalized_video_frame_count(str(path), stat.st_size, stat.st_mtime_ns)
        if start < 0 or start + head + count > total:
            raise ValueError(f"Prompt {current_prompt} exceeds the source video. Shorten the prompt duration/list or choose an earlier video start.")
        width, height = _video_size(str(path))
        available = min(render_frames, total - start)
        frames = _decode_window(str(path), start, available, width, height)
        if available < render_frames:
            frames = torch.cat((frames, frames[-1:].expand(render_frames - available, -1, -1, -1)))
        if audio_source == "video audio":
            audio = _decode_audio_window(str(path), start, render_frames)
        elif audio_source == "custom audio":
            audio_path = media_path(custom_audio, _AUDIO_EXTENSIONS)
            audio_start = round(custom_audio_start_seconds * 24) + elapsed - head
            # Context preceding the start of a custom track is silence.
            prefix = max(0, -audio_start)
            audio = _decode_audio_window(str(audio_path), max(0, audio_start), render_frames - prefix)
            if prefix:
                audio["waveform"] = F.pad(audio["waveform"], (round(render_frames * audio["sample_rate"] / 24) - audio["waveform"].shape[-1], 0))
        else:
            raise ValueError("Choose video audio or custom audio.")
        status = f"Prompt {current_prompt}: source {(start + head)/24:.3f}–{(start + head + count)/24:.3f}s; deliver {count} frames ({count/24:.3f}s)."
        return io.NodeOutput(frames, audio, render_frames / 24, count, status, head / 24)


class SkebaH3MixingTrim(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="SkebaH3MixingTrim", display_name="SKEBA H3 Exact Clip Length",
                         category="Skeba/Video", inputs=[io.Image.Input("images"), io.Audio.Input("audio"),
                         io.Int.Input("frame_count", default=192, min=1),
                         io.Float.Input("fps", default=24, min=.01)],
                         outputs=[io.Image.Output("images"), io.Audio.Output("audio")])

    @classmethod
    def execute(cls, images, audio, frame_count, fps=24):
        if len(images) < frame_count:
            raise ValueError(f"Decoded clip has {len(images)} frames; requested {frame_count}. Check generation length and continuation trim.")
        samples = round(frame_count * audio["sample_rate"] / fps)
        waveform = audio["waveform"][..., :samples].clone()
        if waveform.shape[-1] < samples:
            waveform = F.pad(waveform, (0, samples - waveform.shape[-1]))
        return io.NodeOutput(images[:frame_count].clone(), {**audio, "waveform": waveform})

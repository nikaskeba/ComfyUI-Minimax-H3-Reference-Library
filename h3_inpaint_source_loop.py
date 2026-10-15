"""Frame-accurate source windows for looping H3 video inpainting."""

from __future__ import annotations

import math
from pathlib import Path
import re
import subprocess

import torch


FPS = 24
H3_RUNS = (124, 107, 90, 73, 56, 39, 22, 5, 1)
_DURATION_TAG = re.compile(r"\[s\s*=\s*([^\]]+)\]", re.IGNORECASE)
_SCENE_TAG = re.compile(r"\[new_location\]", re.IGNORECASE)
_VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v"}
_AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".m4a", ".ogg", ".opus", ".aac", ".mp4", ".mkv"}


def _prompt_seconds(prompt: str, default_seconds: float) -> float:
    match = _DURATION_TAG.search(prompt)
    try:
        value = float(match.group(1).strip()) if match else float(default_seconds)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid [s=x] duration in prompt: {match.group(0) if match else default_seconds!r}.") from exc
    if not math.isfinite(value) or value <= 0:
        raise ValueError("Prompt duration must be a positive finite number of seconds.")
    return value


def _nearest_h3_length(required: int) -> int:
    lower = 5 + max(0, (required - 5) // 17) * 17
    upper = lower + 17
    return lower if required - lower < upper - required else upper


def plan_windows(
    prompt_batch: list[str], start_frame: int, default_seconds: float,
    context_length: int, settling_frames: int = 0,
    current_bypass: bool | None = None, current_index: int | None = None,
) -> list[dict]:
    if not isinstance(prompt_batch, list) or not prompt_batch:
        raise ValueError("Inpaint source loop needs a nonempty prompt batch.")
    if int(start_frame) < 0:
        raise ValueError("Starting frame must be zero or greater on the normalized 24 fps source.")
    context_length = int(context_length)
    settling_frames = int(settling_frames)
    if not 0 <= context_length <= 124 or settling_frames < 0:
        raise ValueError("Invalid H3 context or settling-frame setting.")
    settling = ((settling_frames + 16) // 17) * 17
    cursor = int(start_frame)
    previous_render = 0
    plans = []
    for index, prompt in enumerate(prompt_batch):
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError(f"Prompt {index + 1} is empty.")
        seconds = _prompt_seconds(prompt, default_seconds)
        requested_frames = max(5, round(seconds * FPS))
        bypass = index == 0 or bool(_SCENE_TAG.search(prompt))
        if index == current_index and current_bypass is not None and bool(current_bypass) != bypass:
            raise ValueError(
                f"Prompt {index + 1}: Motion Context bypass disagrees with the source-window plan. "
                "Use the same first-prompt/new-location control for both."
            )
        if bypass:
            overlap = 0
        else:
            available = min(context_length, previous_render)
            if available < 1:
                raise ValueError(f"Prompt {index + 1}: no previous video is available for continuation.")
            overlap = next(run for run in H3_RUNS if run <= available)
        head_trim = overlap + (settling if overlap else 0)
        render_frames = _nearest_h3_length(requested_frames + head_trim)
        if render_frames <= head_trim:
            render_frames += 17
        appended_frames = render_frames - head_trim
        source_start = cursor - head_trim
        if source_start < 0:
            raise ValueError(f"Prompt {index + 1}: source starts before frame zero.")
        plans.append({
            "prompt": index + 1,
            "requested_seconds": seconds,
            "requested_frames": requested_frames,
            "source_start_frame": source_start,
            "source_end_frame": source_start + render_frames,
            "delivered_start_frame": cursor,
            "delivered_end_frame": cursor + appended_frames,
            "render_frames": render_frames,
            "head_trim": head_trim,
            "appended_frames": appended_frames,
            "bypass": bypass,
        })
        cursor += appended_frames
        previous_render = render_frames
    return plans


class SkebaH3InpaintWindowPlan:
    CATEGORY = "Skeba AI Nodes - Reference/Experimental"
    FUNCTION = "plan"
    RETURN_TYPES = ("INT", "INT", "INT", "INT", "STRING", "INT")
    RETURN_NAMES = ("source_start_frame", "render_frames", "expected_head_trim", "appended_frames", "status", "video_origin_frame")
    DESCRIPTION = (
        "Plan the current prompt's frame window in one long source video. "
        "The starting frame is on a normalized 24 fps timeline. "
        "Designed for Motion Context video/head mode and an untrimmed 17k+5 H3 source."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "prompt_batch": ("SKEBA_PROMPT_LIST", {"forceInput": True}),
            "index": ("INT", {"forceInput": True}),
            "default_duration": ("FLOAT", {"default": 15.0, "min": 0.01, "max": 3600.0}),
            "start_frame": ("INT", {"default": 0, "min": 0, "max": 100000000}),
            "context_length": ("INT", {"default": 22, "min": 0, "max": 124}),
            "settling_frames": ("INT", {"default": 0, "min": 0, "max": 4096}),
            "bypass": ("BOOLEAN", {"default": False}),
        }}

    def plan(self, prompt_batch, index, default_duration=15.0, start_frame=0,
             context_length=22, settling_frames=0, bypass=False):
        index = int(index)
        if not 0 <= index < len(prompt_batch):
            raise ValueError(f"Inpaint source loop index {index} is outside {len(prompt_batch)} prompts.")
        item = plan_windows(prompt_batch, start_frame, default_duration,
                            context_length, settling_frames, bypass, index)[index]
        status = (
            f"Prompt {item['prompt']}: source frames {item['source_start_frame']}–"
            f"{item['source_end_frame'] - 1}; requested {item['requested_seconds']:g}s / "
            f"{item['requested_frames']} frames; H3 render {item['render_frames']} frames; "
            f"continuation trim {item['head_trim']}; append source frames "
            f"{item['delivered_start_frame']}–{item['delivered_end_frame'] - 1} "
            f"({item['appended_frames']} frames, {item['appended_frames'] / FPS:.3f}s)."
        )
        return (item["source_start_frame"], item["render_frames"],
                item["head_trim"], item["appended_frames"], status, int(start_frame))


def _source_files(extensions=_VIDEO_EXTENSIONS) -> list[str]:
    import folder_paths

    directory = Path(folder_paths.get_input_directory())
    return sorted(p.name for p in directory.iterdir()
                  if p.is_file() and p.suffix.lower() in extensions)


def _ffmpeg_executable() -> str:
    from imageio_ffmpeg import get_ffmpeg_exe

    return get_ffmpeg_exe()


def _video_size(path: str) -> tuple[int, int]:
    import cv2

    capture = cv2.VideoCapture(path)
    try:
        if not capture.isOpened():
            raise ValueError(f"Could not open source video: {Path(path).name}")
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    finally:
        capture.release()
    if width < 1 or height < 1:
        raise ValueError("Could not determine source-video dimensions.")
    return width, height


def _decode_window(path: str, start: int, count: int, width: int, height: int) -> torch.Tensor:
    frame_bytes = width * height * 3
    filter_graph = (
        f"fps=fps={FPS}:start_time=0,"
        f"trim=start_frame={start}:end_frame={start + count},setpts=PTS-STARTPTS"
    )
    cmd = [_ffmpeg_executable(), "-v", "error", "-i", path, "-vf", filter_graph,
           "-an", "-fps_mode", "passthrough", "-pix_fmt", "rgb24",
           "-f", "rawvideo", "pipe:1"]
    frames = torch.empty((count, height, width, 3), dtype=torch.float32)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    loaded = 0
    try:
        for i in range(count):
            chunks = bytearray()
            while len(chunks) < frame_bytes:
                piece = proc.stdout.read(frame_bytes - len(chunks))
                if not piece:
                    break
                chunks.extend(piece)
            if len(chunks) != frame_bytes:
                break
            frame = torch.frombuffer(chunks, dtype=torch.uint8).view(height, width, 3)
            frames[i].copy_(frame)
            loaded += 1
        if loaded != count:
            proc.terminate()
        _, error = proc.communicate()
        if loaded != count or proc.returncode:
            detail = error.decode("utf-8", "replace").strip()
            raise ValueError(
                f"Source video has only {loaded} of {count} required normalized 24 fps frames "
                f"from frame {start}. Shorten the prompt list or move the starting frame earlier. "
                + detail[-400:]
            )
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()
    return frames.div_(255.0)


def _decode_audio_window(path: str, start: int, count: int, sample_rate: int = 44100) -> dict:
    first = round(start * sample_rate / FPS)
    last = round((start + count) * sample_rate / FPS)
    cmd = [
        _ffmpeg_executable(), "-v", "error", "-i", path, "-vn",
        "-af", (f"aresample={sample_rate}:async=1:first_pts=0,"
                f"atrim=start_sample={first}:end_sample={last},asetpts=PTS-STARTPTS"),
        "-ac", "2", "-ar", str(sample_rate), "-f", "f32le", "pipe:1",
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode:
        raise ValueError(
            "Could not load source audio for this window: "
            + result.stderr.decode("utf-8", "replace")[-400:]
        )
    if not result.stdout:
        raise ValueError(
            f"Source audio is too short for frames {start}–{start + count - 1}. "
            "Choose an earlier starting frame or a longer audio file."
        )
    waveform = torch.frombuffer(bytearray(result.stdout), dtype=torch.float32)
    available = waveform.numel() // 2
    wanted = last - first
    if available < wanted - 2:
        raise ValueError(
            f"Source audio is too short for frames {start}–{start + count - 1}: "
            f"{available} of {wanted} samples per channel."
        )
    waveform = waveform[:2 * min(available, wanted)].reshape(-1, 2).T.unsqueeze(0).contiguous()
    if available < wanted:
        waveform = torch.nn.functional.pad(waveform, (0, wanted - available))
    return {"waveform": waveform, "sample_rate": sample_rate}


class SkebaH3InpaintSourceWindow:
    CATEGORY = "Skeba AI Nodes - Reference/Experimental"
    FUNCTION = "load"
    RETURN_TYPES = ("IMAGE", "AUDIO", "STRING", "IMAGE", "*", "*")
    RETURN_NAMES = ("frames", "audio", "status", "fixed_reference_frame", "audio_mask_mode", "video_generation_mode")
    DESCRIPTION = (
        "Read an exact frame window from an uploaded video after normalizing its "
        "whole timeline to 24 fps. Audio uses the same frame-indexed time window."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "video": (["(no source video)"] + _source_files(),),
            "start_frame": ("INT", {"default": 0, "min": 0, "max": 100000000}),
            "frame_count": ("INT", {"default": 124, "min": 5, "max": 100000}),
            "video_origin_frame": ("INT", {"default": 0, "min": 0, "max": 100000000}),
            "reference_frame": ("INT", {"default": 0, "min": 0, "max": 100000000}),
            "audio_source": (["video audio", "custom audio", "generate new audio"],),
            "custom_audio": (["(none)"] + _source_files(_AUDIO_EXTENSIONS),),
            "custom_audio_start_frame": ("INT", {"default": 0, "min": 0, "max": 100000000}),
            "video_generation_mode": (["source video inpaint", "audio drives video"],),
        }}

    @classmethod
    def IS_CHANGED(cls, video, start_frame, frame_count, video_origin_frame=0,
                   reference_frame=0, audio_source="video audio", custom_audio="(none)",
                   custom_audio_start_frame=0, video_generation_mode="source video inpaint"):
        import folder_paths

        if video == "(no source video)":
            video_stamp = (video,)
        else:
            path = Path(folder_paths.get_annotated_filepath(video))
            stat = path.stat()
            video_stamp = (video, stat.st_size, stat.st_mtime_ns)
        audio_stamp = None
        if audio_source == "custom audio" and custom_audio != "(none)":
            audio_stat = Path(folder_paths.get_annotated_filepath(custom_audio)).stat()
            audio_stamp = (custom_audio, audio_stat.st_size, audio_stat.st_mtime_ns)
        return (*video_stamp, int(start_frame),
                int(frame_count), int(video_origin_frame), int(reference_frame),
                audio_source, audio_stamp, int(custom_audio_start_frame),
                video_generation_mode)

    def load(self, video, start_frame, frame_count, video_origin_frame=0,
             reference_frame=0, audio_source="video audio", custom_audio="(none)",
             custom_audio_start_frame=0, video_generation_mode="source video inpaint"):
        import folder_paths

        no_video = video == "(no source video)"
        if no_video and (video_generation_mode != "audio drives video"
                         or audio_source == "video audio"):
            raise ValueError(
                "No source video is available only in audio-drives-video mode "
                "with custom audio or generate-new-audio selected."
            )
        if not no_video and (Path(video).name != video
                             or Path(video).suffix.lower() not in _VIDEO_EXTENSIONS):
            raise ValueError("Choose an uploaded video filename from the ComfyUI input folder.")
        input_dir = Path(folder_paths.get_input_directory()).resolve()
        if not no_video:
            path = Path(folder_paths.get_annotated_filepath(video)).resolve()
            if not path.is_file() or not path.is_relative_to(input_dir):
                raise ValueError("Source video must be an uploaded file inside the ComfyUI input folder.")
        start, count = int(start_frame), int(frame_count)
        if start < 0 or count < 5 or (count - 5) % 17:
            raise ValueError("Source window needs a nonnegative start and a valid 17k+5 H3 frame count.")
        if no_video:
            # Only the audio-trim path consumes these lightweight frames.
            # Source-video encoding, SAM3, and compositing are lazy in this mode.
            width = height = 64
            frames = torch.zeros((count, height, width, 3), dtype=torch.float32)
        else:
            width, height = _video_size(str(path))
            frames = _decode_window(str(path), start, count, width, height)
        ref_index = int(reference_frame)
        if ref_index < 0:
            raise ValueError("Reference frame must be zero or greater.")
        reference = (torch.zeros((1, height, width, 3), dtype=torch.float32)
                     if no_video else _decode_window(str(path), ref_index, 1, width, height))
        if audio_source == "video audio":
            audio = _decode_audio_window(str(path), start, count)
            audio_mode = "preserve source audio"
        elif audio_source == "custom audio":
            if custom_audio == "(none)" or Path(custom_audio).name != custom_audio \
                    or Path(custom_audio).suffix.lower() not in _AUDIO_EXTENSIONS:
                raise ValueError("Select an uploaded custom audio file in the ComfyUI input folder.")
            audio_path = Path(folder_paths.get_annotated_filepath(custom_audio)).resolve()
            if not audio_path.is_file() or not audio_path.is_relative_to(input_dir):
                raise ValueError("Custom audio must be inside the ComfyUI input folder.")
            audio_start = int(custom_audio_start_frame) + start - int(video_origin_frame)
            if audio_start < 0:
                raise ValueError(
                    "Custom audio starts before frame zero. Move its start slider later "
                    "or reduce the incoming continuation overlap."
                )
            audio = _decode_audio_window(str(audio_path), audio_start, count)
            audio_mode = "preserve source audio"
        elif audio_source == "generate new audio":
            samples = round(count * 44100 / FPS)
            audio = {"waveform": torch.zeros((1, 2, samples), dtype=torch.float32),
                     "sample_rate": 44100}
            audio_mode = "generate audio"
        else:
            raise ValueError(f"Unknown audio source: {audio_source}")
        if video_generation_mode not in ("source video inpaint", "audio drives video"):
            raise ValueError(f"Unknown video generation mode: {video_generation_mode}")
        audio_detail = (f"; custom audio frames {audio_start}–{audio_start + count - 1}"
                        if audio_source == "custom audio" else "")
        video_detail = ("no source video; text generates the picture"
                        if no_video else
                        f"{width}x{height}; fixed SAM3 reference frame {ref_index}")
        return (frames, audio,
                f"Loaded {video}: normalized 24 fps frames {start}–{start + count - 1} "
                f"({count / FPS:.3f}s); {video_detail}; {audio_source}{audio_detail}.",
                reference, audio_mode, video_generation_mode)


class SkebaH3InpaintWindowValidate:
    CATEGORY = "Skeba AI Nodes - Reference/Experimental"
    FUNCTION = "validate"
    RETURN_TYPES = ("IMAGE", "AUDIO", "STRING")
    RETURN_NAMES = ("frames", "audio", "status")
    DESCRIPTION = (
        "Check that Motion Context removed the planned head and the saved clip "
        "contains exactly the frame count used to advance the source cursor."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "frames": ("IMAGE",),
            "audio": ("AUDIO",),
            "actual_head_trim": ("INT",),
            "expected_head_trim": ("INT",),
            "expected_appended_frames": ("INT",),
        }}

    def validate(self, frames, audio, actual_head_trim, expected_head_trim,
                 expected_appended_frames):
        actual = int(actual_head_trim)
        planned = int(expected_head_trim)
        count = int(expected_appended_frames)
        if actual != planned:
            raise ValueError(
                f"Inpaint source cursor expected {planned} continuation frames to be trimmed, "
                f"but Motion Context returned {actual}. Check its head/context/settling settings."
            )
        if int(frames.shape[0]) != count:
            raise ValueError(
                f"Inpaint source cursor expected {count} saved frames, "
                f"but the trim produced {int(frames.shape[0])}. "
                "Check the source window and H3 frame grid."
            )
        if audio is None:
            return (frames, None, f"Validated {count} frames; no audio connected.")
        waveform = audio["waveform"]
        rate = int(audio["sample_rate"])
        wanted = round(count * rate / FPS)
        have = int(waveform.shape[-1])
        if have < wanted:
            # H3's audio grid may round a frame boundary by less than one
            # latent step. Permit only that small rounding difference.
            missing = wanted - have
            if missing > round(rate / 40):
                raise ValueError(
                    f"Inpaint audio is {missing / rate:.3f}s shorter than {count} video frames."
                )
            waveform = torch.nn.functional.pad(waveform, (0, missing),
                                               mode="replicate")
        else:
            waveform = waveform[..., :wanted]
        out_audio = dict(audio)
        out_audio["waveform"] = waveform
        return (frames, out_audio,
                f"Validated {count} appended frames ({count / FPS:.3f}s) "
                f"and {wanted} synchronized audio samples at {rate} Hz.")

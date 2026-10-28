"""Frame-accurate source windows for looping H3 video inpainting."""

from __future__ import annotations

import math
import functools
from pathlib import Path
import re
import subprocess

import torch


FPS = 24
H3_RUNS = (124, 107, 90, 73, 56, 39, 22, 5, 1)
_DURATION_TAG = re.compile(r"\[s\s*=\s*([^\]]+)\]", re.IGNORECASE)
_SCENE_TAG = re.compile(r"\[new_location\]", re.IGNORECASE)
_SHOT_TAG = re.compile(r"(?m)^[ \t]*\[Shot\s+\d+(?:\s*:\s*[^\]]+)?\]", re.IGNORECASE)
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


def _fit_duration_tag(prompt: str, frames: int) -> str:
    seconds = f"{frames / FPS:.6f}".rstrip("0").rstrip(".")
    replacement = f"[s={seconds}]"
    if _DURATION_TAG.search(prompt):
        prompt = _DURATION_TAG.sub(replacement, prompt, count=1)
    else:
        prompt = replacement + "\n" + prompt
    # Remove only shots whose explicit start is outside the shortened clip.
    # Unknown/untimed shots remain authored text; never guess their position.
    for shot in _SHOT_TAG.finditer(prompt):
        marker = shot.group(0)
        seconds = None
        inline = re.search(r":\s*(\d+(?:\.\d+)?)s\s*\]", marker, re.IGNORECASE)
        if inline:
            seconds = float(inline.group(1))
        else:
            line = prompt[shot.end():prompt.find("\n", shot.end()) if "\n" in prompt[shot.end():] else len(prompt)]
            clock = re.search(r"\bAt\s+(?:(\d+):)?(\d{2})\.(\d{1,3})\b", line, re.IGNORECASE)
            if clock:
                seconds = (int(clock.group(1) or 0) * 60 + int(clock.group(2))
                           + int(clock.group(3).ljust(3, "0")) / 1000)
        if seconds is not None and seconds >= frames / FPS:
            tail = re.search(r"(?m)^[ \t]*(?:overall_soundscape|non_diegetic_music)\s*:",
                             prompt[shot.start():], re.IGNORECASE)
            end = shot.start() + tail.start() if tail else len(prompt)
            return prompt[:shot.start()].rstrip() + "\n\n" + prompt[end:].lstrip()
    return prompt


def fit_prompt_batch(prompt_batch: list[str], total_frames: int, start_frame: int,
                     default_seconds: float, context_length: int,
                     settling_frames: int = 0) -> tuple[list[str], list[dict]]:
    """Keep only prompts that can consume real source frames on H3's grid."""
    if total_frames <= start_frame:
        raise ValueError("No source-video frames remain after the selected starting frame.")
    fitted = []
    plans = []
    for prompt in prompt_batch:
        candidate = plan_windows(fitted + [prompt], start_frame, default_seconds,
                                 context_length, settling_frames)[-1]
        available = total_frames - candidate["source_start_frame"]
        if available < candidate["render_frames"]:
            maximum = 5 + ((available - 5) // 17) * 17 if available >= 5 else 0
            if maximum <= candidate["head_trim"]:
                break
            prompt = _fit_duration_tag(prompt, maximum - candidate["head_trim"])
            candidate = plan_windows(fitted + [prompt], start_frame, default_seconds,
                                     context_length, settling_frames)[-1]
            if candidate["render_frames"] > available:
                raise ValueError("Could not fit the final prompt to the remaining source-video frames.")
        fitted.append(prompt)
        plans.append(candidate)
    if not fitted:
        raise ValueError(
            "Fewer than five usable H3 source frames remain at this starting frame. "
            "Move the start earlier or choose a longer video."
        )
    return fitted, plans


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


@functools.lru_cache(maxsize=16)
def _normalized_video_frame_count(path: str, size: int, mtime_ns: int) -> int:
    """Count the same 24 fps frames that _decode_window will address."""
    del size, mtime_ns
    cmd = [_ffmpeg_executable(), "-v", "error", "-i", path,
           "-vf", f"fps=fps={FPS}:start_time=0", "-an", "-f", "null", "-",
           "-progress", "pipe:1", "-nostats"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode:
        raise ValueError("Could not count normalized source-video frames: "
                         + result.stderr.strip()[-400:])
    counts = re.findall(r"(?m)^frame=(\d+)\s*$", result.stdout)
    if not counts:
        raise ValueError("Source video contains no decodable 24 fps frames.")
    return int(counts[-1])


class SkebaH3InpaintBatchFit:
    CATEGORY = "Skeba AI Nodes - Reference/Experimental"
    FUNCTION = "fit"
    RETURN_TYPES = ("SKEBA_PROMPT_LIST", "INT", "*", "INT", "STRING")
    RETURN_NAMES = ("prompt_batch", "count", "video", "start_frame", "status")
    DESCRIPTION = (
        "Before the loop, fit prompts to the real normalized 24 fps source. "
        "Shortens the final prompt on H3's frame grid and omits prompts after "
        "the video ends. Select the source video and starting frame here."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "prompt_batch": ("SKEBA_PROMPT_LIST", {"forceInput": True}),
            "video": (["(no source video)"] + _source_files(),),
            "start_frame": ("INT", {"default": 0, "min": 0, "max": 100000000}),
            "default_duration": ("FLOAT", {"default": 15.0, "min": 0.01, "max": 3600.0}),
            "context_length": ("INT", {"default": 22, "min": 0, "max": 124}),
            "settling_frames": ("INT", {"default": 0, "min": 0, "max": 4096}),
        }}

    @classmethod
    def IS_CHANGED(cls, prompt_batch, video, start_frame, default_duration,
                   context_length, settling_frames):
        if video == "(no source video)":
            return (tuple(prompt_batch), video, start_frame, default_duration,
                    context_length, settling_frames)
        import folder_paths
        stat = Path(folder_paths.get_annotated_filepath(video)).stat()
        return (tuple(prompt_batch), video, stat.st_size, stat.st_mtime_ns, start_frame,
                default_duration, context_length, settling_frames)

    def fit(self, prompt_batch, video, start_frame=0, default_duration=15.0,
            context_length=22, settling_frames=0):
        if not isinstance(prompt_batch, list) or not prompt_batch:
            raise ValueError("Inpaint source loop needs a nonempty prompt batch.")
        if video == "(no source video)":
            plan_windows(prompt_batch, start_frame, default_duration,
                         context_length, settling_frames)
            return (prompt_batch, len(prompt_batch), video, int(start_frame),
                    "No source video selected; prompt durations are unchanged.")
        import folder_paths
        if Path(video).name != video or Path(video).suffix.lower() not in _VIDEO_EXTENSIONS:
            raise ValueError("Choose an uploaded source video from the ComfyUI input folder.")
        input_dir = Path(folder_paths.get_input_directory()).resolve()
        path = Path(folder_paths.get_annotated_filepath(video)).resolve()
        if not path.is_file() or not path.is_relative_to(input_dir):
            raise ValueError("Source video must be inside the ComfyUI input folder.")
        stat = path.stat()
        total = _normalized_video_frame_count(str(path), stat.st_size, stat.st_mtime_ns)
        fitted, plans = fit_prompt_batch(prompt_batch, total, int(start_frame),
                                         default_duration, context_length, settling_frames)
        omitted = len(prompt_batch) - len(fitted)
        adjusted = fitted[-1] != prompt_batch[len(fitted) - 1]
        status = (f"{total} normalized 24 fps source frames; {len(fitted)} of "
                  f"{len(prompt_batch)} prompts fit. "
                  f"Last clip appends {plans[-1]['appended_frames']} frames "
                  f"({plans[-1]['appended_frames'] / FPS:.3f}s).")
        if adjusted:
            status += " Final prompt duration shortened to the remaining H3 frame grid."
        if omitted:
            status += f" {omitted} prompt(s) beyond the source end omitted."
        return (fitted, len(fitted), video, int(start_frame), status)


class SkebaH3InpaintVideoChoice:
    """One uploaded-video selection shared by Batch Fit and Source Window."""

    CATEGORY = "Skeba AI Nodes - Reference/Experimental"
    FUNCTION = "choose"
    RETURN_TYPES = ("*",)
    RETURN_NAMES = ("video",)
    DESCRIPTION = "Select one uploaded video for both source-window loading and loop fitting."

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"video": (["(no source video)"] + _source_files(),)}}

    @classmethod
    def IS_CHANGED(cls, video):
        if video == "(no source video)":
            return video
        import folder_paths
        stat = Path(folder_paths.get_annotated_filepath(video)).stat()
        return video, stat.st_size, stat.st_mtime_ns

    def choose(self, video):
        if video != "(no source video)":
            import folder_paths
            if Path(video).name != video or Path(video).suffix.lower() not in _VIDEO_EXTENSIONS:
                raise ValueError("Choose an uploaded source video from ComfyUI's input folder.")
            path = Path(folder_paths.get_annotated_filepath(video)).resolve()
            if not path.is_file() or not path.is_relative_to(Path(folder_paths.get_input_directory()).resolve()):
                raise ValueError("Source video must be inside ComfyUI's input folder.")
        return (video,)


class SkebaH3InpaintStartFrame:
    """Expose the loop's initial source frame outside nested subgraphs."""

    CATEGORY = "Skeba AI Nodes - Reference/Experimental"
    FUNCTION = "select"
    RETURN_TYPES = ("INT",)
    RETURN_NAMES = ("start_frame",)
    DESCRIPTION = "First source-video frame on the normalized 24 fps timeline."

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"start_frame": ("INT", {
            "default": 0, "min": 0, "max": 100000000,
        })}}

    def select(self, start_frame):
        return (int(start_frame),)


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
    waveform = (torch.frombuffer(bytearray(result.stdout), dtype=torch.float32)
                if result.stdout else torch.empty(0, dtype=torch.float32))
    available = waveform.numel() // 2
    wanted = last - first
    waveform = waveform[:2 * min(available, wanted)].reshape(-1, 2).T.unsqueeze(0).contiguous()
    if available < wanted:
        waveform = torch.nn.functional.pad(waveform, (0, wanted - available))
    return {"waveform": waveform, "sample_rate": sample_rate,
            "padded_silence_seconds": max(0, wanted - available) / sample_rate}


class SkebaH3InpaintSourceWindow:
    CATEGORY = "Skeba AI Nodes - Reference/Experimental"
    FUNCTION = "load"
    RETURN_TYPES = ("IMAGE", "AUDIO", "STRING", "IMAGE", "*", "*")
    RETURN_NAMES = ("frames", "audio", "status", "fixed_reference_frame", "audio_mask_mode", "video_generation_mode")
    DESCRIPTION = (
        "Loads the current prompt's source-video window on a normalized 24 fps timeline. "
        "Use Video start to choose where the loop begins, and Reference frame to choose "
        "one fixed image for subject tracking. Audio may come from the video, a separate "
        "track, or generation. Short source audio is padded with silence. The window "
        "planner normally supplies start_frame and frame_count for each prompt."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "video": (["(no source video)"] + _source_files(), {"tooltip": "Video to inpaint or use as source context. Select (no source video) only for audio-driven video generation."}),
            "start_frame": ("INT", {"default": 0, "min": 0, "max": 100000000, "tooltip": "First source frame on the normalized 24 fps timeline. In a loop, connect the window planner; change the initial position on Batch Fit."}),
            "frame_count": ("INT", {"default": 124, "min": 5, "max": 100000, "tooltip": "Number of source frames to load for this prompt, including continuation overlap. Connect the window planner for automatic H3 lengths."}),
            "video_origin_frame": ("INT", {"default": 0, "min": 0, "max": 100000000, "tooltip": "Original loop start frame. Keeps separately selected audio aligned as subsequent video windows advance."}),
            "reference_frame": ("INT", {"default": 0, "min": 0, "max": 100000000, "tooltip": "One fixed frame from the source video used as the subject-tracking reference throughout the loop. It does not set the clip start."}),
            "audio_source": (["video audio", "custom audio", "generate new audio"], {"tooltip": "Video audio follows the source video; custom audio follows its own start position; generate new audio leaves the incoming audio blank for H3."}),
            "custom_audio": (["(none)"] + _source_files(_AUDIO_EXTENSIONS), {"tooltip": "Separate audio file used only when Audio source is custom audio. Missing audio at the end is filled with silence."}),
            "custom_audio_start_frame": ("INT", {"default": 0, "min": 0, "max": 100000000, "tooltip": "Where custom audio begins, measured in 24 fps frame units. It advances with the video loop, so 24 means one second into the track."}),
            "video_generation_mode": (["source video inpaint", "audio drives video", "controlnet only", "inpaint only", "controlnet and inpainting"], {"tooltip": "Audio drives video: prompt and audio only. ControlNet only: prompt plus source-video structural guidance. Inpaint only: edit the tracked source region. ControlNet and inpainting: use both source guidance and tracked-region editing. The legacy source video inpaint choice behaves like both."}),
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
        if video_generation_mode not in ("source video inpaint", "audio drives video",
                                         "controlnet only", "inpaint only", "controlnet and inpainting"):
            raise ValueError(f"Unknown video generation mode: {video_generation_mode}")
        audio_detail = (f"; custom audio frames {audio_start}–{audio_start + count - 1}"
                        if audio_source == "custom audio" else "")
        if audio.get("padded_silence_seconds", 0):
            audio_detail += (f"; padded {audio['padded_silence_seconds']:.3f}s "
                             "of missing source audio with silence")
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

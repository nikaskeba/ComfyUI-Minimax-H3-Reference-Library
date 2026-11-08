"""Seconds-based planning and RTX timing for VHS's streaming batch loop."""

import math
from pathlib import Path

import cv2
import folder_paths
import torch


class SkebaVideoChunkPlan:
    @classmethod
    def INPUT_TYPES(cls):
        root = Path(folder_paths.get_input_directory())
        videos = sorted(p.relative_to(root).as_posix() for p in root.rglob("*")
                        if p.is_file() and p.suffix.lower() in {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v"})
        return {"required": {
            "video": (videos or ["Place a video in ComfyUI/input"],),
            "chunk_seconds": ("FLOAT", {"default": 30.0, "min": 0.01, "step": 1.0,
                                        "tooltip": "Chunk duration, rounded to the nearest whole source frame. Lower this if a chunk runs out of memory."}),
        }}

    RETURN_TYPES = ("STRING", "INT", "FLOAT", "STRING")
    RETURN_NAMES = ("video_path", "frames_per_batch", "fps", "report")
    FUNCTION = "plan"
    CATEGORY = "Skeba/Video"

    def plan(self, video, chunk_seconds):
        root = Path(folder_paths.get_input_directory()).resolve()
        path = (root / video).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("Select a video inside ComfyUI/input.")
        capture = cv2.VideoCapture(str(path))
        try:
            fps = capture.get(cv2.CAP_PROP_FPS)
            total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        finally:
            capture.release()
        if not math.isfinite(fps) or fps <= 0:
            raise ValueError(f"Cannot read the frame rate of {video}.")
        if not math.isfinite(chunk_seconds) or chunk_seconds <= 0:
            raise ValueError("chunk_seconds must be positive.")
        frames = max(1, round(chunk_seconds * fps))
        batches = math.ceil(total / frames)
        report = f"{total} frames at {fps:g} fps; {frames} frames ({frames / fps:.6f}s) per chunk; approximately {batches} chunks. Audio is muxed once at the end."
        return str(path), frames, fps, report


class SkebaRTXChunkTiming:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "images": ("IMAGE",),
            "source_frame_count": ("INT", {"forceInput": True, "min": 1}),
            "multiplier": ("INT", {"default": 2, "min": 1}),
        }}

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "complete"
    CATEGORY = "Skeba/Video"
    DESCRIPTION = "Hold the last RTX-generated frame for the remaining fraction of its source-frame duration, preventing audio drift across chunks."

    def complete(self, images, source_frame_count, multiplier):
        expected = (source_frame_count - 1) * multiplier + 1
        if source_frame_count < 1 or multiplier < 1 or images.shape[0] != expected:
            raise ValueError("Connect RTX multiplier-mode output and the matching source frame count/multiplier to Chunk Timing.")
        if multiplier == 1:
            return (images,)
        return (torch.cat((images, images[-1:].expand(multiplier - 1, -1, -1, -1)), dim=0),)

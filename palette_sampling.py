"""Frame previews and original-pixel sampling, independent of quantization."""
import math
import re
import uuid
from pathlib import Path

import folder_paths
import numpy as np
from PIL import Image


SAMPLING_MODES = {"Exact Pixel": 0, "3x3 Average": 1, "5x5 Average": 2}


def preview_directory():
    return Path(folder_paths.get_temp_directory()) / "skeba_palette"


def sample_frame(frame, u, v, sampling_mode):
    if sampling_mode not in SAMPLING_MODES:
        raise ValueError("Unknown palette sampling mode.")
    u, v = float(u), float(v)
    if not math.isfinite(u) or not math.isfinite(v):
        raise ValueError("Sample coordinates must be finite.")
    height, width = frame.shape[:2]
    x = int(math.floor(max(0.0, min(1.0, u)) * (width - 1) + 0.5))
    y = int(math.floor(max(0.0, min(1.0, v)) * (height - 1) + 0.5))
    radius = SAMPLING_MODES[sampling_mode]
    region = frame[max(0, y-radius):min(height, y+radius+1),
                   max(0, x-radius):min(width, x+radius+1), :3]
    mean = np.asarray(region, dtype=np.float64).mean(axis=(0, 1))
    if not np.isfinite(mean).all():
        raise ValueError("Selected pixels contain non-finite color values.")
    rgb = np.floor(np.clip(mean, 0, 1) * 255 + 0.5).astype(np.uint8).tolist()
    return {"x": x, "y": y, "rgb": rgb, "hex": "#" + "".join(f"{c:02X}" for c in rgb)}


def sample_preview(token, u, v, sampling_mode):
    if not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{32}", token):
        raise ValueError("Invalid palette preview token.")
    frame = np.load(preview_directory() / f"{token}.npy", mmap_mode="r", allow_pickle=False)
    try:
        return sample_frame(frame, u, v, sampling_mode)
    finally:
        del frame


class PaletteFramePreview:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"image": ("IMAGE",), "preview_frame": ("INT", {"default": 0, "min": 0})}}

    RETURN_TYPES = ()
    FUNCTION = "preview"
    OUTPUT_NODE = True
    CATEGORY = "Skeba AI Nodes - Utilities"
    DESCRIPTION = "Capture a source frame for the Fixed Palette Quantize eyedropper."

    def preview(self, image, preview_frame=0):
        if image.ndim != 4 or image.shape[-1] not in (3, 4) or min(image.shape[:3]) < 1:
            raise ValueError("Preview requires a non-empty RGB or RGBA IMAGE batch.")
        index = max(0, min(image.shape[0] - 1, int(preview_frame)))
        frame = image[index, ..., :3].detach().to(device="cpu").float().numpy()
        token = uuid.uuid4().hex
        directory = preview_directory()
        directory.mkdir(parents=True, exist_ok=True)
        # Store only the selected frame, never the video batch or a resident GPU tensor.
        np.save(directory / f"{token}.npy", frame, allow_pickle=False)
        pixels = np.floor(np.clip(frame, 0, 1) * 255 + 0.5).astype(np.uint8)
        preview = Image.fromarray(pixels)
        preview.thumbnail((1280, 960))
        preview.save(directory / f"{token}.png")
        return {"ui": {"palette_preview": [{
            "token": token, "filename": f"{token}.png", "subfolder": "skeba_palette", "type": "temp",
            "frame": index, "frames": image.shape[0], "width": frame.shape[1], "height": frame.shape[0],
        }]}}

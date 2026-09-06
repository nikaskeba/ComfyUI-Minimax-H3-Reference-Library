import logging
import math

import torch
from safetensors.torch import load_file

from .h3_last_frame_store import _frame_path


_LOG = logging.getLogger("skeba_h3_last_frame_exposure")
_BLACK_FLOOR = 1e-4


def _mean_luminance(images):
    rgb = images[..., :3].float()
    luminance = (rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 +
                 rgb[..., 2] * 0.0722)
    return float(luminance.mean().item())


class SkebaH3LastFrameExposureMatch:
    """Match a continuation's opening exposure to its stored guide frame."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "previous_clip_index": ("INT", {
                    "default": 1, "min": 0, "max": 9999,
                    "tooltip": "Clip slot containing the stored last-frame guide.",
                }),
                "bypass": ("BOOLEAN", {
                    "default": True,
                    "label_on": "BYPASS / NEW SCENE",
                    "label_off": "MATCH LAST FRAME",
                    "tooltip": "Bypass on the first clip and whenever motion context resets.",
                }),
                "strength": ("FLOAT", {
                    "default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05,
                }),
                "fade_frames": ("INT", {
                    "default": 12, "min": 1, "max": 240,
                    "tooltip": "Fade the exposure correction back to neutral.",
                }),
                "max_adjust_ev": ("FLOAT", {
                    "default": 0.125, "min": 0.0, "max": 1.0, "step": 0.025,
                    "tooltip": "Maximum brightening or darkening in exposure stops.",
                }),
                "filename_prefix": ("STRING", {
                    "default": "h3_context_frame/clip",
                }),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("images",)
    FUNCTION = "match"
    CATEGORY = "Skeba AI Nodes - Motion Context"
    DESCRIPTION = (
        "Match the first frame of a continuation directly to the losslessly "
        "stored final frame used by its H3 guide, then fade to neutral."
    )

    @classmethod
    def IS_CHANGED(cls, images, previous_clip_index=1, bypass=True,
                   strength=1.0, fade_frames=12, max_adjust_ev=0.125,
                   filename_prefix="h3_context_frame/clip"):
        if bypass or float(strength) <= 0.0:
            return "bypassed"
        path = _frame_path(filename_prefix, previous_clip_index)
        try:
            stat = path.stat()
            return f"{path}:{stat.st_mtime_ns}:{stat.st_size}"
        except OSError:
            return f"missing:{path}"

    def match(self, images, previous_clip_index=1, bypass=True, strength=1.0,
              fade_frames=12, max_adjust_ev=0.125,
              filename_prefix="h3_context_frame/clip"):
        if bypass or float(strength) <= 0.0:
            return (images,)
        if getattr(images, "ndim", 0) != 4 or int(images.shape[0]) < 1:
            raise ValueError("h3_last_frame_exposure: expected a non-empty IMAGE batch")
        if int(images.shape[-1]) < 3:
            raise ValueError("h3_last_frame_exposure: expected RGB images")
        if int(previous_clip_index) < 1:
            raise ValueError(
                "h3_last_frame_exposure: previous_clip_index must be at least 1"
            )

        path = _frame_path(filename_prefix, previous_clip_index)
        if not path.is_file():
            raise FileNotFoundError(
                f"h3_last_frame_exposure: stored guide frame is missing: {path}"
            )
        reference = load_file(str(path), device="cpu").get("image")
        if (reference is None or getattr(reference, "ndim", 0) != 4 or
                int(reference.shape[0]) < 1 or int(reference.shape[-1]) < 3):
            raise ValueError(f"h3_last_frame_exposure: invalid stored frame: {path}")

        reference_luminance = _mean_luminance(reference[-1:])
        opening_luminance = _mean_luminance(images[:1])
        if (reference_luminance <= _BLACK_FLOOR or
                opening_luminance <= _BLACK_FLOOR):
            return (images,)

        raw_ev = math.log2(reference_luminance / opening_luminance)
        limit = max(0.0, float(max_adjust_ev))
        applied_ev = max(-limit, min(limit, raw_ev)) * float(strength)
        if applied_ev == 0.0:
            return (images,)

        fade_count = min(max(1, int(fade_frames)), int(images.shape[0]))
        if fade_count == 1:
            weights = torch.ones(1, device=images.device, dtype=torch.float32)
        else:
            positions = torch.arange(
                fade_count, device=images.device, dtype=torch.float32
            )
            weights = 0.5 * (1.0 + torch.cos(
                math.pi * positions / float(fade_count - 1)
            ))
        gains = torch.exp2(applied_ev * weights).to(dtype=images.dtype)

        output = images.clone()
        corrected_rgb = output[:fade_count, ..., :3] * gains[:, None, None, None]
        output[:fade_count, ..., :3] = corrected_rgb.clamp(0.0, 1.0)
        _LOG.info(
            "h3_last_frame_exposure: clip %d opening %.6f -> reference %.6f "
            "(raw %.4f EV, applied %.4f EV over %d frames)",
            int(previous_clip_index) + 1, opening_luminance,
            reference_luminance, raw_ev, applied_ev, fade_count,
        )
        return (output,)

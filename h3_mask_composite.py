"""Restore source pixels outside an H3 video inpaint selection."""

from __future__ import annotations

import torch
import torch.nn.functional as F


def _selection_alpha(mask: torch.Tensor, expand: int, feather: int) -> torch.Tensor:
    """Build an inward-feathered alpha without changing pixels outside the selection."""
    try:
        import cv2
    except ImportError:
        cv2 = None
    if cv2 is not None:
        selected = (mask.detach().to("cpu").numpy() >= 0.5).astype("uint8")
        if expand:
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (expand * 2 + 1,) * 2)
            selected = cv2.dilate(selected, kernel)
        if feather:
            # Distance is positive only inside the expanded white region.
            # The half-pixel offset gives the outermost selected pixel a soft
            # contribution while every pixel outside remains exactly zero.
            distance = cv2.distanceTransform(selected, cv2.DIST_L2, 3)
            alpha = ((distance - 0.5) / feather).clip(0.0, 1.0)
        else:
            alpha = selected.astype("float32")
        return torch.from_numpy(alpha)[None, None].to(mask.device)

    # Torch-only fallback for environments without OpenCV.
    allowed = (mask >= 0.5).to(torch.float32)[None, None]
    if expand:
        allowed = F.max_pool2d(allowed, expand * 2 + 1, stride=1, padding=expand)
    if not feather:
        return allowed
    # Replicate padding keeps a selection touching the canvas edge fully opaque.
    softened = F.avg_pool2d(
        F.pad(allowed, (feather, feather, feather, feather), mode="replicate"),
        feather * 2 + 1,
        stride=1,
    )
    return softened * allowed


class SkebaH3FinalInpaintComposite:
    CATEGORY = "Skeba AI Nodes - Reference/Experimental"
    FUNCTION = "composite"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("video",)
    DESCRIPTION = (
        "After upscale, use generated video only inside the white mask. "
        "Expand and feather are measured in source-video pixels; feathering stays "
        "inside the expanded selection. Audio is unchanged."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "source_video": ("IMAGE",),
                "generated_video": ("IMAGE",),
                "mask": ("MASK",),
                "enabled": ("BOOLEAN", {"default": True}),
                "expand_mask": ("INT", {"default": 16, "min": 0, "max": 128, "step": 1}),
                "feather_edge": ("INT", {"default": 8, "min": 0, "max": 64, "step": 1}),
            },
            "optional": {"generation_mask": ("MASK",)},
        }

    def composite(
        self,
        source_video: torch.Tensor,
        generated_video: torch.Tensor,
        mask: torch.Tensor,
        enabled: bool = True,
        expand_mask: int = 16,
        feather_edge: int = 8,
        generation_mask: torch.Tensor | None = None,
    ):
        if not enabled:
            return (generated_video,)
        if source_video.ndim != 4 or generated_video.ndim != 4:
            raise ValueError("Final inpaint composite expects IMAGE batches [frames, height, width, channels].")
        if mask.ndim != 3:
            raise ValueError("Final inpaint composite expects one MASK per source frame [frames, height, width].")
        source_count, source_height, source_width, channels = source_video.shape
        generated_count, output_height, output_width, output_channels = generated_video.shape
        if source_count != generated_count or mask.shape[0] != source_count:
            raise ValueError(
                "Final inpaint composite needs matching source, mask, and generated frame counts "
                f"(got {source_count}, {mask.shape[0]}, {generated_count}). "
                "Use the trimmed source frames and composite before continuation trimming."
            )
        if tuple(mask.shape[1:]) != (source_height, source_width):
            raise ValueError("Final inpaint composite mask must match the resized source canvas.")
        if generation_mask is not None and tuple(generation_mask.shape) != tuple(mask.shape):
            raise ValueError("Final inpaint composite generation mask must match source-mask frames and canvas.")
        if channels != output_channels or channels not in (3, 4):
            raise ValueError("Final inpaint composite source and generated videos need matching RGB/RGBA channels.")
        if not 0 <= expand_mask <= 128 or not 0 <= feather_edge <= 64:
            raise ValueError("Final inpaint composite expand/feather settings are out of range.")
        if not torch.isfinite(mask).all():
            raise ValueError("Final inpaint composite mask contains non-finite values.")

        result = torch.empty_like(generated_video)
        for frame in range(source_count):
            original = source_video[frame].permute(2, 0, 1).unsqueeze(0)
            original = F.interpolate(
                original.to(device=generated_video.device, dtype=torch.float32),
                size=(output_height, output_width), mode="bilinear", align_corners=False,
            )
            alpha = _selection_alpha(
                mask[frame].to(device=generated_video.device), expand_mask, feather_edge
            )
            if generation_mask is not None:
                # Cell adjustment in Mask Grid Preview changes the sampler's
                # true editable area. Never reveal generated pixels beyond it.
                grid_alpha = _selection_alpha(
                    generation_mask[frame].to(device=generated_video.device),
                    0, feather_edge,
                )
                alpha = torch.minimum(alpha, grid_alpha)
            # Interpolated alpha can reach adjacent pixels. Clamp it against a
            # nearest-neighbor copy of the allowed area for exact preservation.
            allowed = (alpha > 0).to(alpha.dtype)
            alpha = F.interpolate(alpha, size=(output_height, output_width),
                                  mode="bilinear", align_corners=False)
            allowed = F.interpolate(allowed, size=(output_height, output_width), mode="nearest")
            alpha = (alpha * allowed).movedim(1, -1)[0]
            source_frame = original.movedim(1, -1)[0]
            result[frame] = torch.lerp(source_frame, generated_video[frame].to(torch.float32), alpha).to(result.dtype)
        return (result,)

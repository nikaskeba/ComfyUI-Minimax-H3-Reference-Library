"""Square, padding-free FlashHead crop and return-to-canvas composite."""

from __future__ import annotations

import math

import cv2
import numpy as np
import torch


def _boxes_for_first_frame(bboxes):
    if isinstance(bboxes, dict):
        return [bboxes]
    if not isinstance(bboxes, (list, tuple)) or not bboxes:
        return []
    first = bboxes[0]
    if isinstance(first, dict):
        return list(bboxes)
    return list(first or [])


def _square_from_bbox(box, width, height):
    for key in ("x", "y", "width", "height"):
        if key not in box or not math.isfinite(float(box[key])):
            raise ValueError(f"Target bounding box has no valid {key}.")
    x, y = float(box["x"]), float(box["y"])
    bw, bh = float(box["width"]), float(box["height"])
    if bw <= 0 or bh <= 0:
        raise ValueError("Target bounding box has zero width or height.")
    side = min(max(1, math.ceil(max(bw, bh))), width, height)
    cx, cy = x + bw / 2, y + bh / 2
    left = max(0, min(width - side, round(cx - side / 2)))
    top = max(0, min(height - side, round(cy - side / 2)))
    return int(left), int(top), int(side)


def _crop_square(image, box, output_size=512):
    if image.ndim != 4 or image.shape[0] < 1 or image.shape[-1] < 3:
        raise ValueError("Source must be a nonempty ComfyUI IMAGE batch.")
    height, width = image.shape[1:3]
    left, top, side = _square_from_bbox(box, width, height)
    source = image[0, top:top + side, left:left + side, :3].detach().float().cpu().numpy()
    resized = cv2.resize(source, (output_size, output_size), interpolation=cv2.INTER_AREA)
    if resized.ndim == 2:
        resized = resized[..., None]
    crop = torch.from_numpy(np.ascontiguousarray(resized)).unsqueeze(0).clamp(0, 1)
    crop_info = {"left": left, "top": top, "side": side,
                 "source_width": width, "source_height": height, "crop_size": output_size}
    return crop, crop_info


def _inner_alpha(side, feather):
    if feather <= 0:
        return np.ones((side, side, 1), dtype=np.float32)
    edge = min(int(feather), max(1, side // 2))
    coordinate = np.arange(side, dtype=np.float32)
    ramp = np.minimum(coordinate, side - 1 - coordinate)
    alpha = np.minimum(ramp[:, None], ramp[None, :]) / edge
    return np.clip(alpha, 0, 1)[..., None]


def _paste_square(source, generated, crop_info, feather=12):
    if source.ndim != 4 or generated.ndim != 4 or source.shape[-1] < 3 or generated.shape[-1] < 3:
        raise ValueError("Source and generated frames must be ComfyUI IMAGE batches.")
    count = len(generated)
    if len(source) not in (1, count):
        raise ValueError("Source must be one still image or match the generated frame count.")
    height, width = source.shape[1:3]
    if (width, height) != (crop_info["source_width"], crop_info["source_height"]):
        raise ValueError("Source image dimensions changed since the square crop was made.")
    left, top, side = (int(crop_info[k]) for k in ("left", "top", "side"))
    if side < 1 or left < 0 or top < 0 or left + side > width or top + side > height:
        raise ValueError("Square crop coordinates fall outside the source image.")
    alpha = _inner_alpha(side, feather)
    output = []
    for index in range(count):
        original = source[0 if len(source) == 1 else index].detach().float().cpu().numpy().copy()
        patch = generated[index, ..., :3].detach().float().cpu().numpy()
        patch = cv2.resize(patch, (side, side), interpolation=cv2.INTER_LINEAR)
        region = original[top:top + side, left:left + side, :3]
        original[top:top + side, left:left + side, :3] = region * (1 - alpha) + patch * alpha
        output.append(original)
    return torch.from_numpy(np.stack(output)).clamp(0, 1)


class SkebaAvatarSquareCrop:
    CATEGORY = "Skeba AI Nodes/Avatar"
    FUNCTION = "crop"
    RETURN_TYPES = ("IMAGE", "SKEBA_AVATAR_CROP", "STRING")
    RETURN_NAMES = ("avatar_512", "crop_info", "status")

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE",),
            "bboxes": ("BOUNDING_BOX",),
            "box_index": ("INT", {"default": 0, "min": 0, "max": 99}),
        }}

    def crop(self, image, bboxes, box_index=0):
        boxes = _boxes_for_first_frame(bboxes)
        if box_index >= len(boxes):
            raise ValueError(f"Target detection returned {len(boxes)} box(es); box_index={box_index} is unavailable.")
        crop, info = _crop_square(image, boxes[box_index])
        return crop, info, f"512×512 crop from source x={info['left']}, y={info['top']}, side={info['side']} px; no padding."


class SkebaAvatarSquareComposite:
    CATEGORY = "Skeba AI Nodes/Avatar"
    FUNCTION = "composite"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("frames",)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "original_image": ("IMAGE",),
            "generated_frames": ("IMAGE",),
            "crop_info": ("SKEBA_AVATAR_CROP",),
            "edge_feather": ("INT", {"default": 12, "min": 0, "max": 128}),
        }}

    def composite(self, original_image, generated_frames, crop_info, edge_feather=12):
        return (_paste_square(original_image, generated_frames, crop_info, edge_feather),)

import re

import torch


DEFAULT_COLORS = ("#00FF00", "#000000", "#FFFFFF") + ("#FFFFFF",) * 13
CHUNK_PIXELS = 65536


def parse_color(value):
    if not isinstance(value, str) or not re.fullmatch(r"#?[0-9a-fA-F]{6}", value.strip()):
        raise ValueError(f"Invalid palette color: {value!r}. Expected #RRGGBB.")
    value = "#" + value.strip().lstrip("#").upper()
    return value, [int(value[i:i + 2], 16) / 255.0 for i in (1, 3, 5)]


class FixedPaletteQuantize:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE",),
            "number_of_colors": ("INT", {"default": 3, "min": 2, "max": 16}),
            **{f"color_{i + 1}": ("STRING", {"default": color, "dynamicPrompts": False})
               for i, color in enumerate(DEFAULT_COLORS)},
        }, "optional": {
            "preview_frame": ("INT", {"default": 0, "min": 0, "max": 2147483647}),
            "sampling_mode": (["Exact Pixel", "3x3 Average", "5x5 Average"], {"default": "3x3 Average"}),
        }}

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "palette")
    FUNCTION = "quantize"
    CATEGORY = "Skeba AI Nodes - Utilities"
    DESCRIPTION = "Replace every RGB pixel with its nearest exact palette color. No dithering; preserves alpha."

    def quantize(self, image, number_of_colors=3, preview_frame=0, sampling_mode="3x3 Average", **colors):
        if not 2 <= number_of_colors <= 16:
            raise ValueError("number_of_colors must be between 2 and 16.")
        if image.ndim != 4 or image.shape[-1] not in (3, 4) or not image.is_floating_point():
            raise ValueError("Expected a floating-point IMAGE batch [B,H,W,3 or 4].")
        parsed = [parse_color(colors.get(f"color_{i + 1}", DEFAULT_COLORS[i]))
                  for i in range(number_of_colors)]
        palette = torch.tensor([rgb for _, rgb in parsed], device=image.device, dtype=image.dtype)
        comparison_palette = palette.to(dtype=torch.float32)
        output = torch.empty(image.shape, device=image.device, dtype=image.dtype)
        channels = image.shape[-1]
        # Chunk across pixels, never allocating a whole video's distance matrix.
        for frame_index in range(image.shape[0]):
            pixels = image[frame_index].reshape(-1, channels)
            result = output[frame_index].view(-1, channels)
            for start in range(0, pixels.shape[0], CHUNK_PIXELS):
                chunk = pixels[start:start + CHUNK_PIXELS]
                distance = (chunk[:, None, :3].float() - comparison_palette[None]).square().sum(-1)
                result[start:start + CHUNK_PIXELS, :3] = palette[distance.argmin(-1)]
                if channels == 4:
                    result[start:start + CHUNK_PIXELS, 3] = chunk[:, 3]
        return output, ",".join(value for value, _ in parsed)

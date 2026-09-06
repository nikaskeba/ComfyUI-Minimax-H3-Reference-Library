import os
from pathlib import Path

import folder_paths
from safetensors.torch import load_file, save_file


def _frame_path(filename_prefix, clip_index):
    prefix = (filename_prefix or "h3_context_frame/clip").strip().replace("\\", "/")
    relative = Path(prefix + f"_{int(clip_index):05d}.safetensors")
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("h3_last_frame: filename_prefix must stay inside ComfyUI/output")
    output_root = Path(folder_paths.get_output_directory()).resolve()
    path = (output_root / relative).resolve()
    if output_root not in path.parents:
        raise ValueError("h3_last_frame: filename_prefix must stay inside ComfyUI/output")
    return path


class SkebaH3SaveLastFrame:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "filename_prefix": ("STRING", {
                    "default": "h3_context_frame/clip",
                }),
                "clip_index": ("INT", {"default": 1, "min": 1, "max": 9999}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("frame_path",)
    FUNCTION = "save"
    OUTPUT_NODE = True
    CATEGORY = "Skeba AI Nodes - Motion Context"
    DESCRIPTION = "Losslessly save the final decoded frame for the next loop iteration."

    def save(self, images, filename_prefix="h3_context_frame/clip", clip_index=1):
        if getattr(images, "ndim", 0) != 4 or int(images.shape[0]) < 1:
            raise ValueError("h3_last_frame: expected a non-empty IMAGE batch")
        path = _frame_path(filename_prefix, clip_index)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(".tmp.safetensors")
        save_file(
            {"image": images[-1:].detach().cpu().contiguous()},
            str(temp_path),
            metadata={"format": "skeba_h3_last_frame_v1"},
        )
        os.replace(temp_path, path)
        return (str(path),)


class SkebaH3LoopGuideImage:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "use_original": ("BOOLEAN", {
                    "default": True,
                    "label_on": "ORIGINAL / NEW SCENE",
                    "label_off": "PREVIOUS LAST FRAME",
                }),
                "previous_clip_index": ("INT", {
                    "default": 1, "min": 0, "max": 9999,
                }),
                "filename_prefix": ("STRING", {
                    "default": "h3_context_frame/clip",
                }),
            },
            "optional": {
                "original_image": ("IMAGE", {"lazy": True}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("guide_image",)
    FUNCTION = "select"
    CATEGORY = "Skeba AI Nodes - Motion Context"
    DESCRIPTION = (
        "Use the original guide for a new scene, otherwise load the previous "
        "loop iteration's losslessly stored final frame."
    )

    @classmethod
    def IS_CHANGED(cls, original_image=None, use_original=True,
                   previous_clip_index=1,
                   filename_prefix="h3_context_frame/clip"):
        if use_original:
            return "original"
        path = _frame_path(filename_prefix, previous_clip_index)
        try:
            return f"{path}:{path.stat().st_mtime_ns}:{path.stat().st_size}"
        except OSError:
            return f"missing:{path}"

    def check_lazy_status(self, original_image=None, use_original=True, **kwargs):
        if use_original and original_image is None:
            return ["original_image"]
        return []

    def select(self, original_image=None, use_original=True, previous_clip_index=1,
               filename_prefix="h3_context_frame/clip"):
        if use_original:
            if original_image is None:
                raise ValueError("h3_last_frame: connect original_image for a new scene")
            return (original_image,)
        if int(previous_clip_index) < 1:
            raise ValueError(
                "h3_last_frame: previous_clip_index must be at least 1 on a continuation"
            )
        path = _frame_path(filename_prefix, previous_clip_index)
        if not path.is_file():
            raise FileNotFoundError(
                f"h3_last_frame: no stored final frame for clip {previous_clip_index}: {path}. "
                "Run that clip as a new scene first."
            )
        tensors = load_file(str(path), device="cpu")
        image = tensors.get("image")
        if image is None or image.ndim != 4 or int(image.shape[0]) != 1:
            raise ValueError(f"h3_last_frame: invalid stored frame: {path}")
        return (image,)

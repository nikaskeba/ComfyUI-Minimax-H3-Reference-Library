import comfy.utils
import torch.nn.functional as F


class SkebaH3GuideResizeToLatent:
    """Resize a guide image to the exact spatial canvas of an H3 AV latent."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "latent": ("LATENT",),
                "fit_mode": (["center crop", "edge pad", "stretch"], {
                    "default": "center crop",
                    "tooltip": (
                        "Center crop establishes the initial framing. Edge "
                        "pad carries that framing to another H3 resolution "
                        "without cropping or geometric distortion."
                    ),
                }),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    FUNCTION = "resize"
    CATEGORY = "Skeba AI Nodes - Reference"
    DESCRIPTION = (
        "Fit an image to the exact width and height of an H3 AV latent. Use "
        "center crop for the first guide fit, then edge-pad that normalized "
        "image to a later upscaled latent to retain the same composition."
    )

    @staticmethod
    def _video_latent(latent):
        if not isinstance(latent, dict) or "samples" not in latent:
            raise ValueError("h3_guide_resize: expected an H3 LATENT input")
        samples = latent["samples"]
        if not getattr(samples, "is_nested", False):
            raise ValueError("h3_guide_resize: expected a MiniMax H3 AV latent")
        tensors = getattr(samples, "tensors", None)
        if tensors is None:
            tensors = samples.unbind()
        if len(tensors) < 1:
            raise ValueError("h3_guide_resize: H3 latent has no video stream")
        video = tensors[0]
        if getattr(video, "ndim", 0) != 5 or int(video.shape[1]) != 24:
            raise ValueError(
                "h3_guide_resize: expected H3 video latent [B,24,T,H,W]"
            )
        return video

    def resize(self, image, latent, fit_mode="center crop"):
        if getattr(image, "ndim", 0) != 4:
            raise ValueError("h3_guide_resize: expected IMAGE [B,H,W,C]")
        video = self._video_latent(latent)
        height = int(video.shape[-2]) * 16
        width = int(video.shape[-1]) * 16
        samples = image[..., :3].movedim(-1, 1)
        if fit_mode == "edge pad":
            source_h, source_w = int(samples.shape[-2]), int(samples.shape[-1])
            scale = min(width / source_w, height / source_h)
            fitted_w = max(1, min(width, round(source_w * scale)))
            fitted_h = max(1, min(height, round(source_h * scale)))
            resized = comfy.utils.common_upscale(
                samples, fitted_w, fitted_h, "lanczos", "disabled"
            )
            pad_w = width - fitted_w
            pad_h = height - fitted_h
            resized = F.pad(
                resized,
                (pad_w // 2, pad_w - pad_w // 2,
                 pad_h // 2, pad_h - pad_h // 2),
                mode="replicate",
            )
        else:
            crop = "center" if fit_mode == "center crop" else "disabled"
            resized = comfy.utils.common_upscale(
                samples, width, height, "lanczos", crop
            )
        return (resized.movedim(1, -1),)

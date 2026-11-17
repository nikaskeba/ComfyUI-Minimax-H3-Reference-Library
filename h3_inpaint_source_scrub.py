"""Optionally remove source appearance from H3's selected video latent."""

import torch
import torch.nn.functional as F


def _scrub_video(video, mask, spatial_halo=0, temporal_halo=0):
    if video.ndim != 5 or video.shape[1] != 24:
        raise ValueError("H3 source scrub expects a video latent [batch,24,time,height,width].")
    if mask.ndim != 3 or not torch.isfinite(mask).all():
        raise ValueError("H3 source scrub expects a finite generation mask [frames,height,width].")
    batch, _, time, height, width = video.shape
    # A selected source pixel can affect a neighboring VAE token. Max pooling
    # prevents thin face regions from disappearing during resolution reduction.
    selected = F.adaptive_max_pool3d(
        mask.to(device=video.device, dtype=torch.float32)[None, None],
        output_size=(time, height, width),
    ) >= 0.5
    if temporal_halo or spatial_halo:
        selected = F.max_pool3d(
            selected.float(),
            kernel_size=(2 * temporal_halo + 1, 2 * spatial_halo + 1,
                         2 * spatial_halo + 1),
            stride=1, padding=(temporal_halo, spatial_halo, spatial_halo),
        ) >= 0.5
    selected = selected.expand(batch, 1, time, height, width)
    scrubbed = video.masked_fill(selected, 0)
    return scrubbed, int(selected.sum().item()), selected.numel()


class SkebaH3InpaintSourceScrub:
    CATEGORY = "Skeba AI Nodes - Reference/Experimental"
    FUNCTION = "scrub"
    RETURN_TYPES = ("LATENT", "STRING")
    RETURN_NAMES = ("latent", "status")
    DESCRIPTION = (
        "Experimental: zero the selected source-video latent before masked H3 sampling. "
        "Unselected video tokens and the audio latent stay unchanged."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "av_latent": ("LATENT",),
            "enabled": ("BOOLEAN", {"default": False}),
            "spatial_halo": ("INT", {"default": 1, "min": 0, "max": 3}),
            "temporal_halo": ("INT", {"default": 0, "min": 0, "max": 2}),
        }}

    def scrub(self, av_latent, enabled=False, spatial_halo=1, temporal_halo=0):
        if not enabled:
            return av_latent, "Source latent unchanged."
        import comfy.nested_tensor

        samples = av_latent.get("samples")
        noise_mask = av_latent.get("noise_mask")
        if not getattr(samples, "is_nested", False) or not getattr(noise_mask, "is_nested", False):
            raise ValueError("Source scrub needs the masked joint AV latent from MiniMax H3 Set Generation Mask.")
        streams = samples.unbind()
        masks = noise_mask.unbind()
        if len(streams) != 2 or len(masks) != 2:
            raise ValueError("Source scrub needs one video and one audio stream with matching generation masks.")
        video, audio = streams
        scrubbed, selected, total = _scrub_video(video, masks[0],
                                                  int(spatial_halo), int(temporal_halo))
        result = av_latent.copy()
        result["samples"] = comfy.nested_tensor.NestedTensor((scrubbed, audio))
        return result, f"Cleared {selected}/{total} source-video latent positions; audio untouched."

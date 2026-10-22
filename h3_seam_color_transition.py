"""A short, conservative color transition across an H3 clip join."""

import math

import torch


def transition_color(images, previous, context_frames, discard_frames,
                     strength=0.6, fade_frames=24, max_change=0.12,
                     analysis_frames=6):
    """Match corresponding pinned/previous frames, then fade the gain out.

    The comparison uses overlapping frames representing the same moments.
    Only delivered frames change; context frames and audio remain untouched.
    """
    n = int(context_frames)
    start = int(discard_frames)
    if (strength <= 0 or n <= 0 or start < n or start >= len(images)
            or len(previous) < n or images.ndim != 4
            or previous.ndim != 4 or images.shape[-1] < 3
            or tuple(previous.shape[1:]) != tuple(images.shape[1:])):
        return images

    count = min(max(1, int(analysis_frames)), n)
    # Previous tail and incoming pinned head represent the same time span.
    old = previous[-count:, ..., :3].float()
    pinned = images[n - count:n, ..., :3].float()
    old_mean = old.mean(dim=(0, 1, 2))
    pinned_mean = pinned.mean(dim=(0, 1, 2))
    if torch.any(old_mean < 0.01) or torch.any(pinned_mean < 0.01):
        return images

    # Each RGB channel receives a separately bounded adjustment, unlike a
    # luminance-only exposure match. No spatial or temporal frame mixing.
    log_gain = torch.log(old_mean / pinned_mean)
    limit = math.log1p(max(0.0, float(max_change)))
    log_gain = log_gain.clamp(-limit, limit) * float(strength)
    length = min(max(1, int(fade_frames)), len(images) - start)
    positions = torch.arange(length, device=images.device, dtype=torch.float32)
    weights = (torch.ones_like(positions) if length == 1 else
               0.5 * (1 + torch.cos(math.pi * positions / (length - 1))))
    gains = torch.exp(log_gain.to(images.device)[None, :] * weights[:, None])
    result = images.clone()
    result[start:start + length, ..., :3] = (
        images[start:start + length, ..., :3].float()
        * gains[:, None, None, :]
    ).clamp(0, 1).to(images.dtype)
    return result


class SkebaH3SeamColorTransition:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "context_frames": ("INT,FLOAT,IMAGE,LATENT", {"default": 22}),
                "discard_frames": ("INT", {"default": 22, "min": 0, "max": 4096}),
                "strength": ("FLOAT", {"default": 0.6, "min": 0.0,
                                       "max": 1.0, "step": 0.05}),
                "fade_frames": ("INT", {"default": 24, "min": 1, "max": 240}),
                "max_change": ("FLOAT", {"default": 0.12, "min": 0.0,
                                         "max": 0.5, "step": 0.01}),
            },
            "optional": {
                "accumulation": ("ACCUMULATION",),
                "bypass": ("BOOLEAN", {"default": False}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("images",)
    FUNCTION = "apply"
    CATEGORY = "Skeba AI Nodes - Motion Context"
    DESCRIPTION = ("Match RGB color from the previous saved clip to the "
                   "incoming pinned overlap, then fade that correction over "
                   "the first delivered frames. Strength 0 is a no-op.")

    def apply(self, images, context_frames, discard_frames, strength=0.6,
              fade_frames=24, max_change=0.12, accumulation=None,
              bypass=False):
        if bypass or accumulation is None or strength <= 0:
            return (images,)
        clips = accumulation.get("accum", []) if isinstance(accumulation, dict) else []
        if not clips:
            return (images,)
        previous = (clips[-1].seam_frames(int(context_frames))
                    if hasattr(clips[-1], "seam_frames")
                    else clips[-1].get_components().images)
        return (transition_color(images, previous, context_frames,
                                 discard_frames, strength, fade_frames,
                                 max_change),)

"""Conservative luminance matching for decoded clip joins."""

import math

import torch


_ANALYSIS_FRAMES = 6
_DEADBAND_EV = 0.02
_MAX_EV = 0.25
_BLACK_FLOOR = 1e-4


def _mean_luminance(images):
    rgb = images[..., :3].float()
    luminance = (rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 +
                 rgb[..., 2] * 0.0722)
    return float(luminance.mean().item())


class H3SeamExposureMatch:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "strength": ("FLOAT", {
                    "default": 0.75, "min": 0.0, "max": 1.0,
                    "step": 0.05,
                    "tooltip": "0 disables matching. Lower values preserve "
                               "more of the new clip's generated exposure."}),
                "fade_frames": ("INT", {
                    "default": 24, "min": 1, "max": 240,
                    "tooltip": "Fade the correction back to neutral across "
                               "this many frames. 24 frames is one second at "
                               "the standard H3 frame rate."}),
            },
            "optional": {
                "accumulation": ("ACCUMULATION", {
                    "tooltip": "Previously accepted VIDEO clips from the "
                               "loop accumulation. Leave unwired for a "
                               "bit-identical pass-through."}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("images",)
    FUNCTION = "match"
    CATEGORY = "Skeba AI Nodes - Motion Context"
    DESCRIPTION = ("Match the start luminance of a decoded clip to the end "
                   "of the previously accumulated clip, then fade the "
                   "correction back to neutral.")

    def match(self, images, strength=0.75, fade_frames=24,
              accumulation=None):
        if float(strength) <= 0.0 or accumulation is None:
            return (images,)
        if images.ndim != 4 or images.shape[0] == 0 or images.shape[-1] < 3:
            return (images,)
        if not isinstance(accumulation, dict):
            raise ValueError(
                "h3_motion_context: seam exposure expected a loop "
                "ACCUMULATION of VIDEO clips.")

        clips = accumulation.get("accum", [])
        if not clips:
            return (images,)
        try:
            previous = clips[-1].get_components().images
        except (AttributeError, TypeError):
            raise ValueError(
                "h3_motion_context: seam exposure accumulation does not "
                "contain VIDEO clips.") from None

        if previous.ndim != 4 or previous.shape[0] == 0 or previous.shape[-1] < 3:
            return (images,)
        if tuple(previous.shape[1:]) != tuple(images.shape[1:]):
            raise ValueError(
                "h3_motion_context: seam exposure cannot match %s frames "
                "to %s frames; clip resolutions must agree."
                % (tuple(previous.shape[1:]), tuple(images.shape[1:])))

        count = min(_ANALYSIS_FRAMES, int(previous.shape[0]),
                    int(images.shape[0]))
        reference_luminance = _mean_luminance(previous[-count:])
        target_luminance = _mean_luminance(images[:count])
        if (reference_luminance <= _BLACK_FLOOR or
                target_luminance <= _BLACK_FLOOR):
            return (images,)

        exposure_ev = math.log2(reference_luminance / target_luminance)
        if abs(exposure_ev) < _DEADBAND_EV:
            return (images,)
        exposure_ev = max(-_MAX_EV, min(_MAX_EV, exposure_ev))
        exposure_ev *= float(strength)

        fade_count = min(max(1, int(fade_frames)), int(images.shape[0]))
        if fade_count == 1:
            weights = torch.ones(1, device=images.device, dtype=torch.float32)
        else:
            positions = torch.arange(
                fade_count, device=images.device, dtype=torch.float32)
            weights = 0.5 * (1.0 + torch.cos(
                math.pi * positions / float(fade_count - 1)))
        gains = torch.exp2(exposure_ev * weights).to(dtype=images.dtype)

        output = images.clone()
        output[:fade_count] = (output[:fade_count] *
                               gains[:, None, None, None]).clamp(0.0, 1.0)
        return (output,)


"""Resize an H3 video latent on its 16-pixel spatial grid."""

import torch
import torch.nn.functional as F


class SkebaH3VideoLatentResize:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "video_latent": ("LATENT",),
            "width": ("INT", {"default": 736, "min": 16, "max": 8192, "step": 16}),
            "height": ("INT", {"default": 416, "min": 16, "max": 8192, "step": 16}),
        }}

    RETURN_TYPES = ("LATENT",)
    FUNCTION = "resize"
    CATEGORY = "Skeba AI Nodes - Motion Context"
    DESCRIPTION = ("Resize only the H3 video latent to the requested pixel canvas "
                   "using H3's 16-pixel grid. Place between Separate AV Latent "
                   "and Concat AV Latent; the audio stream stays unchanged.")

    def resize(self, video_latent, width, height):
        if width % 16 or height % 16:
            raise ValueError("H3 video latent resize: width and height must be multiples of 16.")
        samples = video_latent.get("samples") if isinstance(video_latent, dict) else None
        if not isinstance(samples, torch.Tensor) or samples.ndim != 5:
            raise ValueError("H3 video latent resize: connect the video_latent output of Separate AV Latent.")
        size = (samples.shape[2], height // 16, width // 16)
        if tuple(samples.shape[2:]) == size:
            return (video_latent,)
        resized = F.interpolate(samples.float(), size=size, mode="area").to(samples.dtype)
        return ({**video_latent, "samples": resized},)


class SkebaH3AVContextResize:
    """Resize a loaded H3 AV context without touching its audio or bypass state."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "width": ("INT", {"default": 736, "min": 16, "max": 8192, "step": 16}),
            "height": ("INT", {"default": 416, "min": 16, "max": 8192, "step": 16}),
            "av_latent": ("LATENT",),
        }}

    RETURN_TYPES = ("LATENT",)
    FUNCTION = "resize"
    CATEGORY = "Skeba AI Nodes - Motion Context"
    DESCRIPTION = ("Downsize the video stream of a loaded H3 AV context on its "
                   "16-pixel grid. Keep audio and first-prompt bypass unchanged.")

    def resize(self, width, height, av_latent):
        if width % 16 or height % 16:
            raise ValueError("H3 AV context resize: width and height must be multiples of 16.")
        if not isinstance(av_latent, dict):
            raise ValueError("H3 AV context resize: connect H3 Motion Context Load Latent.")
        if av_latent.get("skeba_h3_motion_context_bypassed") and av_latent.get("samples") is None:
            return (av_latent,)
        streams = av_latent.get("samples")
        if not isinstance(streams, (list, tuple)) or len(streams) < 2:
            raise ValueError("H3 AV context resize: expected the loaded video/audio latent pair.")
        video, audio = streams[:2]
        if not isinstance(video, torch.Tensor) or video.ndim != 5:
            raise ValueError("H3 AV context resize: video stream must be a five-dimensional tensor.")
        source_width, source_height = video.shape[4] * 16, video.shape[3] * 16
        ratio_error = abs((source_width / source_height) / (width / height) - 1.0)
        if ratio_error > 0.02:
            raise ValueError(
                f"H3 AV context resize: source {source_width}x{source_height} and target "
                f"{width}x{height} differ in aspect ratio by {ratio_error:.1%}. "
                "Choose a closer even H3 latent grid or use an exact-ratio "
                "scale compatible with the 2x2 patch grid."
            )
        size = (video.shape[2], height // 16, width // 16)
        if tuple(video.shape[2:]) == size:
            return (av_latent,)
        resized = F.interpolate(video.float(), size=size, mode="area").to(video.dtype)
        kept = [resized, audio, *streams[2:]]
        return ({**av_latent, "samples": tuple(kept) if isinstance(streams, tuple) else kept},)


class SkebaH3VideoLatentAspectMatch:
    """Choose a close H3 grid compatible with 2x2 sampler patches."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "video_latent": ("LATENT",),
            "base_width": ("INT", {"default": 736, "min": 16, "max": 8192, "step": 16}),
            "base_height": ("INT", {"default": 416, "min": 16, "max": 8192, "step": 16}),
        }}

    RETURN_TYPES = ("LATENT",)
    FUNCTION = "match"
    CATEGORY = "Skeba AI Nodes - Motion Context"
    DESCRIPTION = ("After the learned H3 latent upscaler, prefer the closest "
                   "base aspect ratio on an even H3 latent grid required by "
                   "the sampler's 2x2 patches. Audio is connected separately.")

    def match(self, video_latent, base_width, base_height):
        if base_width % 16 or base_height % 16:
            raise ValueError("H3 aspect match: base dimensions must be multiples of 16.")
        samples = video_latent.get("samples") if isinstance(video_latent, dict) else None
        if not isinstance(samples, torch.Tensor) or samples.ndim != 5:
            raise ValueError("H3 aspect match: connect the video output of the latent upscaler.")
        current_h, current_w = samples.shape[-2:]
        aspect = base_width / base_height
        candidates = []
        for target_w in range(max(2, current_w - 4) // 2 * 2, current_w + 6, 2):
            for target_h in range(max(2, current_h - 4) // 2 * 2, current_h + 6, 2):
                ratio_error = abs((target_w / target_h) / aspect - 1.0)
                size_error = abs(target_w / current_w - 1.0) + abs(target_h / current_h - 1.0)
                candidates.append((ratio_error, size_error, target_w, target_h))
        # Prefer exact aspect when a patch-safe grid is close to the learned
        # upscaler's output (e.g. 2x). At 1.5x this base ratio has no nearby
        # even-grid exact solution, so choose the least disruptive near match.
        exact = [candidate for candidate in candidates
                 if candidate[0] < 1e-9 and candidate[1] <= 0.10]
        if exact:
            _, _, target_w, target_h = min(exact, key=lambda c: (c[1], c[2], c[3]))
        else:
            _, _, target_w, target_h = min(
                candidates, key=lambda c: (c[0] * 4 + c[1], c[1], c[2], c[3]))
        ratio_error = abs((target_w / target_h) / aspect - 1.0)
        if ratio_error > 0.02:
            raise ValueError(
                f"H3 aspect match: closest even latent grid {target_w * 16}x{target_h * 16} "
                f"is {ratio_error:.1%} from base aspect {base_width}x{base_height}."
            )
        if (current_w, current_h) == (target_w, target_h):
            return (video_latent,)
        size = (samples.shape[2], target_h, target_w)
        resized = F.interpolate(samples.float(), size=size, mode="trilinear", align_corners=False).to(samples.dtype)
        return ({**video_latent, "samples": resized},)

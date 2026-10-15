"""Choose source-video inpainting or prompt video guided by selected audio."""

import torch


class SkebaH3InpaintLatentMode:
    CATEGORY = "Skeba AI Nodes - Reference/Experimental"
    FUNCTION = "select"
    RETURN_TYPES = ("LATENT", "STRING")
    RETURN_NAMES = ("latent", "status")
    DESCRIPTION = (
        "Source video inpaint uses the tracked mask. Audio drives video starts from "
        "a blank H3 video latent, keeps the selected source audio, and skips mask tracking."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "mode": (["source video inpaint", "audio drives video"],),
            "audio_mode": (["generate audio", "preserve source audio"],),
            "width": ("INT", {"default": 1344, "min": 32, "max": 8192}),
            "height": ("INT", {"default": 768, "min": 32, "max": 8192}),
            "length": ("INT", {"default": 124, "min": 5, "max": 3600}),
        }, "optional": {
            "inpaint_latent": ("LATENT", {"lazy": True}),
            "source_audio_latent": ("LATENT", {"lazy": True}),
        }}

    def check_lazy_status(self, mode, inpaint_latent=None, source_audio_latent=None, **kwargs):
        if mode == "source video inpaint" and inpaint_latent is None:
            return ["inpaint_latent"]
        if mode == "audio drives video" and source_audio_latent is None:
            return ["source_audio_latent"]
        return []

    def select(self, mode, audio_mode, width, height, length,
               inpaint_latent=None, source_audio_latent=None):
        if mode == "source video inpaint":
            if inpaint_latent is None:
                raise ValueError("Connect the masked source-video latent for inpaint mode.")
            return (inpaint_latent, "Source-video inpaint and subject tracking enabled.")
        if mode != "audio drives video":
            raise ValueError(f"Unknown H3 video mode: {mode}")
        if source_audio_latent is None:
            raise ValueError("Audio-driven video needs the selected audio's VAE latent.")
        audio = source_audio_latent.get("samples")
        if not isinstance(audio, torch.Tensor) or audio.ndim != 4 or audio.shape[1:3] != (32, 2):
            raise ValueError("Audio-driven video needs an H3 audio VAE latent [batch,32,2,time].")
        width, height, length = int(width), int(height), int(length)
        if width % 16 or height % 16 or length < 5 or (length - 5) % 17:
            raise ValueError("Audio-driven video needs a 16-pixel canvas and a valid 17k+5 H3 length.")
        import comfy.nested_tensor

        video_t = 2 if length == 5 else ((length - 5) // 17) * 5 + 2
        audio_t = round(length / 24 * 40)
        if abs(audio.shape[-1] - audio_t) > 2:
            raise ValueError(
                f"Selected audio encodes to {audio.shape[-1]} H3 steps, but the "
                f"video window needs {audio_t}. Check the source-window trim and audio VAE."
            )
        if audio.shape[-1] > audio_t:
            audio = audio[..., :audio_t]
        elif audio.shape[-1] < audio_t:
            audio = torch.nn.functional.pad(audio, (0, audio_t - audio.shape[-1]))
        video = torch.zeros((audio.shape[0], 24, video_t, height // 16, width // 16),
                            dtype=audio.dtype, device=audio.device)
        audio = audio.contiguous()
        video_mask = torch.ones((audio.shape[0], 1, video_t, height // 16, width // 16),
                                dtype=torch.float32, device=audio.device)
        audio_mask = (torch.ones_like(audio, dtype=torch.float32)
                      if audio_mode == "generate audio" else
                      torch.zeros_like(audio, dtype=torch.float32))
        return ({"samples": comfy.nested_tensor.NestedTensor((video, audio)),
                 "noise_mask": comfy.nested_tensor.NestedTensor((video_mask, audio_mask))},
                f"Prompt-generated video, {length} frames; "
                + ("new audio generated." if audio_mode == "generate audio"
                   else "selected audio preserved."))


class SkebaH3InpaintVideoMode:
    CATEGORY = "Skeba AI Nodes - Reference/Experimental"
    FUNCTION = "select"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("video",)
    DESCRIPTION = "Skip the source-video composite when audio drives prompt-generated video."

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"mode": (["source video inpaint", "audio drives video"],)},
                "optional": {
                    "inpaint_video": ("IMAGE", {"lazy": True}),
                    "generated_video": ("IMAGE", {"lazy": True}),
                }}

    def check_lazy_status(self, mode, inpaint_video=None, generated_video=None, **kwargs):
        if mode == "source video inpaint" and inpaint_video is None:
            return ["inpaint_video"]
        if mode == "audio drives video" and generated_video is None:
            return ["generated_video"]
        return []

    def select(self, mode, inpaint_video=None, generated_video=None):
        if mode == "source video inpaint":
            if inpaint_video is None:
                raise ValueError("Connect the final inpaint composite.")
            return (inpaint_video,)
        if mode == "audio drives video":
            if generated_video is None:
                raise ValueError("Connect the decoded prompt-generated video.")
            return (generated_video,)
        raise ValueError(f"Unknown H3 video mode: {mode}")

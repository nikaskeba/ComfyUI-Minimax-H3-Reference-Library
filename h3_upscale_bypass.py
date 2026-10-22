"""Select a completed H3 base pass or the optional upscale pass."""


class SkebaH3UpscaleBypass:
    CATEGORY = "Skeba AI Nodes - Reference/Experimental"
    FUNCTION = "select"
    RETURN_TYPES = ("LATENT", "BOOLEAN")
    RETURN_NAMES = ("latent", "save_upscale_context")
    DESCRIPTION = (
        "Base only skips the upscale model and second sampler. Upscaled keeps "
        "the existing two-pass output. Use one mode for the whole prompt loop."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mode": (["Upscaled", "Base only"], {"default": "Upscaled"}),
                "prompts_remain": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "base_latent": ("LATENT", {"lazy": True}),
                "upscaled_latent": ("LATENT", {"lazy": True}),
            },
        }

    def check_lazy_status(self, mode, prompts_remain=False, base_latent=None,
                          upscaled_latent=None, **kwargs):
        if mode == "Base only" and base_latent is None:
            return ["base_latent"]
        if mode == "Upscaled" and upscaled_latent is None:
            return ["upscaled_latent"]
        return []

    def select(self, mode, prompts_remain=False, base_latent=None,
               upscaled_latent=None):
        if mode == "Base only":
            if base_latent is None:
                raise ValueError("H3 upscale bypass: connect the first sampler to base_latent.")
            return (base_latent, False)
        if mode == "Upscaled":
            if upscaled_latent is None:
                raise ValueError("H3 upscale bypass: connect the upscale sampler to upscaled_latent.")
            return (upscaled_latent, bool(prompts_remain))
        raise ValueError(f"Unknown H3 upscale mode: {mode}")


class SkebaH3UpscaleTrimBypass:
    """Use the selected pass's continuation trim without executing the other pass."""

    CATEGORY = "Skeba AI Nodes - Reference/Experimental"
    FUNCTION = "select"
    RETURN_TYPES = ("INT",)
    RETURN_NAMES = ("trim_frames",)
    DESCRIPTION = (
        "Select the base or upscale Motion Context trim count. The unused "
        "pass is lazy and does not execute just to calculate trimming."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mode": (["Upscaled", "Base only"], {"default": "Upscaled"}),
                "base_trim_frames": ("INT", {"lazy": True}),
                "upscaled_trim_frames": ("INT", {"lazy": True}),
            },
        }

    def check_lazy_status(self, mode, base_trim_frames=None,
                          upscaled_trim_frames=None, **kwargs):
        if mode == "Base only" and base_trim_frames is None:
            return ["base_trim_frames"]
        if mode == "Upscaled" and upscaled_trim_frames is None:
            return ["upscaled_trim_frames"]
        return []

    def select(self, mode, base_trim_frames=None, upscaled_trim_frames=None):
        if mode == "Base only":
            if base_trim_frames is None:
                raise ValueError("H3 base-only trimming needs the base Motion Context trim count.")
            return (int(base_trim_frames),)
        if mode == "Upscaled":
            if upscaled_trim_frames is None:
                raise ValueError("H3 upscale trimming needs the upscale Motion Context trim count.")
            return (int(upscaled_trim_frames),)
        raise ValueError(f"Unknown H3 upscale mode: {mode}")

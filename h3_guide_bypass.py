from comfy_api.latest import io
from comfy_extras.nodes_minimax_h3 import MiniMaxH3AddGuide


class SkebaMiniMaxH3AddGuideBypass(io.ComfyNode):
    """Native MiniMax H3 guide with a lazy bypass control."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="SkebaMiniMaxH3AddGuideBypass",
            display_name="SKEBA MiniMax H3 Add Guide with Bypass",
            category="Skeba AI Nodes - Reference",
            description=(
                "Add a native MiniMax H3 image/audio guide, or return the "
                "conditioning unchanged without evaluating the guide branch."
            ),
            inputs=[
                io.Conditioning.Input("positive"),
                io.Latent.Input("latent", optional=True, lazy=True),
                io.Vae.Input("vae", optional=True, lazy=True),
                io.Vae.Input("audio_vae", optional=True, lazy=True),
                io.Image.Input("image", optional=True, lazy=True),
                io.Audio.Input("audio", optional=True, lazy=True),
                io.Int.Input("frame_idx", default=0, min=-9999, max=9999),
                io.Boolean.Input(
                    "bypass",
                    default=False,
                    label_on="BYPASS",
                    label_off="GUIDE",
                    tooltip=(
                        "When enabled, return positive unchanged and do not "
                        "load or encode the guide inputs."
                    ),
                ),
            ],
            outputs=[io.Conditioning.Output(display_name="positive")],
        )

    @classmethod
    def check_lazy_status(cls, positive, frame_idx, bypass, **kwargs):
        if bypass:
            return []

        needed = []
        if kwargs.get("latent") is None:
            needed.append("latent")

        image_connected = "image" in kwargs
        audio_connected = "audio" in kwargs
        if not image_connected and not audio_connected:
            # Let execute produce the native actionable error when neither is wired.
            return needed
        if image_connected and kwargs.get("image") is None:
            needed.append("image")
        if audio_connected and kwargs.get("audio") is None:
            needed.append("audio")
        if image_connected and kwargs.get("vae") is None:
            needed.append("vae")
        if audio_connected and kwargs.get("audio_vae") is None:
            needed.append("audio_vae")
        return needed

    @classmethod
    def execute(cls, positive, frame_idx, bypass, latent=None, vae=None,
                audio_vae=None, image=None, audio=None):
        if bypass:
            return io.NodeOutput(positive)
        if latent is None:
            raise ValueError("H3 Add Guide with Bypass: connect latent while GUIDE is active")
        return MiniMaxH3AddGuide.execute(
            positive=positive,
            latent=latent,
            frame_idx=frame_idx,
            vae=vae,
            audio_vae=audio_vae,
            image=image,
            audio=audio,
        )

"""Optional sparse H3 keyframes sampled from a completed base-pass decode."""

from __future__ import annotations

import torch

from comfy_api.latest import io
from comfy_extras import nodes_minimax_h3 as h3

from .h3_multi_guide import _latent_geometry


def _sparse_positions(frame_count: int, occupied: set[int]) -> list[int]:
    """Choose two interior thirds, without duplicating existing guides."""
    if frame_count < 4:
        return []
    candidates = (round((frame_count - 1) / 3), round(2 * (frame_count - 1) / 3))
    return sorted({index for index in candidates if 0 < index < frame_count - 1
                   and index not in occupied})


class SkebaH3UpscaleContextGuides(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="SkebaH3UpscaleContextGuides",
            display_name="SKEBA H3 Upscale Context Guides",
            category="Skeba AI Nodes - Reference/Experimental",
            description=("Optionally anchor upscale refinement with two interior "
                         "frames from the completed base pass. Audio is unchanged."),
            inputs=[
                io.Conditioning.Input("positive"),
                io.Combo.Input("mode", options=["Off", "Automatic sparse"], default="Off"),
                io.Latent.Input("latent", optional=True, lazy=True),
                io.Image.Input("base_frames", optional=True, lazy=True),
                io.Vae.Input("vae", optional=True, lazy=True),
            ],
            outputs=[io.Conditioning.Output(display_name="positive"),
                     io.String.Output(display_name="status")],
        )

    @classmethod
    def check_lazy_status(cls, positive, mode="Off", latent=None,
                          base_frames=None, vae=None):
        if mode == "Off":
            return []
        return [name for name, value in (("latent", latent),
                                         ("base_frames", base_frames),
                                         ("vae", vae)) if value is None]

    @classmethod
    def execute(cls, positive, mode="Off", latent=None, base_frames=None, vae=None):
        if mode == "Off":
            return io.NodeOutput(positive, "Off — original upscale conditioning")
        if mode != "Automatic sparse":
            raise ValueError(f"Unknown H3 upscale context mode: {mode}")
        if latent is None or base_frames is None or vae is None:
            raise ValueError("Automatic sparse guides need the completed H3 latent, "
                             "its decoded video frames, and the H3 video VAE.")
        width, height, frame_count, _ = _latent_geometry(latent)
        if not isinstance(base_frames, torch.Tensor) or base_frames.ndim != 4 \
                or base_frames.shape[-1] < 3:
            raise ValueError("base_frames must be an IMAGE batch [frames,H,W,C].")
        if base_frames.shape[0] != frame_count:
            raise ValueError(
                f"Decoded base pass has {base_frames.shape[0]} frames, but the "
                f"upscale latent has {frame_count}. Decode the same completed "
                "latent supplied to the upscaler."
            )
        if not positive:
            raise ValueError("Upscale context needs positive H3 conditioning.")
        occupied = set()
        for _, metadata in positive:
            for guide in metadata.get("minimax_keyframes", []):
                index = guide.get("resolved_frame_index")
                if not isinstance(index, int) or not 0 <= index < frame_count:
                    raise ValueError("Existing H3 keyframe has an invalid frame index.")
                occupied.add(index)
        positions = _sparse_positions(frame_count, occupied)
        if not positions:
            return io.NodeOutput(positive, "Automatic sparse — no free interior frames")
        added = []
        for index in positions:
            image = h3._resize(base_frames[index:index + 1, :, :, :3],
                               width, height, "center")
            added.append({"resolved_frame_index": index, "latent": vae.encode(image)})
        result = []
        for entry in positive:
            copied = list(entry)
            metadata = dict(entry[1])
            metadata["minimax_keyframes"] = sorted(
                list(metadata.get("minimax_keyframes", [])) + added,
                key=lambda item: item["resolved_frame_index"])
            copied[1] = metadata
            result.append(tuple(copied) if isinstance(entry, tuple) else copied)
        return io.NodeOutput(result,
                             "Automatic sparse — base-pass guides at frames "
                             + ", ".join(map(str, positions)))

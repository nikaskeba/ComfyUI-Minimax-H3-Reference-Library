"""Experimental multi-frame image guides for MiniMax H3."""

from __future__ import annotations

import torch

import node_helpers
from comfy.ldm.minimax.model import FRAME_PER_TOKEN
from comfy_api.latest import io
from comfy_extras import nodes_minimax_h3 as h3


MAX_GUIDES = 8


def _parse_frame_indices(value: str) -> list[int]:
    value = str(value or "").strip()
    if not value:
        return []

    parts = value.split(",")
    if any(not part.strip() for part in parts):
        raise ValueError(
            "Multi-Frame H3 Guide: batch_frame_indices must be comma-separated "
            "integers, for example 0, 22, 60, -1"
        )
    try:
        return [int(part.strip()) for part in parts]
    except ValueError as exc:
        raise ValueError(
            "Multi-Frame H3 Guide: batch_frame_indices must be comma-separated "
            "integers, for example 0, 22, 60, -1"
        ) from exc


def _latent_geometry(latent):
    try:
        samples = latent["samples"]
        tensors = samples.tensors
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError(
            "Multi-Frame H3 Guide: connect a MiniMax H3 AV latent"
        ) from exc

    if (
        not getattr(samples, "is_nested", False)
        or len(tensors) != 2
        or tensors[0].ndim != 5
        or tensors[0].shape[1] != 24
    ):
        raise ValueError(
            "Multi-Frame H3 Guide: latent must be a MiniMax H3 AV latent"
        )

    video = tensors[0]
    frame_count = sum(
        FRAME_PER_TOKEN[index % 5] for index in range(video.shape[2])
    )
    return video.shape[4] * 16, video.shape[3] * 16, frame_count, video


def _resolve_frame_index(requested: int, frame_count: int) -> int:
    resolved = requested if requested >= 0 else frame_count + requested
    if resolved < 0 or resolved >= frame_count:
        raise ValueError(
            f"Multi-Frame H3 Guide: frame index {requested} is outside the "
            f"output video's {frame_count} frames (valid: "
            f"-{frame_count} through {frame_count - 1})"
        )
    return resolved


class SkebaMiniMaxH3MultiFrameGuideTest(io.ComfyNode):
    """Add up to eight native single-frame keyframes in one lazy node."""

    @classmethod
    def define_schema(cls):
        inputs = [
            io.Conditioning.Input("positive"),
            io.Latent.Input("latent", optional=True, lazy=True),
            io.Vae.Input("vae", optional=True, lazy=True),
            io.Image.Input(
                "guide_batch",
                optional=True,
                lazy=True,
                tooltip=(
                    "Video/IMAGE batch sampled evenly across its complete "
                    "frame range, once per batch_frame_indices entry."
                ),
            ),
            io.String.Input(
                "batch_frame_indices",
                default="",
                tooltip="Comma-separated zero-based output frames, e.g. 0, 22, 60, -1.",
            ),
        ]
        for lane in range(1, MAX_GUIDES + 1):
            inputs.extend(
                [
                    io.Image.Input(
                        f"guide_image_{lane}",
                        optional=True,
                        lazy=True,
                        tooltip="A single IMAGE (not an image batch).",
                    ),
                    io.Int.Input(
                        f"guide_frame_{lane}",
                        default=0,
                        min=-9999,
                        max=9999,
                        tooltip="Zero-based target frame; -1 is the final frame.",
                    ),
                ]
            )
        inputs.append(
            io.Boolean.Input(
                "bypass",
                default=False,
                label_on="BYPASS",
                label_off="GUIDE",
                tooltip=(
                    "Return conditioning unchanged without loading or "
                    "VAE-encoding any guide inputs."
                ),
            )
        )
        return io.Schema(
            node_id="SkebaMiniMaxH3MultiFrameGuideTest",
            display_name="SKEBA MiniMax H3 Multi-Frame Guide",
            category="Skeba AI Nodes - Reference/Experimental",
            description=(
                "Experimental native H3 keyframe injector. Adds up to eight "
                "independently positioned hard image guides; no guide audio."
            ),
            inputs=inputs,
            outputs=[
                io.Conditioning.Output(display_name="positive"),
                io.String.Output(display_name="status"),
            ],
        )

    @classmethod
    def check_lazy_status(cls, positive, batch_frame_indices="", bypass=False,
                          **kwargs):
        if bypass:
            return []

        connected_images = []
        if "guide_batch" in kwargs:
            connected_images.append("guide_batch")
        connected_images.extend(
            f"guide_image_{lane}"
            for lane in range(1, MAX_GUIDES + 1)
            if f"guide_image_{lane}" in kwargs
        )

        needed = []
        if kwargs.get("latent") is None:
            needed.append("latent")
        for name in connected_images:
            if kwargs.get(name) is None:
                needed.append(name)
        if connected_images and kwargs.get("vae") is None:
            needed.append("vae")
        return needed

    @classmethod
    def execute(
        cls,
        positive,
        batch_frame_indices="",
        guide_frame_1=0,
        guide_frame_2=0,
        guide_frame_3=0,
        guide_frame_4=0,
        guide_frame_5=0,
        guide_frame_6=0,
        guide_frame_7=0,
        guide_frame_8=0,
        bypass=False,
        latent=None,
        vae=None,
        guide_batch=None,
        guide_image_1=None,
        guide_image_2=None,
        guide_image_3=None,
        guide_image_4=None,
        guide_image_5=None,
        guide_image_6=None,
        guide_image_7=None,
        guide_image_8=None,
    ):
        if bypass:
            return io.NodeOutput(positive, "BYPASSED — no guide images evaluated")
        if latent is None:
            raise ValueError(
                "Multi-Frame H3 Guide: connect latent while GUIDE is active"
            )

        width, height, frame_count, video = _latent_geometry(latent)
        requested_batch_targets = _parse_frame_indices(batch_frame_indices)
        guides = []

        if requested_batch_targets and guide_batch is None:
            raise ValueError(
                "Multi-Frame H3 Guide: batch_frame_indices contains targets, "
                "but guide_batch is not connected"
            )
        if guide_batch is not None and not requested_batch_targets:
            raise ValueError(
                "Multi-Frame H3 Guide: guide_batch is connected; add at least "
                "one target to batch_frame_indices"
            )
        if guide_batch is not None:
            if guide_batch.ndim != 4 or guide_batch.shape[0] < 1:
                raise ValueError(
                    "Multi-Frame H3 Guide: guide_batch must contain one or more "
                    "IMAGE frames"
                )
            source_indices = torch.linspace(
                0,
                guide_batch.shape[0] - 1,
                steps=len(requested_batch_targets),
                device="cpu",
            ).round().to(torch.int64).tolist()
            for source_index, target in zip(
                source_indices, requested_batch_targets, strict=True
            ):
                guides.append(
                    {
                        "source": f"batch frame {source_index}",
                        "image": guide_batch[source_index:source_index + 1],
                        "requested": target,
                    }
                )

        lane_images = (
            guide_image_1,
            guide_image_2,
            guide_image_3,
            guide_image_4,
            guide_image_5,
            guide_image_6,
            guide_image_7,
            guide_image_8,
        )
        lane_targets = (
            guide_frame_1,
            guide_frame_2,
            guide_frame_3,
            guide_frame_4,
            guide_frame_5,
            guide_frame_6,
            guide_frame_7,
            guide_frame_8,
        )
        for lane, (image, target) in enumerate(
            zip(lane_images, lane_targets, strict=True), start=1
        ):
            if image is None:
                continue
            if image.ndim != 4 or image.shape[0] != 1:
                count = image.shape[0] if image.ndim >= 1 else "unknown"
                raise ValueError(
                    f"Multi-Frame H3 Guide: guide_image_{lane} must contain "
                    f"exactly one IMAGE frame; received {count}"
                )
            guides.append(
                {
                    "source": f"individual guide {lane}",
                    "image": image,
                    "requested": target,
                }
            )

        if not guides:
            raise ValueError(
                "Multi-Frame H3 Guide: connect guide_batch or at least one "
                "individual guide image"
            )
        if len(guides) > MAX_GUIDES:
            raise ValueError(
                f"Multi-Frame H3 Guide: {len(guides)} guides were requested; "
                f"the combined batch and individual limit is {MAX_GUIDES}"
            )
        if vae is None:
            raise ValueError(
                "Multi-Frame H3 Guide: connect the video VAE while GUIDE is active"
            )

        existing = list(positive[0][1].get("minimax_keyframes", []))
        occupied = {}
        for position, keyframe in enumerate(existing, start=1):
            index = keyframe.get("resolved_frame_index")
            if not isinstance(index, int):
                raise ValueError(
                    f"Multi-Frame H3 Guide: existing keyframe {position} has "
                    "no valid resolved_frame_index"
                )
            if index < 0 or index >= frame_count:
                raise ValueError(
                    f"Multi-Frame H3 Guide: existing keyframe {position} targets "
                    f"frame {index}, outside the output video's {frame_count} frames"
                )
            if index in occupied:
                raise ValueError(
                    f"Multi-Frame H3 Guide: existing keyframes {occupied[index]} "
                    f"and {position} both target frame {index}"
                )
            occupied[index] = f"existing keyframe {position}"

        for guide in guides:
            resolved = _resolve_frame_index(guide["requested"], frame_count)
            if resolved in occupied:
                raise ValueError(
                    f"Multi-Frame H3 Guide: target frame {resolved} from "
                    f"{guide['source']} conflicts with {occupied[resolved]}; "
                    "choose a different frame index"
                )
            occupied[resolved] = guide["source"]
            guide["resolved"] = resolved

        added_keyframes = []
        status_lines = []
        for guide in guides:
            frames = h3._resize(guide["image"], width, height, "center")
            latent_guide = vae.encode(frames)
            added_keyframes.append(
                {
                    "resolved_frame_index": guide["resolved"],
                    "latent": latent_guide,
                }
            )
            status_lines.append(
                f"{guide['source']} -> output frame {guide['resolved']} "
                f"(requested {guide['requested']})"
            )

        keyframes = sorted(
            existing + added_keyframes,
            key=lambda item: item["resolved_frame_index"],
        )
        positive = node_helpers.conditioning_set_values(
            positive, {"minimax_keyframes": keyframes}
        )

        tokens_per_guide = (video.shape[3] // 2) * (video.shape[4] // 2)
        estimated_tokens = tokens_per_guide * len(guides)
        status_lines.append(
            f"Added {len(guides)} guide(s); estimated {estimated_tokens:,} "
            "visual tokens per transformer step"
        )
        return io.NodeOutput(positive, "\n".join(status_lines))

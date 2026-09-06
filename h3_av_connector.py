"""Experimental start/end audio-video bridges for MiniMax H3."""

from __future__ import annotations

import math

import torch

import comfy.nested_tensor
import node_helpers
from comfy.ldm.minimax.model import FRAME_PER_TOKEN, FRAME_RESCALE
from comfy_api.latest import io
from comfy_extras import nodes_minimax_h3 as h3

try:
    import torchaudio
except ImportError:  # ComfyUI normally includes it; errors remain actionable.
    torchaudio = None


FPS = 24.0
BUNDLE_VERSION = 1
ConnectorBundle = io.Custom("SKEBA_H3_AV_CONNECTOR_BUNDLE")
SeamBundle = io.Custom("SKEBA_H3_AV_CONNECTOR_SEAM")
OVERLAP_OPTIONS = ["22", "39", "56", "5"]


def _latent_geometry(latent):
    try:
        samples = latent["samples"]
        tensors = samples.tensors
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError(
            "H3 AV Connector: connect a MiniMax H3 AV latent"
        ) from exc
    if (
        not getattr(samples, "is_nested", False)
        or len(tensors) != 2
        or tensors[0].ndim != 5
        or tensors[0].shape[1] != 24
        or tensors[1].ndim != 4
        or tensors[1].shape[1] != 32
    ):
        raise ValueError("H3 AV Connector: latent must be a MiniMax H3 AV latent")
    video = tensors[0]
    frame_count = sum(
        FRAME_PER_TOKEN[index % 5] for index in range(video.shape[2])
    )
    return (
        video.shape[4] * 16,
        video.shape[3] * 16,
        frame_count,
        int(tensors[1].shape[-1]),
        video,
        tensors[1],
    )


def _validate_images(images, name, needed):
    if not isinstance(images, torch.Tensor) or images.ndim != 4:
        raise ValueError(f"H3 AV Connector: {name} must be an IMAGE batch")
    if images.shape[0] < needed:
        raise ValueError(
            f"H3 AV Connector: {name} has {images.shape[0]} frames but the "
            f"selected overlap needs {needed}"
        )


def _normalise_waveform(audio, target_sr, name):
    try:
        waveform = audio["waveform"]
        sample_rate = int(audio["sample_rate"])
    except (KeyError, TypeError) as exc:
        raise ValueError(f"H3 AV Connector: {name} is not a valid AUDIO value") from exc
    if waveform.ndim == 2:
        waveform = waveform.unsqueeze(0)
    if waveform.ndim != 3 or waveform.shape[-1] < 1:
        raise ValueError(
            f"H3 AV Connector: {name} waveform must have shape [B, C, samples]"
        )
    waveform = waveform[:1]
    channels = waveform.shape[1]
    if channels == 1:
        waveform = waveform.repeat(1, 2, 1)
    elif channels > 2:
        waveform = waveform[:, :2]
    if sample_rate != target_sr:
        if torchaudio is None:
            raise ValueError(
                f"H3 AV Connector: {name} is {sample_rate} Hz but the audio "
                f"VAE needs {target_sr} Hz and torchaudio is unavailable"
            )
        waveform = torchaudio.functional.resample(
            waveform, sample_rate, target_sr
        )
    return waveform.contiguous()


def _encode_audio_window(audio_vae, audio, overlap, side, name):
    target_sr = int(getattr(audio_vae, "audio_sample_rate", 32000))
    waveform = _normalise_waveform(audio, target_sr, name)
    sample_count = int(round(overlap / FPS * target_sr))
    if waveform.shape[-1] < sample_count:
        raise ValueError(
            f"H3 AV Connector: {name} is {waveform.shape[-1] / target_sr:.3f}s "
            f"but a {overlap}-frame overlap needs {overlap / FPS:.3f}s"
        )
    window = (
        waveform[..., -sample_count:]
        if side == "start"
        else waveform[..., :sample_count]
    )
    latent = audio_vae.encode(window.movedim(1, -1))
    return latent, sample_count, target_sr


def _keyframe_span(keyframe):
    video_latent = keyframe.get("latent")
    if video_latent is not None:
        if getattr(video_latent, "ndim", 0) != 5:
            raise ValueError(
                "H3 AV Connector: an existing keyframe has an invalid video latent"
            )
        return sum(
            FRAME_PER_TOKEN[index % 5]
            for index in range(video_latent.shape[2])
        )
    audio_latent = keyframe.get("audio_latent")
    if audio_latent is not None:
        return max(1, int(math.ceil(audio_latent.shape[-1] / FRAME_RESCALE)))
    return 1


def _ranges_overlap(first, second):
    return first[0] <= second[1] and second[0] <= first[1]


class SkebaMiniMaxH3AVConnectorGuideTest(io.ComfyNode):
    """Prepare native H3 start/end guide clips and their matching audio."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="SkebaMiniMaxH3AVConnectorGuideTest",
            display_name="SKEBA MiniMax H3 AV Connector Guide",
            category="Skeba AI Nodes - Reference/Experimental",
            description=(
                "Guide a generated bridge from a source clip, toward a "
                "destination clip, or both. Inputs are decoded at 24 FPS."
            ),
            inputs=[
                io.Conditioning.Input("positive"),
                io.Latent.Input("latent", optional=True, lazy=True),
                io.Vae.Input("vae", optional=True, lazy=True),
                io.Vae.Input("audio_vae", optional=True, lazy=True),
                io.Combo.Input(
                    "start_overlap",
                    display_name="Starting Video Context Frames",
                    options=OVERLAP_OPTIONS,
                    default="22",
                    tooltip=(
                        "Frames and matching audio taken from the end of the "
                        "Starting Video. 22 = 0.92s, 39 = 1.63s, 56 = 2.33s."
                    ),
                ),
                io.Combo.Input(
                    "end_overlap",
                    display_name="Ending Video Context Frames",
                    options=OVERLAP_OPTIONS,
                    default="22",
                    tooltip=(
                        "Frames and matching audio taken from the beginning "
                        "of the Ending Video."
                    ),
                ),
                io.Boolean.Input(
                    "bypass",
                    default=False,
                    label_on="BYPASS",
                    label_off="CONNECT",
                    tooltip="Return conditioning unchanged without evaluating media or VAEs.",
                ),
                io.Boolean.Input(
                    "replace_existing_noise_mask",
                    display_name="Replace Existing Noise Mask",
                    default=False,
                    tooltip=(
                        "Allow this connector to replace a mask carried from an "
                        "earlier connector pass. Leave disabled when using an "
                        "independent inpaint mask."
                    ),
                ),
                io.Boolean.Input(
                    "preserve_upscaled_endpoints",
                    display_name="Preserve Upscaled Pass Endpoints",
                    default=False,
                    tooltip=(
                        "For a second render pass, pin the endpoint latents "
                        "already produced by the latent upscaler instead of "
                        "overwriting them with a separate VAE encode. This "
                        "automatically follows the upscaler's scale and avoids "
                        "a spatial jump when the overlap ends."
                    ),
                ),
                io.Image.Input(
                    "start_frames", display_name="Starting Video Frames",
                    optional=True, lazy=True,
                ),
                io.Audio.Input(
                    "start_audio", display_name="Starting Video Audio",
                    optional=True, lazy=True,
                ),
                io.Image.Input(
                    "end_frames", display_name="Ending Video Frames",
                    optional=True, lazy=True,
                ),
                io.Audio.Input(
                    "end_audio", display_name="Ending Video Audio",
                    optional=True, lazy=True,
                ),
            ],
            outputs=[
                io.Conditioning.Output(display_name="positive"),
                ConnectorBundle.Output(display_name="connector_bundle"),
                io.String.Output(display_name="status"),
                io.Latent.Output(display_name="Pinned Generation Latent"),
            ],
        )

    @classmethod
    def check_lazy_status(cls, positive, start_overlap="22", end_overlap="22",
                          bypass=False, **kwargs):
        if bypass:
            return ["latent"] if kwargs.get("latent") is None else []
        connected = [
            name for name in ("start_frames", "start_audio", "end_frames", "end_audio")
            if name in kwargs
        ]
        needed = []
        if kwargs.get("latent") is None:
            needed.append("latent")
        for name in connected:
            if kwargs.get(name) is None:
                needed.append(name)
        image_connected = any(name in connected for name in ("start_frames", "end_frames"))
        audio_connected = any(name in connected for name in ("start_audio", "end_audio"))
        if image_connected and kwargs.get("vae") is None:
            needed.append("vae")
        if audio_connected and kwargs.get("audio_vae") is None:
            needed.append("audio_vae")
        return needed

    @classmethod
    def execute(
        cls,
        positive,
        start_overlap="22",
        end_overlap="22",
        bypass=False,
        replace_existing_noise_mask=False,
        preserve_upscaled_endpoints=False,
        latent=None,
        vae=None,
        audio_vae=None,
        start_frames=None,
        start_audio=None,
        end_frames=None,
        end_audio=None,
    ):
        if bypass:
            if latent is None:
                raise ValueError(
                    "H3 AV Connector: connect latent so BYPASS can pass it through"
                )
            bundle = {
                "version": BUNDLE_VERSION,
                "bypass": True,
                "fps": FPS,
                "start": None,
                "end": None,
            }
            return io.NodeOutput(
                positive,
                bundle,
                "BYPASSED - guide media and VAEs were not evaluated",
                latent,
            )
        if latent is None:
            raise ValueError("H3 AV Connector: connect latent while CONNECT is active")
        (
            width,
            height,
            frame_count,
            target_audio_t,
            target_video,
            target_audio,
        ) = _latent_geometry(latent)
        replacing_noise_mask = latent.get("noise_mask") is not None
        if replacing_noise_mask and not replace_existing_noise_mask:
            raise ValueError(
                "H3 AV Connector: the input latent already has a noise_mask; "
                "remove the other latent-inpaint mask or enable Replace Existing "
                "Noise Mask when this is a deliberate second connector pass"
            )
        start_n, end_n = int(start_overlap), int(end_overlap)

        if start_audio is not None and start_frames is None:
            raise ValueError("H3 AV Connector: start_audio requires start_frames")
        if end_audio is not None and end_frames is None:
            raise ValueError("H3 AV Connector: end_audio requires end_frames")
        if start_frames is None and end_frames is None:
            raise ValueError(
                "H3 AV Connector: connect start_frames, end_frames, or both"
            )
        if vae is None:
            raise ValueError("H3 AV Connector: connect the video VAE")
        if (start_audio is not None or end_audio is not None) and audio_vae is None:
            raise ValueError("H3 AV Connector: connect the audio VAE for guide audio")

        requested = []
        if start_frames is not None:
            _validate_images(start_frames, "start_frames", start_n)
            requested.append(("start", 0, start_n))
        if end_frames is not None:
            _validate_images(end_frames, "end_frames", end_n)
            requested.append(("end", frame_count - end_n, end_n))
        for side, position, count in requested:
            if position < 0 or position + count > frame_count:
                raise ValueError(
                    f"H3 AV Connector: the {side} {count}-frame overlap does "
                    f"not fit in the output video's {frame_count} frames"
                )
        if len(requested) == 2 and _ranges_overlap(
            (requested[0][1], requested[0][1] + requested[0][2] - 1),
            (requested[1][1], requested[1][1] + requested[1][2] - 1),
        ):
            raise ValueError(
                "H3 AV Connector: start and end overlaps collide; use a longer output"
            )

        existing = list(positive[0][1].get("minimax_keyframes", []))
        occupied = []
        for number, keyframe in enumerate(existing, start=1):
            position = keyframe.get("resolved_frame_index")
            if not isinstance(position, int):
                raise ValueError(
                    f"H3 AV Connector: existing keyframe {number} has no valid frame index"
                )
            span = _keyframe_span(keyframe)
            region = (position, position + span - 1)
            if region[0] < 0 or region[1] >= frame_count:
                raise ValueError(
                    f"H3 AV Connector: existing keyframe {number} range "
                    f"{region[0]}-{region[1]} is outside {frame_count} frames"
                )
            occupied.append((region, number))
        for side, position, count in requested:
            region = (position, position + count - 1)
            for old_region, number in occupied:
                if _ranges_overlap(region, old_region):
                    raise ValueError(
                        f"H3 AV Connector: {side} range {region[0]}-{region[1]} "
                        f"collides with existing keyframe {number} range "
                        f"{old_region[0]}-{old_region[1]}"
                    )

        keyframes = list(existing)
        status = []
        if replacing_noise_mask:
            status.append(
                "Replaced the incoming first-pass noise mask with upscale endpoint masks"
            )
        pinned_video = target_video.clone()
        pinned_audio = target_audio.clone()
        video_mask = torch.ones_like(pinned_video)
        audio_mask = torch.ones_like(pinned_audio)
        bundle = {
            "version": BUNDLE_VERSION,
            "bypass": False,
            "fps": FPS,
            "frame_count": frame_count,
            "start": None,
            "end": None,
        }
        for side, position, count in requested:
            source_frames = start_frames if side == "start" else end_frames
            source_audio = start_audio if side == "start" else end_audio
            selected = (
                source_frames[-count:]
                if side == "start"
                else source_frames[:count]
            )
            resized = h3._resize(selected, width, height, "center")
            video_latent = vae.encode(resized)
            encoded_span = sum(
                FRAME_PER_TOKEN[index % 5]
                for index in range(video_latent.shape[2])
            )
            if encoded_span != count:
                raise RuntimeError(
                    f"H3 AV Connector: {count} {side} frames encoded to a "
                    f"latent covering {encoded_span} frames; the connected "
                    "video VAE is not using the expected H3 temporal grid"
                )
            if (
                video_latent.ndim != 5
                or video_latent.shape[0] != pinned_video.shape[0]
                or video_latent.shape[1] != pinned_video.shape[1]
                or video_latent.shape[3:] != pinned_video.shape[3:]
            ):
                raise ValueError(
                    f"H3 AV Connector: encoded {side} video latent shape "
                    f"{tuple(video_latent.shape)} does not match target "
                    f"{tuple(pinned_video.shape)}"
                )
            video_steps = int(video_latent.shape[2])
            video_slice = (
                slice(0, video_steps)
                if side == "start"
                else slice(pinned_video.shape[2] - video_steps, pinned_video.shape[2])
            )
            if not preserve_upscaled_endpoints:
                pinned_video[:, :, video_slice] = video_latent.to(
                    device=pinned_video.device, dtype=pinned_video.dtype
                )
            video_mask[:, :, video_slice] = 0
            keyframe = {
                "resolved_frame_index": position,
                "latent": video_latent,
            }
            audio_note = "silent"
            if source_audio is not None:
                audio_latent, samples, sample_rate = _encode_audio_window(
                    audio_vae, source_audio, count, side,
                    f"{side}_audio",
                )
                max_audio_t = int(math.floor(
                    target_audio_t - FRAME_RESCALE * position
                ))
                if max_audio_t < 1:
                    raise ValueError(
                        f"H3 AV Connector: {side} audio starts past the "
                        "target audio timeline"
                    )
                if audio_latent.shape[-1] > max_audio_t:
                    audio_latent = audio_latent[..., :max_audio_t].clone()
                if (
                    audio_latent.ndim != 4
                    or audio_latent.shape[:3] != pinned_audio.shape[:3]
                ):
                    raise ValueError(
                        f"H3 AV Connector: encoded {side} audio latent shape "
                        f"{tuple(audio_latent.shape)} does not match target "
                        f"{tuple(pinned_audio.shape)}"
                    )
                audio_steps = int(audio_latent.shape[-1])
                audio_slice = (
                    slice(0, audio_steps)
                    if side == "start"
                    else slice(pinned_audio.shape[-1] - audio_steps, pinned_audio.shape[-1])
                )
                if not preserve_upscaled_endpoints:
                    pinned_audio[..., audio_slice] = audio_latent.to(
                        device=pinned_audio.device, dtype=pinned_audio.dtype
                    )
                audio_mask[..., audio_slice] = 0
                keyframe["audio_latent"] = audio_latent
                audio_note = (
                    f"{samples} samples at {sample_rate} Hz -> "
                    f"{audio_latent.shape[-1]} latent steps"
                )
            keyframes.append(keyframe)
            bundle[side] = {
                "frames": source_frames,
                "audio": source_audio,
                "overlap": count,
            }
            status.append(
                f"{side}: {count} frames at {position}-{position + count - 1}; "
                f"audio {audio_note}"
            )

        keyframes.sort(key=lambda item: item["resolved_frame_index"])
        positive = node_helpers.conditioning_set_values(
            positive, {"minimax_keyframes": keyframes}
        )
        pinned_latent = latent.copy()
        pinned_latent["samples"] = comfy.nested_tensor.NestedTensor(
            (pinned_video, pinned_audio)
        )
        pinned_latent["noise_mask"] = comfy.nested_tensor.NestedTensor(
            (video_mask, audio_mask)
        )
        if preserve_upscaled_endpoints:
            status.append(
                "Pinned endpoint content was preserved from the upscaled input "
                "latent; guide media was used for conditioning only"
            )
        else:
            status.append("Endpoint AV latents were inserted from the guide media")
        status.append(
            "Endpoint ranges use zero-denoise masks; connect Pinned Generation "
            "Latent to the sampler"
        )
        status.append("Native H3 strength; use H3 Condition Strength for global control")
        return io.NodeOutput(positive, bundle, "\n".join(status), pinned_latent)


class SkebaH3AVConnectorFinalizeTest(io.ComfyNode):
    """Remove sacrificial guided overlaps from a decoded bridge."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="SkebaH3AVConnectorFinalizeTest",
            display_name="SKEBA H3 AV Connector Finalize",
            category="Skeba AI Nodes - Reference/Experimental",
            inputs=[
                io.Image.Input(
                    "generated_images", display_name="Generated Video Frames"
                ),
                ConnectorBundle.Input("connector_bundle"),
                io.Audio.Input(
                    "generated_audio", display_name="Generated Video Audio",
                    optional=True,
                ),
            ],
            outputs=[
                io.Image.Output(display_name="Generated Connector Video Frames"),
                io.Audio.Output(display_name="Generated Connector Video Audio"),
                SeamBundle.Output(display_name="seam_bundle"),
                io.String.Output(display_name="status"),
            ],
        )

    @classmethod
    def execute(cls, generated_images, connector_bundle, generated_audio=None):
        if connector_bundle.get("version") != BUNDLE_VERSION:
            raise ValueError("H3 AV Connector Finalize: incompatible connector bundle")
        start = connector_bundle.get("start")
        end = connector_bundle.get("end")
        head = int(start["overlap"]) if start else 0
        tail = int(end["overlap"]) if end else 0
        if connector_bundle.get("bypass"):
            head = tail = 0
        if generated_images.ndim != 4:
            raise ValueError("H3 AV Connector Finalize: expected an IMAGE batch")
        total = int(generated_images.shape[0])
        if total <= head + tail:
            raise ValueError(
                f"H3 AV Connector Finalize: {total} generated frames cannot "
                f"lose {head} start and {tail} end overlap frames"
            )
        stop = total - tail if tail else total
        bridge_images = generated_images[head:stop]

        bridge_audio = generated_audio
        audio_note = "no generated audio"
        if generated_audio is not None:
            waveform = generated_audio["waveform"]
            sample_rate = int(generated_audio["sample_rate"])
            if waveform.ndim == 2:
                waveform = waveform.unsqueeze(0)
            if waveform.ndim != 3:
                raise ValueError(
                    "H3 AV Connector Finalize: generated audio must be [B,C,samples]"
                )
            head_samples = int(round(head / FPS * sample_rate))
            tail_samples = int(round(tail / FPS * sample_rate))
            audio_stop = waveform.shape[-1] - tail_samples if tail_samples else waveform.shape[-1]
            if audio_stop <= head_samples:
                raise ValueError(
                    "H3 AV Connector Finalize: generated audio is too short for the overlaps"
                )
            trimmed = waveform[..., head_samples:audio_stop]
            wanted = int(round(bridge_images.shape[0] / FPS * sample_rate))
            shortfall = wanted - int(trimmed.shape[-1])
            padded_samples = 0
            if shortfall > 0:
                # H3 video is timed at 24 FPS while its audio latent runs at
                # 40 Hz. The audio VAE decoder can therefore finish a fraction
                # of one audio-latent step before the exact picture boundary.
                # Preserve A/V duration by extending the final sample only for
                # that bounded grid-rounding case; a larger deficit still
                # indicates genuinely incomplete generated audio.
                grid_tolerance = int(math.ceil(sample_rate / h3.AUDIO_LATENT_FPS))
                if shortfall > grid_tolerance:
                    raise ValueError(
                        f"H3 AV Connector Finalize: audio is {shortfall} samples "
                        f"shorter than the trimmed picture (grid tolerance is "
                        f"{grid_tolerance}); check that video and audio came "
                        "from the same sampler output"
                    )
                padding = trimmed[..., -1:].expand(
                    *trimmed.shape[:-1], shortfall
                )
                trimmed = torch.cat((trimmed, padding), dim=-1)
                padded_samples = shortfall
            trimmed = trimmed[..., :wanted].contiguous()
            bridge_audio = {"waveform": trimmed, "sample_rate": sample_rate}
            audio_note = f"{trimmed.shape[-1]} samples at {sample_rate} Hz"
            if padded_samples:
                audio_note += f" (edge-padded {padded_samples} for H3 grid alignment)"

        seam_bundle = dict(connector_bundle)
        seam_bundle["generated_total_frames"] = total
        seam_bundle["bridge_frames"] = int(bridge_images.shape[0])
        status = (
            f"Trimmed start {head} frame(s), end {tail} frame(s); "
            f"bridge {bridge_images.shape[0]} frames; {audio_note}"
        )
        return io.NodeOutput(bridge_images, bridge_audio, seam_bundle, status)


def _audio_value(audio, name):
    if audio is None:
        return None, None
    try:
        waveform = audio["waveform"]
        sample_rate = int(audio["sample_rate"])
    except (KeyError, TypeError) as exc:
        raise ValueError(f"H3 AV Connector Assemble: invalid {name}") from exc
    if waveform.ndim == 2:
        waveform = waveform.unsqueeze(0)
    if waveform.ndim != 3:
        raise ValueError(f"H3 AV Connector Assemble: {name} must be [B,C,samples]")
    return waveform[:1], sample_rate


def _resample_audio(waveform, old_sr, new_sr):
    if old_sr == new_sr:
        return waveform
    if torchaudio is None:
        raise ValueError("H3 AV Connector Assemble: torchaudio is needed to resample")
    return torchaudio.functional.resample(waveform, old_sr, new_sr)


def _match_channels(waveform, channels):
    current = waveform.shape[1]
    if current == channels:
        return waveform
    if current == 1 and channels == 2:
        return waveform.repeat(1, 2, 1)
    if current >= 2 and channels == 1:
        return waveform.mean(dim=1, keepdim=True)
    if current > channels:
        return waveform[:, :channels]
    repeats = math.ceil(channels / current)
    return waveform.repeat(1, repeats, 1)[:, :channels]


def _fit_audio(waveform, samples):
    if waveform.shape[-1] >= samples:
        return waveform[..., :samples].contiguous()
    return torch.nn.functional.pad(waveform, (0, samples - waveform.shape[-1]))


class SkebaH3AVConnectorAssembleTest(io.ComfyNode):
    """Optionally assemble endpoint clips around a finalized bridge."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="SkebaH3AVConnectorAssembleTest",
            display_name="SKEBA H3 AV Connector Assemble",
            category="Skeba AI Nodes - Reference/Experimental",
            inputs=[
                io.Image.Input(
                    "bridge_images", display_name="Generated Connector Video Frames"
                ),
                SeamBundle.Input("seam_bundle"),
                io.Audio.Input(
                    "bridge_audio", display_name="Generated Connector Audio",
                    optional=True,
                ),
                io.Float.Input(
                    "seam_ms", default=40.0, min=0.0, max=500.0, step=1.0,
                    tooltip="Smooth only the bridge edges; endpoint audio is not modified.",
                ),
                io.Combo.Input(
                    "endpoint_resize",
                    display_name="Endpoint Video Resize",
                    options=["center_crop", "stretch", "error"],
                    default="center_crop",
                    tooltip=(
                        "Match Starting/Ending Video frames to the generated "
                        "bridge. Center crop preserves proportions; stretch "
                        "fills the canvas; error retains strict validation."
                    ),
                ),
            ],
            outputs=[
                io.Image.Output(display_name="images"),
                io.Audio.Output(display_name="audio"),
                io.Float.Output(display_name="fps"),
                io.String.Output(display_name="status"),
            ],
        )

    @classmethod
    def execute(cls, bridge_images, seam_bundle, seam_ms=40.0,
                bridge_audio=None, endpoint_resize="center_crop"):
        if seam_bundle.get("version") != BUNDLE_VERSION:
            raise ValueError("H3 AV Connector Assemble: incompatible seam bundle")
        if endpoint_resize not in ("center_crop", "stretch", "error"):
            raise ValueError(
                f"H3 AV Connector Assemble: unknown endpoint resize mode "
                f"{endpoint_resize!r}"
            )
        start = seam_bundle.get("start")
        end = seam_bundle.get("end")
        image_segments = []
        labels = []
        if start:
            image_segments.append(start["frames"])
            labels.append("source")
        image_segments.append(bridge_images)
        labels.append("bridge")
        if end:
            image_segments.append(end["frames"])
            labels.append("destination")
        if bridge_images.ndim != 4:
            raise ValueError("H3 AV Connector Assemble: bridge must be an IMAGE batch")
        shape = tuple(bridge_images.shape[1:])
        normalized_segments = []
        resized_labels = []
        for label, images in zip(labels, image_segments, strict=True):
            if images.ndim != 4:
                raise ValueError(
                    f"H3 AV Connector Assemble: {label} must be an IMAGE batch"
                )
            if tuple(images.shape[1:]) != shape:
                if label == "bridge" or endpoint_resize == "error":
                    raise ValueError(
                        f"H3 AV Connector Assemble: {label} image dimensions "
                        f"{tuple(images.shape[1:])} do not match bridge {shape}"
                    )
                crop = "center" if endpoint_resize == "center_crop" else "disabled"
                images = h3._resize(images, shape[1], shape[0], crop)
                resized_labels.append(label)
            normalized_segments.append(images)
        image_segments = normalized_segments
        images = torch.cat(image_segments, dim=0)
        resize_note = (
            f"; resized {', '.join(resized_labels)} via {endpoint_resize}"
            if resized_labels else ""
        )

        raw_audios = []
        if start:
            raw_audios.append(start.get("audio"))
        raw_audios.append(bridge_audio)
        if end:
            raw_audios.append(end.get("audio"))
        parsed = [_audio_value(audio, label) for audio, label in zip(raw_audios, labels, strict=True)]
        present = [(waveform, rate) for waveform, rate in parsed if waveform is not None]
        if not present:
            return io.NodeOutput(
                images, None, FPS,
                f"Assembled {' + '.join(labels)}: {images.shape[0]} frames, "
                f"silent{resize_note}",
            )
        bridge_index = labels.index("bridge")
        bridge_wave, bridge_rate = parsed[bridge_index]
        target_sr = bridge_rate if bridge_wave is not None else present[0][1]
        target_channels = (
            bridge_wave.shape[1]
            if bridge_wave is not None
            else min(2, max(waveform.shape[1] for waveform, _ in present))
        )

        cumulative_frames = 0
        sample_cursor = 0
        fitted = []
        for images_part, parsed_audio in zip(image_segments, parsed, strict=True):
            cumulative_frames += int(images_part.shape[0])
            next_cursor = int(round(cumulative_frames / FPS * target_sr))
            wanted = next_cursor - sample_cursor
            waveform, sample_rate = parsed_audio
            if waveform is None:
                waveform = torch.zeros(
                    (1, target_channels, wanted),
                    dtype=present[0][0].dtype,
                    device=present[0][0].device,
                )
            else:
                if sample_rate != target_sr:
                    waveform = _resample_audio(waveform, sample_rate, target_sr)
                waveform = _match_channels(waveform, target_channels)
                waveform = _fit_audio(waveform, wanted)
            fitted.append(waveform)
            sample_cursor = next_cursor

        bridge = fitted[bridge_index].clone()
        smooth = min(int(round(float(seam_ms) / 1000.0 * target_sr)), bridge.shape[-1])
        if smooth > 1 and start and fitted[bridge_index - 1].shape[-1] > 0:
            fade = torch.linspace(
                0.0, 1.0, smooth, dtype=bridge.dtype, device=bridge.device
            ).view(1, 1, -1)
            boundary = fitted[bridge_index - 1][..., -1:].expand(-1, -1, smooth)
            bridge[..., :smooth] = boundary * (1.0 - fade) + bridge[..., :smooth] * fade
        if smooth > 1 and end and fitted[bridge_index + 1].shape[-1] > 0:
            fade = torch.linspace(
                1.0, 0.0, smooth, dtype=bridge.dtype, device=bridge.device
            ).view(1, 1, -1)
            boundary = fitted[bridge_index + 1][..., :1].expand(-1, -1, smooth)
            bridge[..., -smooth:] = bridge[..., -smooth:] * fade + boundary * (1.0 - fade)
        fitted[bridge_index] = bridge
        waveform = torch.cat(fitted, dim=-1)
        audio = {"waveform": waveform, "sample_rate": target_sr}
        status = (
            f"Assembled {' + '.join(labels)}: {images.shape[0]} frames, "
            f"{waveform.shape[-1]} samples at {target_sr} Hz; "
            f"bridge-edge smoothing {float(seam_ms):.1f} ms"
            + resize_note
        )
        return io.NodeOutput(images, audio, FPS, status)

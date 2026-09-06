import math
import logging
from collections import OrderedDict

import torch
import node_helpers
import nodes
import comfy.model_management
from comfy_api.latest import io
from comfy_extras import nodes_minimax_h3 as h3
from comfy.text_encoders.minimax import MiniMaxQwen3VL

from .reference_cache import (
    CACHE_SCHEMA_VERSION,
    ReferenceTensorCache,
    clip_fingerprint,
    fingerprint,
    hash_audio,
    hash_tensor,
    source_fingerprint,
    vae_fingerprint,
)


ReferenceBundle = io.Custom("SKEBA_H3_REFERENCE_BUNDLE")
_CACHE = ReferenceTensorCache()
_IMAGE_PROCESSING_VERSION = 1
_AUDIO_PROCESSING_VERSION = 1
_VIDEO_PROCESSING_VERSION = 1
_VIDEO_AUDIO_PROCESSING_VERSION = 1
_QWEN_PROCESSING_VERSION = 1
_CACHED_VISUAL_MARKER = "skeba_minimax_qwen_visual_v1"
_LOG = logging.getLogger(__name__)


def _h3_latent_geometry(latent):
    """Return the pixel canvas and frame count of a MiniMax H3 AV latent."""
    try:
        samples = latent["samples"]
        tensors = samples.tensors
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError(
            "Cached Reference + First/Last Frame: target_latent must be a "
            "MiniMax H3 AV latent"
        ) from error
    if (
        not getattr(samples, "is_nested", False)
        or len(tensors) != 2
        or tensors[0].ndim != 5
        or tensors[0].shape[1] != 24
        or tensors[1].ndim != 4
        or tensors[1].shape[1] != 32
    ):
        raise ValueError(
            "Cached Reference + First/Last Frame: target_latent must be a "
            "MiniMax H3 AV latent"
        )
    video = tensors[0]
    frame_count = sum(
        h3.FRAME_PER_TOKEN[index % 5] for index in range(video.shape[2])
    )
    return int(video.shape[4] * 16), int(video.shape[3] * 16), frame_count


def _load_image_source(path):
    from .h3_tag_references import load_image
    return load_image(path)


def _load_audio_source(path):
    from .h3_tag_references import load_audio
    return load_audio(path)


def _load_video_source(path, fps, max_side):
    from .h3_tag_references import load_video
    return load_video(path, fps, max_side)


def _install_qwen_visual_cache_bridge():
    if getattr(MiniMaxQwen3VL, "_skeba_visual_cache_bridge", False):
        return
    original = MiniMaxQwen3VL.preprocess_embed

    def preprocess_embed(self, embed, device):
        payload = embed.get("data") if embed.get("type") == "image" else None
        if isinstance(payload, dict) and payload.get(_CACHED_VISUAL_MARKER):
            merged = payload["merged"].to(device=device)
            grid = payload["grid"].to(device=device)
            deepstack = [tensor.to(device=device) for tensor in payload["deepstack"]]
            return merged, {"grid": grid, "deepstack": deepstack}
        return original(self, embed, device)

    MiniMaxQwen3VL.preprocess_embed = preprocess_embed
    MiniMaxQwen3VL._skeba_visual_cache_bridge = True


_install_qwen_visual_cache_bridge()


class _CachedVideoVisualBlocks:
    def __init__(self, blocks):
        self.blocks = blocks
        self.shape = (len(blocks) * 2,)

    def __getitem__(self, item):
        if not isinstance(item, slice) or item.step not in (None, 1):
            raise TypeError("cached Qwen video blocks only support contiguous slices")
        start = 0 if item.start is None else item.start
        stop = self.shape[0] if item.stop is None else item.stop
        if start % 2 or stop != start + 2:
            raise IndexError("cached Qwen video blocks must be requested in frame pairs")
        return self.blocks[start // 2]


def _encode_qwen_visual(clip, image, video_block=False):
    clip.load_model()
    device = clip.patcher.load_device
    stage_model = clip.cond_stage_model
    inner = getattr(stage_model, stage_model.clip)
    transformer = inner.transformer
    with comfy.model_management.cuda_device_context(device):
        merged, extra = transformer.preprocess_embed(
            {
                "type": "image",
                "data": image,
                "minimax_video_block": bool(video_block),
            },
            device,
        )
    if not isinstance(extra, dict):
        raise ValueError("MiniMax H3 Qwen encoder did not return visual metadata")
    return {
        "merged": merged,
        "grid": extra["grid"],
        "deepstack": extra["deepstack"],
    }


def _summarize_block_states(states):
    if not states:
        return "NO BLOCKS"
    counts = OrderedDict()
    for state in states:
        counts[state] = counts.get(state, 0) + 1
    details = ", ".join(f"{state} {count}" for state, count in counts.items())
    return f"{details} ({len(states)} blocks)"


def _compiled_key(kind, source_hash, **settings):
    return fingerprint({
        "schema": CACHE_SCHEMA_VERSION,
        "compiled_version": 1,
        "kind": kind,
        "source_sha256": source_hash,
        **settings,
    })


def _pack_visual(tensors, prefix, visual):
    tensors[f"{prefix}_merged"] = visual["merged"]
    tensors[f"{prefix}_grid"] = visual["grid"]
    for index, tensor in enumerate(visual["deepstack"]):
        tensors[f"{prefix}_deepstack_{index}"] = tensor
    return len(visual["deepstack"])


def _unpack_visual(tensors, prefix, deepstack_count):
    return {
        _CACHED_VISUAL_MARKER: True,
        "merged": tensors[f"{prefix}_merged"],
        "grid": tensors[f"{prefix}_grid"],
        "deepstack": [
            tensors[f"{prefix}_deepstack_{index}"]
            for index in range(int(deepstack_count))
        ],
    }


def _entry_source_hash(entry):
    if not entry or not entry.get("source_path"):
        return None
    try:
        return source_fingerprint(entry, lambda: None)
    except (OSError, TypeError):
        return None


class SkebaCachedMiniMaxH3ReferenceToVideo(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="SkebaCachedMiniMaxH3ReferenceToVideo",
            display_name="SKEBA MiniMax H3 Cached Reference to Video",
            category="Skeba AI Nodes - Reference",
            description="MiniMax H3 reference conditioning with persistent image, video, audio, and Qwen visual caches.",
            inputs=[
                io.Clip.Input("clip"),
                io.Vae.Input("vae"),
                io.Vae.Input("audio_vae"),
                io.String.Input("prompt", multiline=True, dynamic_prompts=True),
                io.Int.Input("width", default=1344, min=32, max=nodes.MAX_RESOLUTION, step=32),
                io.Int.Input("height", default=768, min=32, max=nodes.MAX_RESOLUTION, step=32),
                io.Int.Input("length", default=124, min=5, max=3600, step=17),
                io.Combo.Input("ref_image_size", options=["match", "max"], default="match"),
                io.Combo.Input("cache_mode", options=["auto", "disabled", "rebuild"], default="auto",
                               tooltip="Auto reuses valid caches. Rebuild replaces them. Disabled always encodes references."),
                io.Autogrow.Input("ref_images", optional=True,
                    template=io.Autogrow.TemplatePrefix(
                        input=io.Image.Input("ref_image"), prefix="ref_image_", min=0, max=9)),
                io.Autogrow.Input("ref_videos", optional=True,
                    template=io.Autogrow.TemplatePrefix(
                        input=io.Image.Input("ref_video"), prefix="ref_video_", min=0, max=3)),
                io.Autogrow.Input("ref_video_audios", optional=True,
                    template=io.Autogrow.TemplatePrefix(
                        input=io.Audio.Input("ref_video_audio"), prefix="ref_video_audio_", min=0, max=3)),
                io.Autogrow.Input("ref_audios", optional=True,
                    template=io.Autogrow.TemplatePrefix(
                        input=io.Audio.Input("ref_audio"), prefix="ref_audio_", min=0, max=3)),
                ReferenceBundle.Input("reference_bundle", optional=True,
                                      tooltip="Connect H3 Tagged Reference Prompt for per-character cache identity."),
            ],
            outputs=[
                io.Conditioning.Output(display_name="positive"),
                io.Latent.Output(),
                io.String.Output(display_name="cache_status"),
            ],
        )

    @classmethod
    def execute(cls, clip, vae, audio_vae, prompt, width, height, length,
                ref_image_size="match", cache_mode="auto", reference_bundle=None,
                ref_images=None, ref_videos=None, ref_video_audios=None,
                ref_audios=None, first_frame=None, last_frame=None,
                target_latent=None):
        if target_latent is None:
            latent, frame_count = h3._empty_av_latent(width, height, length)
        else:
            width, height, frame_count = _h3_latent_geometry(target_latent)
            latent = target_latent
        bundle = reference_bundle if isinstance(reference_bundle, dict) else {}
        image_entries = bundle.get("images", [])
        audio_entries = bundle.get("audios", [])
        video_entries = bundle.get("videos", [])
        statuses = OrderedDict()

        def report(tag, modality, state):
            statuses.setdefault(tag, []).append(f"{modality}: {state}")

        video_vae_id = vae_fingerprint(vae) if cache_mode != "disabled" else None
        audio_vae_id = vae_fingerprint(audio_vae) if cache_mode != "disabled" else None
        qwen_id = clip_fingerprint(clip) if cache_mode != "disabled" else None
        ref_items = []
        ref_blocks = []

        image_values = list((ref_images or {}).values())
        image_count = max(len(image_entries), len(image_values))
        for image_index in range(image_count):
            img = image_values[image_index] if image_index < len(image_values) else None
            entry = image_entries[image_index] if image_index < len(image_entries) else None
            tag = (entry or {}).get("tag") or f"Picture {image_index + 1}"
            source_hash = (_entry_source_hash(entry)
                           if cache_mode != "disabled" else None)
            compiled_key = None
            if source_hash and video_vae_id and qwen_id:
                compiled_key = _compiled_key(
                    "image", source_hash,
                    video_vae=video_vae_id,
                    qwen=qwen_id,
                    ref_image_size=ref_image_size,
                    width=int(width),
                    height=int(height),
                    image_processing=_IMAGE_PROCESSING_VERSION,
                    qwen_processing=_QWEN_PROCESSING_VERSION,
                )
                if cache_mode != "rebuild":
                    compiled = _CACHE.load_compiled(entry, compiled_key, "image")
                    if compiled is not None:
                        tensors, packed = compiled
                        qwen_data = _unpack_visual(
                            tensors, "qwen", packed["qwen_deepstack_count"])
                        ref_items.append({"type": "image", "data": qwen_data})
                        ref_blocks.append({
                            "kind": "image",
                            "latent_h": int(packed["latent_h"]),
                            "latent_w": int(packed["latent_w"]),
                            "latent": tensors["video_latent"],
                        })
                        report(tag, "Image", "HIT (lazy bundle)")
                        report(tag, "Qwen", "HIT (lazy bundle)")
                        continue
            if img is None and entry and entry.get("source_path"):
                img = _load_image_source(entry["source_path"])
                report(tag, "Source Media", "LOADED (cache miss)")
            if img is None:
                continue
            h, w = img.shape[1], img.shape[2]
            if ref_image_size == "match":
                scale = min(1.0, math.sqrt((width * height) / (w * h)))
            else:
                scale = min(1.0, h3.REF_IMAGE_SHORT_EDGE / min(w, h))
            tw = max(h3.CANVAS_MULTIPLE, round(w * scale / h3.CANVAS_MULTIPLE) * h3.CANVAS_MULTIPLE)
            th = max(h3.CANVAS_MULTIPLE, round(h * scale / h3.CANVAS_MULTIPLE) * h3.CANVAS_MULTIPLE)
            resized = h3._resize(img[:1], tw, th, "disabled")
            if source_hash is None and (video_vae_id is not None or qwen_id is not None):
                source_hash = source_fingerprint(entry, lambda: hash_tensor(img[:1]))

            if video_vae_id is None:
                z = vae.encode(resized)
                reason = "DISABLED" if cache_mode == "disabled" else "DISABLED (VAE identity unavailable)"
                report(tag, "Image", reason)
            else:
                metadata = {
                    "source_sha256": source_hash,
                    "model": video_vae_id,
                    "ref_image_size": ref_image_size,
                    "width": int(width),
                    "height": int(height),
                    "resized_width": int(tw),
                    "resized_height": int(th),
                    "latent_h": int(th // 16),
                    "latent_w": int(tw // 16),
                    "processing_version": _IMAGE_PROCESSING_VERSION,
                }
                key = fingerprint({"schema": CACHE_SCHEMA_VERSION, "modality": "image", **metadata})
                z, _, state = _CACHE.get_or_create(
                    "image", entry, key, metadata, lambda: vae.encode(resized), cache_mode)
                report(tag, "Image", state)

            qwen_data = resized
            if qwen_id is None:
                reason = "DISABLED" if cache_mode == "disabled" else "DISABLED (CLIP identity unavailable)"
                report(tag, "Qwen", reason)
            else:
                qwen_metadata = {
                    "source_sha256": source_hash,
                    "model": qwen_id,
                    "ref_image_size": ref_image_size,
                    "resized_width": int(tw),
                    "resized_height": int(th),
                    "processing_version": _QWEN_PROCESSING_VERSION,
                }
                qwen_key = fingerprint({
                    "schema": CACHE_SCHEMA_VERSION,
                    "modality": "qwen",
                    **qwen_metadata,
                })
                try:
                    visual, _, state = _CACHE.get_or_create_visual(
                        entry,
                        qwen_key,
                        qwen_metadata,
                        lambda: _encode_qwen_visual(clip, resized),
                        cache_mode,
                    )
                    qwen_data = {_CACHED_VISUAL_MARKER: True, **visual}
                    report(tag, "Qwen", state)
                except (AttributeError, KeyError, TypeError, ValueError) as error:
                    _LOG.warning("H3 Qwen cache fell back to native processing: %s", error)
                    report(tag, "Qwen", "FALLBACK (native processing)")

            ref_items.append({"type": "image", "data": qwen_data})
            ref_blocks.append({
                "kind": "image", "latent_h": th // 16, "latent_w": tw // 16,
                "latent": z,
            })
            if (compiled_key and isinstance(qwen_data, dict)
                    and qwen_data.get(_CACHED_VISUAL_MARKER)):
                packed_tensors = {"video_latent": z}
                deepstack_count = _pack_visual(
                    packed_tensors, "qwen", qwen_data)
                try:
                    _CACHE.save_compiled(
                        entry, compiled_key, "image", packed_tensors,
                        {
                            "tag": tag,
                            "latent_h": int(th // 16),
                            "latent_w": int(tw // 16),
                            "qwen_deepstack_count": deepstack_count,
                        },
                    )
                    report(tag, "Lazy Bundle", "CREATED")
                except (OSError, ValueError) as error:
                    _LOG.warning("H3 image lazy bundle could not be saved: %s", error)

        ref_video_audios = ref_video_audios or {}
        video_items = list((ref_videos or {}).items())
        video_count = max(len(video_entries), len(video_items))
        for video_index in range(video_count):
            if video_index < len(video_items):
                name, video_frames = video_items[video_index]
            else:
                name, video_frames = f"ref_video_{video_index}", None
            entry = video_entries[video_index] if video_index < len(video_entries) else None
            tag = (entry or {}).get("tag") or f"Video {video_index + 1}"
            soundtrack = ref_video_audios.get("ref_video_audio_" + name.rsplit("_", 1)[-1])
            has_soundtrack = bool((entry or {}).get("has_audio") or soundtrack is not None)
            source_hash = (_entry_source_hash(entry)
                           if cache_mode != "disabled" else None)
            compiled_key = None
            if (source_hash and video_vae_id and qwen_id
                    and (not has_soundtrack or audio_vae_id)):
                compiled_key = _compiled_key(
                    "video", source_hash,
                    video_vae=video_vae_id,
                    audio_vae=audio_vae_id if has_soundtrack else None,
                    qwen=qwen_id,
                    forced_fps=float(bundle.get("video_fps", h3.FPS)),
                    loader_max_side=int(bundle.get("video_max_side", 0)),
                    render_frame_limit=int(frame_count),
                    video_processing=_VIDEO_PROCESSING_VERSION,
                    audio_processing=_VIDEO_AUDIO_PROCESSING_VERSION,
                    qwen_processing=_QWEN_PROCESSING_VERSION,
                )
                if cache_mode != "rebuild":
                    compiled = _CACHE.load_compiled(entry, compiled_key, "video")
                    if compiled is not None:
                        tensors, packed = compiled
                        blocks = [
                            _unpack_visual(
                                tensors,
                                f"qwen_{block_index}",
                                packed["qwen_deepstack_counts"][block_index],
                            )
                            for block_index in range(int(packed["qwen_block_count"]))
                        ]
                        qwen_data = _CachedVideoVisualBlocks(blocks)
                        timestamps = [float(value) for value in packed["timestamps"]]
                        audio_latent = tensors.get("audio_latent")
                        ref_audio_t = int(packed.get("ref_audio_t", 0))
                        if audio_latent is not None:
                            ref_items.append({"type": "audio"})
                        ref_items.append({
                            "type": "video",
                            "data": qwen_data,
                            "timestamps": timestamps,
                        })
                        ref_blocks.append({
                            "kind": "video_audio" if ref_audio_t else "video",
                            "latent_t": int(tensors["video_latent"].shape[2]),
                            "latent_h": int(packed["latent_h"]),
                            "latent_w": int(packed["latent_w"]),
                            "ref_audio_t": ref_audio_t,
                            "latent": tensors["video_latent"],
                            "audio_latent": audio_latent,
                        })
                        report(tag, "Video", "HIT (lazy bundle)")
                        if ref_audio_t:
                            report(tag, "Soundtrack", "HIT (lazy bundle)")
                        report(
                            tag,
                            "Qwen Video",
                            f"HIT {len(blocks)} ({len(blocks)} blocks) (lazy bundle)",
                        )
                        continue
            if video_frames is None and entry and entry.get("source_path"):
                video_frames, loaded_audio = _load_video_source(
                    entry["source_path"],
                    float(bundle.get("video_fps", h3.FPS)),
                    int(bundle.get("video_max_side", 0)),
                )
                if soundtrack is None and has_soundtrack:
                    soundtrack = loaded_audio
                report(tag, "Source Media", "LOADED (cache miss)")
            if video_frames is None:
                continue
            vh, vw = video_frames.shape[1], video_frames.shape[2]
            cw, ch = h3.adapt_canvas(vw, vh)
            if vw * vh < cw * ch:
                cw = max(h3.CANVAS_MULTIPLE, round(vw / h3.CANVAS_MULTIPLE) * h3.CANVAS_MULTIPLE)
                ch = max(h3.CANVAS_MULTIPLE, round(vh / h3.CANVAS_MULTIPLE) * h3.CANVAS_MULTIPLE)
            frames = h3._resize(video_frames, cw, ch, "disabled")
            if frames.shape[0] > frame_count:
                frames = frames[:frame_count]
            n = frames.shape[0]
            if n < 5:
                raise ValueError("MiniMax H3 reference videos need at least 5 frames (~0.2s at 24 fps)")
            while n % 17 != 5:
                n -= 1
            frames = frames[:n]
            if source_hash is None and (
                    video_vae_id is not None or audio_vae_id is not None
                    or qwen_id is not None):
                source_hash = source_fingerprint(entry, lambda: hash_tensor(video_frames))

            if video_vae_id is None:
                z = vae.encode(frames)
                reason = "DISABLED" if cache_mode == "disabled" else "DISABLED (VAE identity unavailable)"
                report(tag, "Video", reason)
            else:
                video_metadata = {
                    "source_sha256": source_hash,
                    "model": video_vae_id,
                    "forced_fps": float(bundle.get("video_fps", h3.FPS)),
                    "loader_max_side": int(bundle.get("video_max_side", 0)),
                    "input_frames": int(n),
                    "canvas_width": int(cw),
                    "canvas_height": int(ch),
                    "latent_h": int(ch // 16),
                    "latent_w": int(cw // 16),
                    "processing_version": _VIDEO_PROCESSING_VERSION,
                }
                video_key = fingerprint({
                    "schema": CACHE_SCHEMA_VERSION,
                    "modality": "video",
                    **video_metadata,
                })
                z, _, state = _CACHE.get_or_create(
                    "video", entry, video_key, video_metadata,
                    lambda: vae.encode(frames), cache_mode)
                report(tag, "Video", state)

            audio_latent, ref_audio_t = (None, 0)
            if soundtrack is not None:
                if audio_vae_id is None:
                    audio_latent, ref_audio_t = h3._encode_ref_audio(audio_vae, soundtrack)
                    reason = "DISABLED" if cache_mode == "disabled" else "DISABLED (VAE identity unavailable)"
                    report(tag, "Soundtrack", reason)
                else:
                    soundtrack_metadata = {
                        "source_sha256": source_hash,
                        "model": audio_vae_id,
                        "source_sample_rate": int(soundtrack["sample_rate"]),
                        "audio_sample_rate": int(getattr(audio_vae, "audio_sample_rate", 32000)),
                        "processing_version": _VIDEO_AUDIO_PROCESSING_VERSION,
                    }

                    def encode_soundtrack():
                        encoded, _ = h3._encode_ref_audio(audio_vae, soundtrack)
                        return encoded

                    soundtrack_key = fingerprint({
                        "schema": CACHE_SCHEMA_VERSION,
                        "modality": "video_soundtrack",
                        **soundtrack_metadata,
                    })
                    audio_latent, _, state = _CACHE.get_or_create(
                        "audio", entry, soundtrack_key, soundtrack_metadata,
                        encode_soundtrack, cache_mode)
                    ref_audio_t = audio_latent.shape[-1]
                    report(tag, "Soundtrack", state)
                ref_items.append({"type": "audio"})

            qwen_fps = float(h3.FPS)
            sample_step = max(1, int(round(qwen_fps / 2.0)))
            sample_idx = list(range(0, frames.shape[0], sample_step))
            qwen_frames = frames[sample_idx]
            timestamps = [i / qwen_fps for i in sample_idx]
            qwen_data = qwen_frames
            if qwen_id is None:
                reason = "DISABLED" if cache_mode == "disabled" else "DISABLED (CLIP identity unavailable)"
                report(tag, "Qwen Video", reason)
            else:
                if qwen_frames.shape[0] % 2 == 1:
                    qwen_frames = torch.cat([qwen_frames, qwen_frames[-1:]], dim=0)
                    timestamps.append(timestamps[-1])
                blocks = []
                states = []
                try:
                    for block_index in range(0, qwen_frames.shape[0], 2):
                        pair = qwen_frames[block_index:block_index + 2]
                        qwen_metadata = {
                            "source_sha256": source_hash,
                            "model": qwen_id,
                            "forced_fps": float(bundle.get("video_fps", h3.FPS)),
                            "loader_max_side": int(bundle.get("video_max_side", 0)),
                            "canvas_width": int(cw),
                            "canvas_height": int(ch),
                            "input_frames": int(n),
                            "sample_step": int(sample_step),
                            "block_index": int(block_index // 2),
                            "processing_version": _QWEN_PROCESSING_VERSION,
                        }
                        qwen_key = fingerprint({
                            "schema": CACHE_SCHEMA_VERSION,
                            "modality": "qwen_video",
                            **qwen_metadata,
                        })
                        visual, _, state = _CACHE.get_or_create_visual(
                            entry,
                            qwen_key,
                            qwen_metadata,
                            lambda pair=pair: _encode_qwen_visual(
                                clip, pair, video_block=True),
                            cache_mode,
                        )
                        blocks.append({_CACHED_VISUAL_MARKER: True, **visual})
                        states.append(state)
                    qwen_data = _CachedVideoVisualBlocks(blocks)
                    report(tag, "Qwen Video", _summarize_block_states(states))
                except (AttributeError, KeyError, TypeError, ValueError) as error:
                    _LOG.warning("H3 Qwen video cache fell back to native processing: %s", error)
                    qwen_data = frames[sample_idx]
                    timestamps = [i / qwen_fps for i in sample_idx]
                    report(tag, "Qwen Video", "FALLBACK (native processing)")

            ref_items.append({"type": "video", "data": qwen_data,
                              "timestamps": timestamps})
            ref_blocks.append({"kind": "video_audio" if ref_audio_t else "video",
                               "latent_t": z.shape[2], "latent_h": ch // 16, "latent_w": cw // 16,
                               "ref_audio_t": ref_audio_t, "latent": z, "audio_latent": audio_latent})
            if compiled_key and isinstance(qwen_data, _CachedVideoVisualBlocks):
                packed_tensors = {"video_latent": z}
                if audio_latent is not None:
                    packed_tensors["audio_latent"] = audio_latent
                deepstack_counts = []
                for block_index, visual in enumerate(qwen_data.blocks):
                    deepstack_counts.append(_pack_visual(
                        packed_tensors, f"qwen_{block_index}", visual))
                try:
                    _CACHE.save_compiled(
                        entry, compiled_key, "video", packed_tensors,
                        {
                            "tag": tag,
                            "latent_h": int(ch // 16),
                            "latent_w": int(cw // 16),
                            "input_frames": int(n),
                            "ref_audio_t": int(ref_audio_t),
                            "timestamps": [float(value) for value in timestamps],
                            "qwen_block_count": len(qwen_data.blocks),
                            "qwen_deepstack_counts": deepstack_counts,
                        },
                    )
                    report(tag, "Lazy Bundle", "CREATED")
                except (OSError, ValueError) as error:
                    _LOG.warning("H3 video lazy bundle could not be saved: %s", error)

        audio_values = list((ref_audios or {}).values())
        audio_count = max(len(audio_entries), len(audio_values))
        for audio_index in range(audio_count):
            audio = audio_values[audio_index] if audio_index < len(audio_values) else None
            entry = audio_entries[audio_index] if audio_index < len(audio_entries) else None
            tag = (entry or {}).get("tag") or f"Audio {audio_index + 1}"
            vae_sr = int(getattr(audio_vae, "audio_sample_rate", 32000))
            source_hash = (_entry_source_hash(entry)
                           if cache_mode != "disabled" else None)
            compiled_key = None
            if source_hash and audio_vae_id:
                compiled_key = _compiled_key(
                    "audio", source_hash,
                    audio_vae=audio_vae_id,
                    audio_processing=_AUDIO_PROCESSING_VERSION,
                )
                if cache_mode != "rebuild":
                    compiled = _CACHE.load_compiled(entry, compiled_key, "audio")
                    if compiled is not None:
                        tensors, packed = compiled
                        audio_latent = tensors["audio_latent"]
                        ref_audio_t = int(packed["ref_audio_t"])
                        ref_items.append({"type": "audio"})
                        ref_blocks.append({
                            "kind": "audio",
                            "ref_audio_t": ref_audio_t,
                            "audio_latent": audio_latent,
                        })
                        report(tag, "Audio", "HIT (lazy bundle)")
                        continue
            if audio is None and entry and entry.get("source_path"):
                # The audio loader can demux a video container without decoding
                # its image stream, which keeps voice-only video tags inexpensive.
                audio = _load_audio_source(entry["source_path"])
                report(tag, "Source Media", "LOADED (cache miss)")
            if audio is None:
                continue
            if audio_vae_id is None:
                audio_latent, ref_audio_t = h3._encode_ref_audio(audio_vae, audio)
                reason = "DISABLED" if cache_mode == "disabled" else "DISABLED (VAE identity unavailable)"
                report(tag, "Audio", reason)
            else:
                if source_hash is None:
                    source_hash = source_fingerprint(entry, lambda: hash_audio(audio))
                source_sr = int(audio["sample_rate"])
                metadata = {
                    "source_sha256": source_hash,
                    "model": audio_vae_id,
                    "source_sample_rate": source_sr,
                    "audio_sample_rate": vae_sr,
                    "processing_version": _AUDIO_PROCESSING_VERSION,
                }

                def encode_audio():
                    encoded, _ = h3._encode_ref_audio(audio_vae, audio)
                    return encoded

                key = fingerprint({"schema": CACHE_SCHEMA_VERSION, "modality": "audio", **metadata})
                audio_latent, _, state = _CACHE.get_or_create(
                    "audio", entry, key, metadata, encode_audio, cache_mode)
                ref_audio_t = audio_latent.shape[-1]
                report(tag, "Audio", state)
            ref_items.append({"type": "audio"})
            ref_blocks.append({"kind": "audio", "ref_audio_t": ref_audio_t,
                               "audio_latent": audio_latent})
            if compiled_key:
                try:
                    _CACHE.save_compiled(
                        entry, compiled_key, "audio",
                        {"audio_latent": audio_latent},
                        {"tag": tag, "ref_audio_t": int(ref_audio_t)},
                    )
                    report(tag, "Lazy Bundle", "CREATED")
                except (OSError, ValueError) as error:
                    _LOG.warning("H3 audio lazy bundle could not be saved: %s", error)

        guide_keyframes = []
        if first_frame is not None:
            first = h3._resize(first_frame[:1], width, height, "disabled")
            # Keep library references first so their <Picture N> ordinals do
            # not change. The guide image participates in Qwen visual context
            # but enters the DiT only through minimax_keyframes.
            ref_items.append({"type": "image", "data": first})
            guide_keyframes.append({
                "resolved_frame_index": 0,
                "latent": vae.encode(first),
            })
        if last_frame is not None:
            last = h3._resize(last_frame[:1], width, height, "center")
            ref_items.append({"type": "image", "data": last})
            guide_keyframes.append({
                "resolved_frame_index": frame_count - 1,
                "latent": vae.encode(last),
            })

        tokens = clip.tokenize(prompt, minimax_ref_items=ref_items)
        cond = clip.encode_from_tokens_scheduled(tokens)
        if ref_blocks:
            cond = node_helpers.conditioning_set_values(cond, {"minimax_refs": ref_blocks})
        if guide_keyframes:
            cond = node_helpers.conditioning_set_values(
                cond, {"minimax_keyframes": guide_keyframes})
            labels = []
            if first_frame is not None:
                labels.append("first")
            if last_frame is not None:
                labels.append("last")
            statuses.setdefault("Frame Guides", []).append(
                f"Keyframes: {' + '.join(labels)}")
        status = "\n".join(
            line for tag, lines in statuses.items() for line in (tag, *lines))
        if not status:
            status = "No cacheable image or standalone audio references."
        return io.NodeOutput(cond, latent, status)


class SkebaCachedMiniMaxH3ReferenceFirstLast(io.ComfyNode):
    """Native first/last-frame H3 generation combined with cached references."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="SkebaCachedMiniMaxH3ReferenceFirstLast",
            display_name="SKEBA MiniMax H3 Cached Reference + First/Last Frame",
            category="Skeba AI Nodes - Reference/Experimental",
            description=(
                "Combine cached image/video/audio references with native H3 "
                "first-frame and last-frame keyframes without changing the "
                "library reference ordinals."
            ),
            inputs=[
                io.Clip.Input("clip"),
                io.Vae.Input("vae"),
                io.Vae.Input("audio_vae"),
                io.String.Input("prompt", multiline=True, dynamic_prompts=True),
                io.Int.Input("width", default=1344, min=32,
                             max=nodes.MAX_RESOLUTION, step=32),
                io.Int.Input("height", default=768, min=32,
                             max=nodes.MAX_RESOLUTION, step=32),
                io.Int.Input("length", default=124, min=5, max=3600, step=17),
                io.Combo.Input("ref_image_size", options=["match", "max"],
                               default="match"),
                io.Combo.Input(
                    "cache_mode", options=["auto", "disabled", "rebuild"],
                    default="auto",
                ),
                io.Latent.Input(
                    "target_latent", optional=True,
                    tooltip=(
                        "For an upscale/second pass, connect the exact H3 AV "
                        "latent sent to that sampler. Guide images are encoded "
                        "at its real canvas and the same latent is returned."
                    ),
                ),
                io.Image.Input("first_frame", optional=True),
                io.Image.Input("last_frame", optional=True),
                io.Autogrow.Input(
                    "ref_images", optional=True,
                    template=io.Autogrow.TemplatePrefix(
                        input=io.Image.Input("ref_image"), prefix="ref_image_",
                        min=0, max=9)),
                io.Autogrow.Input(
                    "ref_videos", optional=True,
                    template=io.Autogrow.TemplatePrefix(
                        input=io.Image.Input("ref_video"), prefix="ref_video_",
                        min=0, max=3)),
                io.Autogrow.Input(
                    "ref_video_audios", optional=True,
                    template=io.Autogrow.TemplatePrefix(
                        input=io.Audio.Input("ref_video_audio"),
                        prefix="ref_video_audio_", min=0, max=3)),
                io.Autogrow.Input(
                    "ref_audios", optional=True,
                    template=io.Autogrow.TemplatePrefix(
                        input=io.Audio.Input("ref_audio"), prefix="ref_audio_",
                        min=0, max=3)),
                ReferenceBundle.Input(
                    "reference_bundle", optional=True,
                    tooltip="Connect H3 Tagged Reference Prompt for cache identity.",
                ),
            ],
            outputs=[
                io.Conditioning.Output(display_name="positive"),
                io.Latent.Output(),
                io.String.Output(display_name="cache_status"),
            ],
        )

    @classmethod
    def execute(cls, clip, vae, audio_vae, prompt, width, height, length,
                ref_image_size="match", cache_mode="auto", first_frame=None,
                last_frame=None, target_latent=None, reference_bundle=None, ref_images=None,
                ref_videos=None, ref_video_audios=None, ref_audios=None):
        return SkebaCachedMiniMaxH3ReferenceToVideo.execute(
            clip=clip,
            vae=vae,
            audio_vae=audio_vae,
            prompt=prompt,
            width=width,
            height=height,
            length=length,
            ref_image_size=ref_image_size,
            cache_mode=cache_mode,
            reference_bundle=reference_bundle,
            ref_images=ref_images,
            ref_videos=ref_videos,
            ref_video_audios=ref_video_audios,
            ref_audios=ref_audios,
            first_frame=first_frame,
            last_frame=last_frame,
            target_latent=target_latent,
        )

"""Skeba's locally loaded variant of MiniMax H3 Video to Prompt.

The analyzer runtime and prompt guides are adapted from ComfyUI-VideoAnalyzer
under the MIT notice in this directory's LICENSE file.
"""

import json
import threading
from pathlib import Path
from uuid import uuid4

import folder_paths
from comfy_api.latest import Types, io, ui

from . import pipeline
from .vlm import ATTENTION_MODES, MEMORY_MODES, VLMPredictor


_CACHE = {"lock": threading.RLock(), "path": None, "settings": None,
          "signature": None, "predictor": None}


def _model_roots():
    roots = [Path(folder_paths.models_dir) / name for name in
             ("video_analyzer", "vlm", "LLM", "clip", "clip_vision", "text_encoders")]
    for category in ("clip", "clip_vision", "text_encoders", "vlm", "LLM", "video_analyzer"):
        try:
            roots.extend(Path(path) for path in folder_paths.get_folder_paths(category))
        except KeyError:
            pass
    return tuple(dict.fromkeys(path.resolve() for path in roots if path.is_dir()))


def local_vlm_folders():
    """List complete local model folders, including configured extra model paths."""
    found = set()
    for root in _model_roots():
        for parent in (root, *root.iterdir()):
            if not parent.is_dir():
                continue
            for candidate in (parent, *parent.iterdir()):
                if candidate.is_dir() and _supported_model(candidate):
                    found.add(str(candidate.resolve()))
    return sorted(found, key=str.casefold)


def _supported_model(path):
    config = path / "config.json"
    if not config.is_file():
        return False
    try:
        model_type = str(json.loads(config.read_text(encoding="utf-8")).get("model_type", ""))
    except (OSError, ValueError):
        return False
    has_weights = any(path.glob("*.safetensors")) or any(path.glob("pytorch_model*.bin"))
    has_processor = (path / "preprocessor_config.json").is_file()
    has_tokenizer = any((path / name).is_file() for name in
                        ("tokenizer.json", "tokenizer_config.json"))
    return (model_type.startswith("qwen") and "vl" in model_type
            and has_weights and has_processor and has_tokenizer)


def _resolve_model(model_folder, custom_folder):
    choice = custom_folder.strip() if model_folder == "Custom local folder" else model_folder
    if not choice:
        raise ValueError("Select a local VLM folder or enter one in custom_folder.")
    path = Path(choice).expanduser().resolve()
    if not path.is_dir() or not _supported_model(path):
        raise ValueError("Select a complete local Qwen VL folder containing config.json, "
                         "model weights, and processor/tokenizer files. A single CLIP "
                         ".safetensors file cannot generate video descriptions.")
    return path


def _model_signature(path):
    files = [file for file in path.iterdir() if file.is_file() and
             (file.suffix in (".json", ".safetensors", ".bin") or
              file.name in ("tokenizer.model", "merges.txt", "vocab.json"))]
    return tuple(sorted((file.name, file.stat().st_size, file.stat().st_mtime_ns)
                        for file in files))


class SkebaH3LocalVLMLoader(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        folders = local_vlm_folders()
        return io.Schema(
            node_id="SkebaH3LocalVLMLoader",
            display_name="SKEBA H3 Local VLM Loader",
            category="Skeba AI Nodes - Video Analysis",
            description="Load a complete Qwen vision-language model from a local folder. "
                        "Searches ComfyUI model and extra-model clip/VLM folders; never downloads.",
            inputs=[
                io.Combo.Input("model_folder", options=folders + ["Custom local folder"],
                               default=folders[0] if folders else "Custom local folder"),
                io.String.Input("custom_folder", default="", optional=True,
                                tooltip="Local directory containing config.json, weights, and processor files."),
                io.Combo.Input("memory_mode", options=list(MEMORY_MODES),
                               default="ComfyUI managed (BF16)", advanced=True),
                io.Combo.Input("attention_mode", options=list(ATTENTION_MODES),
                               default="Auto (SDPA)", advanced=True),
            ],
            outputs=[io.Custom("VLM_MODEL").Output(display_name="vlm")],
        )

    @classmethod
    def execute(cls, model_folder, custom_folder="", memory_mode="ComfyUI managed (BF16)",
                attention_mode="Auto (SDPA)"):
        path = _resolve_model(model_folder, custom_folder)
        settings = (memory_mode, attention_mode)
        signature = _model_signature(path)
        with _CACHE["lock"]:
            if (_CACHE["path"] != path or _CACHE["settings"] != settings or
                    _CACHE["signature"] != signature or _CACHE["predictor"] is None):
                if _CACHE["predictor"] is not None:
                    _CACHE["predictor"].close()
                _CACHE["predictor"] = VLMPredictor(str(path), *settings)
                _CACHE["path"], _CACHE["settings"], _CACHE["signature"] = path, settings, signature
            predictor = _CACHE["predictor"]
        return io.NodeOutput({"kind": "local", "predictor": predictor})

    @classmethod
    def fingerprint_inputs(cls, model_folder, custom_folder="", memory_mode="ComfyUI managed (BF16)",
                           attention_mode="Auto (SDPA)"):
        path = _resolve_model(model_folder, custom_folder)
        return str((path, memory_mode, attention_mode, _model_signature(path),
                    id(_CACHE["predictor"])))


class SkebaH3VideoToPrompt(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="SkebaH3VideoToPrompt",
            display_name="SKEBA H3 Video to Prompt (Local VLM)",
            category="Skeba AI Nodes - Video Analysis",
            description="Analyze video with a locally loaded VLM and write a MiniMax H3 or LTX prompt.",
            is_output_node=True,
            inputs=[
                io.Video.Input("video"),
                io.Custom("VLM_MODEL").Input("vlm"),
                io.Combo.Input("mode", options=["T2VA", "I2VA", "FL2VA", "L2VA", "Ref2VA", "LTX"],
                               default="T2VA"),
                io.Float.Input("duration", default=0.0, min=0.0, max=20.0, step=1.0, optional=True),
                io.Float.Input("max_seconds", default=0.0, min=0.0, max=600.0, step=1.0,
                               optional=True, advanced=True),
                io.Boolean.Input("keep_fade", default=False, advanced=True),
                io.Float.Input("frame_fps", default=1.0, min=0.1, max=4.0, step=0.1, advanced=True),
                io.Int.Input("max_frames", default=24, min=1, max=48, advanced=True),
                io.Int.Input("frame_max_side", default=512, min=64, max=1280, step=16, advanced=True),
                io.Boolean.Input("use_asr", default=False,
                                 tooltip="Optional audio transcription; may download ASR weights on first use."),
                io.Combo.Input("asr_model", options=["tiny", "base", "small", "medium",
                                                     "large-v3", "large-v3-turbo"],
                               default=pipeline.DEFAULT_ASR_MODEL, advanced=True),
                io.Boolean.Input("use_audio_tags", default=False,
                                 tooltip="Optional audio tagging; may download PANNs weights on first use."),
                io.Float.Input("tags_threshold", default=pipeline.DEFAULT_TAG_THRESHOLD,
                               min=0.0, max=1.0, step=0.01, advanced=True),
                io.Int.Input("tags_max", default=pipeline.DEFAULT_TAG_MAX, min=1, max=32, advanced=True),
                io.Int.Input("max_new_tokens", default=8192, min=256, max=16384,
                             step=256, advanced=True),
                io.Boolean.Input("unload_vlm", default=False, advanced=True),
            ],
            outputs=[io.String.Output(display_name="MiniMax H3 Prompt")],
        )

    @classmethod
    def execute(cls, video, vlm, mode="T2VA", duration=0.0, max_seconds=0.0,
                keep_fade=False, frame_fps=1.0, max_frames=24, frame_max_side=512,
                use_asr=False, asr_model="small", use_audio_tags=False,
                tags_threshold=pipeline.DEFAULT_TAG_THRESHOLD, tags_max=pipeline.DEFAULT_TAG_MAX,
                max_new_tokens=8192, unload_vlm=False):
        if not isinstance(vlm, dict) or vlm.get("kind") != "local" or not hasattr(vlm.get("predictor"), "generate_text"):
            raise ValueError("Connect SKEBA H3 Local VLM Loader to vlm.")
        parent = Path(folder_paths.get_temp_directory()) / "skeba_h3_video_to_prompt"
        parent.mkdir(parents=True, exist_ok=True)
        work_dir = parent / uuid4().hex
        work_dir.mkdir()
        source = work_dir / "source.mp4"
        video.save_to(str(source), format=Types.VideoContainer.MP4, codec=Types.VideoCodec.AUTO)
        try:
            prompt = pipeline.video_to_prompt(
                str(source), work_dir, vlm=vlm, mode=mode,
                duration=duration if duration > 0 else None,
                max_seconds=max_seconds if max_seconds > 0 else None,
                keep_fade=keep_fade, frame_fps=frame_fps, max_frames=max_frames,
                frame_max_side=frame_max_side, use_asr=use_asr, asr_model=asr_model,
                use_audio_tags=use_audio_tags, tags_threshold=tags_threshold,
                tags_max=tags_max, max_new_tokens=max_new_tokens)
        finally:
            if unload_vlm:
                vlm["predictor"].handle.unload()
        return io.NodeOutput(prompt, ui=ui.PreviewText(prompt))

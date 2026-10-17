# Adapted from ComfyUI-VideoAnalyzer (MIT; see LICENSE). Qwen-family VL models
# load exclusively from a complete local folder, with ComfyUI-managed residency.
import gc
import os
import threading
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
from PIL import Image

# This node uses PyTorch only. Avoid importing an unrelated TensorFlow build
# through transformers' auto classes (the local ComfyUI venv may contain one).
os.environ.setdefault("USE_TF", "0")


def log(msg: str) -> None:
    print(f"[h3] {msg}", flush=True)


@dataclass(frozen=True)
class ModelSpec:
    repo_id: str
    estimated_gib: float
    video: bool = True


# Qwen-family only: the video input pathway (video_metadata + do_sample_frames)
# below is implemented and tested against these processors.
MODEL_CATALOG = {
    "Qwen 2.5 VL 3B Instruct": ModelSpec("Qwen/Qwen2.5-VL-3B-Instruct", 7.0),
    "Qwen 2.5 VL 7B Instruct": ModelSpec("Qwen/Qwen2.5-VL-7B-Instruct", 16.0),
    "Qwen 3 VL 2B Instruct": ModelSpec("Qwen/Qwen3-VL-2B-Instruct", 5.0),
    "Qwen 3 VL 4B Instruct": ModelSpec("Qwen/Qwen3-VL-4B-Instruct", 9.0),
    "Qwen 3 VL 8B Instruct": ModelSpec("Qwen/Qwen3-VL-8B-Instruct", 18.0),
}
DEFAULT_MODEL_LABEL = "Qwen 2.5 VL 7B Instruct"
MEMORY_MODES = ("ComfyUI managed (BF16)", "CPU")
ATTENTION_MODES = ("Auto (SDPA)", "Flash Attention 2", "Eager")


def execution_device() -> torch.device:
    """ComfyUI's selected device, with standalone fallbacks."""
    try:
        import comfy.model_management as model_management

        return model_management.get_torch_device()
    except Exception:
        if torch.cuda.is_available():
            return torch.device("cuda", torch.cuda.current_device())
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")


def _supports_bfloat16(device: torch.device) -> bool:
    try:
        torch.empty(1, dtype=torch.bfloat16, device=device)
        return True
    except Exception:
        return False


def pick_dtype(memory_mode: str, device: torch.device | None = None) -> torch.dtype:
    device = device or execution_device()
    if memory_mode == "CPU":
        return torch.float32
    if _supports_bfloat16(device):
        return torch.bfloat16
    return torch.float16 if device.type in {"cuda", "mps", "xpu"} else torch.float32


def inference_context(device: torch.device, dtype: torch.dtype):
    if device.type in {"cuda", "xpu"} and dtype in {torch.float16, torch.bfloat16}:
        return torch.autocast(device.type, dtype=dtype)
    return nullcontext()


def model_device(model: torch.nn.Module) -> torch.device:
    try:
        return next(model.parameters()).device
    except StopIteration:
        return execution_device()


def move_inputs(inputs: dict, device: torch.device) -> dict:
    return {k: v.to(device) if isinstance(v, torch.Tensor) else v
            for k, v in inputs.items()}


def tensor_batch_to_pil(images: torch.Tensor) -> list:
    if images.dim() == 3:
        images = images.unsqueeze(0)
    if images.dim() != 4:
        raise ValueError(f"Expected an IMAGE batch, got {tuple(images.shape)}")
    batch = (images.clamp(0, 1).mul(255).round().byte().cpu().numpy())
    return [Image.fromarray(frame, mode="RGB") for frame in batch]


class ManagedModelAdapter(torch.nn.Module):
    """Give an HF model the mutable ``device`` attribute ComfyUI expects.

    Recent transformers models expose ``device`` as a read-only property;
    ModelPatcher writes that attribute as residency changes, so the original
    module must be wrapped. Attribute access stays transparent."""

    def __init__(self, model: torch.nn.Module, device: torch.device):
        super().__init__()
        self.wrapped_model = model
        self.device = device

    def forward(self, *args, **kwargs):
        return self.wrapped_model(*args, **kwargs)

    def __getattr__(self, name):
        try:
            return super().__getattr__(name)
        except AttributeError:
            return getattr(self.wrapped_model, name)


class ManagedTorchModel:
    """Register a transformers model with ComfyUI's smart VRAM manager."""

    def __init__(self, model: torch.nn.Module, *, processor: Any = None,
                 load_device: torch.device | None = None,
                 offload_device: torch.device | None = None):
        import comfy.model_management as model_management
        from comfy.model_patcher import ModelPatcher

        self.load_device = load_device or model_management.get_torch_device()
        self.offload_device = offload_device or (
            torch.device("cpu") if self.load_device.type != "cpu" else self.load_device)
        self.model = ManagedModelAdapter(model.eval(), self.offload_device)
        self.processor = processor
        self.patcher = ModelPatcher(self.model, load_device=self.load_device,
                                    offload_device=self.offload_device)
        self._lock = threading.RLock()
        self._closed = False

    def ensure_loaded(self) -> torch.nn.Module:
        if self._closed:
            raise RuntimeError("This model handle has already been closed.")
        with self._lock:
            import comfy.model_management as model_management

            model_management.load_models_gpu([self.patcher])
            return self.model

    def unload(self) -> None:
        if self._closed:
            return
        with self._lock:
            import comfy.model_management as model_management

            model_management.unload_model_and_clones(self.patcher)

    def close(self) -> None:
        if self._closed:
            return
        self.unload()
        self._closed = True
        self.processor = None
        self.model = None
        self.patcher = None
        gc.collect()


VRAM_HINT = ("the VLM was partially loaded because there was not enough free VRAM "
             "(this happens when other models are resident). Free VRAM (unload other "
             "models) or select a smaller model in SKEBA H3 Local VLM Loader.")


def _vram_hint(e: RuntimeError) -> str:
    s = str(e)
    return VRAM_HINT if ("same device" in s or "index_select" in s) else s


class WindowedRepetitionPenalty:
    """Penalize tokens repeated within the last `window` *generated* tokens only.

    transformers' built-in repetition_penalty covers the prompt as well, which
    suppresses field labels that appear many times in the rewrite prompt
    (e.g. "non_diegetic_music") and makes the model stop or dodge mid-output.
    A generated-only windowed penalty breaks local loops without that damage.
    Batch size 1."""

    def __init__(self, penalty: float = 1.15, window: int = 128,
                 prompt_len: int = 0):
        self.penalty = penalty
        self.window = window
        self.prompt_len = prompt_len

    def __call__(self, input_ids, scores):
        generated = input_ids[0, self.prompt_len:][-self.window:]
        if generated.numel() == 0:
            return scores
        for token_id in torch.unique(generated):
            s = scores[0, token_id]
            scores[0, token_id] = s / self.penalty if s > 0 else s * self.penalty
        return scores


class VLMPredictor:
    """Load one vision-language model and run video/text generations on it."""

    def __init__(self, model_path: str,
                 memory_mode: str = "ComfyUI managed (BF16)",
                 attention_mode: str = "Auto (SDPA)"):
        import transformers
        # ComfyUI may import transformers before this custom node, caching a
        # broken TensorFlow installation as available. This VLM is PyTorch-only.
        if os.environ.get("USE_TF") == "0":
            import transformers.utils.import_utils as import_utils
            if hasattr(import_utils, "_tf_available"):
                import_utils._tf_available = False

        model_path = Path(model_path).resolve()
        if not (model_path.is_dir() and (model_path / "config.json").is_file()):
            raise ValueError("Select a complete local VLM folder containing config.json, "
                             "model weights, and processor/tokenizer files.")
        self.repo_id = str(model_path)
        self.memory_mode = memory_mode

        attention = {"Auto (SDPA)": None, "Flash Attention 2": "flash_attention_2",
                     "Eager": "eager"}[attention_mode]
        if attention_mode == "Flash Attention 2" and execution_device().type != "cuda":
            raise RuntimeError("Flash Attention 2 requires a CUDA build. "
                               "Select Auto (SDPA) on this device.")

        self.dtype = pick_dtype(memory_mode)
        log(f"VLM: loading local model {model_path} "
            f"({'CPU' if memory_mode == 'CPU' else str(execution_device())}, {self.dtype})")
        self.processor = transformers.AutoProcessor.from_pretrained(
            str(model_path), local_files_only=True, trust_remote_code=False)

        kwargs: dict = {"dtype": self.dtype}
        if attention is not None:
            kwargs["attn_implementation"] = attention
        if memory_mode == "CPU":
            pass  # stay in CPU RAM; load happens lazily via ensure_loaded
        try:
            model = transformers.AutoModelForImageTextToText.from_pretrained(
                str(model_path), local_files_only=True, trust_remote_code=False,
                **kwargs).eval()
        except ImportError as exc:
            if attention_mode == "Flash Attention 2":
                raise RuntimeError("Flash Attention 2 is unavailable for this "
                                   "PyTorch build. Select Auto (SDPA).") from exc
            raise
        self.handle = ManagedTorchModel(model, processor=self.processor)
        log(f"VLM ready: {model_path}")

    def close(self) -> None:
        self.handle.close()
        self.processor = None

    def _inputs(self, messages, video_metadata=None):
        """Chat template with the Qwen video pathway, older-template fallback.

        Video timing metadata is version-dependent: transformers >=5 wants it
        nested inside a `processor_kwargs` dict, while 4.5x takes
        video_metadata/do_sample_frames as direct top-level kwargs. Both are
        tried before falling back to a metadata-less multi-image call (which
        makes shot timestamps approximate)."""
        if video_metadata is not None:
            attempts = (
                {"processor_kwargs": {
                    "video_metadata": [[video_metadata]],
                    "do_sample_frames": False}},
                {"video_metadata": [[video_metadata]],
                 "do_sample_frames": False},
            )
            for kwargs in attempts:
                try:
                    return self.processor.apply_chat_template(
                        messages, add_generation_prompt=True, tokenize=True,
                        return_dict=True, return_tensors="pt", **kwargs)
                except (TypeError, ValueError, KeyError):
                    continue
            log("warning: video timing metadata not applied by this transformers "
                "version; shot timestamps may be approximate")

        # portable fallback: no video metadata (still images, or unsupported
        # transformers versions)
        media = []
        portable_messages = []
        for message in messages:
            content = []
            for part in message["content"]:
                if part["type"] == "image":
                    media.append(part["image"])
                    content.append({"type": "image"})
                elif part["type"] == "video":
                    media.extend(part["video"])
                    content.extend({"type": "image"} for _ in part["video"])
                else:
                    content.append(part)
            portable_messages.append({"role": message["role"], "content": content})
        prompt = self.processor.apply_chat_template(
            portable_messages, add_generation_prompt=True, tokenize=False)
        return self.processor(text=[prompt], images=media, return_tensors="pt")

    def _decode(self, output, input_length: int) -> str:
        return self.processor.batch_decode(
            output[:, input_length:], skip_special_tokens=True,
            clean_up_tokenization_spaces=False)[0].strip()

    def generate_text(self, prompt: str, max_new_tokens: int,
                      temperature: float = 0.2, top_p: float = 0.9) -> str:
        """Text-only generation on the loaded model."""
        model = self.handle.ensure_loaded()
        device = model_device(model)
        messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
        inputs = move_inputs(
            self.processor.apply_chat_template(
                messages, add_generation_prompt=True, tokenize=True,
                return_dict=True, return_tensors="pt"),
            device)
        generation = {"max_new_tokens": int(max_new_tokens), "do_sample": temperature > 0,
                      # premature EOS (right after a section marker/label) is a common
                      # 7B glitch; forcing continuation lets it finish the structure,
                      # which validation and the fence/label fixers then clean up
                      "min_new_tokens": min(200, int(max_new_tokens))}
        if temperature > 0:
            generation.update(temperature=temperature, top_p=top_p)
        with torch.inference_mode(), inference_context(device, self.dtype):
            try:
                from transformers import LogitsProcessorList

                output = model.generate(
                    **inputs, **generation,
                    logits_processor=LogitsProcessorList([WindowedRepetitionPenalty(
                        prompt_len=inputs["input_ids"].shape[-1])]))
            except RuntimeError as e:
                raise RuntimeError(_vram_hint(e))
        return self._decode(output, inputs["input_ids"].shape[-1])

    def generate(self, images=None, prompt: str = "", system_prompt: str = "",
                 max_new_tokens: int = 4096, temperature: float = 0.2,
                 top_p: float = 0.9, video_frames=None, fps: float = 1.0) -> str:
        """One generation over a frame batch (video pathway) or per still image."""
        still_images = tensor_batch_to_pil(images) if images is not None else []
        video = tensor_batch_to_pil(video_frames) if video_frames is not None else None
        if video is None and not still_images:
            raise ValueError("Connect either image or video_frames.")

        results = []
        runs = [None] if video is not None else still_images
        for image in runs:
            messages = []
            if system_prompt.strip():
                messages.append({"role": "system",
                                 "content": [{"type": "text", "text": system_prompt.strip()}]})
            if video is not None:
                content = [{"type": "video", "video": video}]
                effective_prompt = (f"The video frames are sampled at {float(fps):g} FPS.\n\n"
                                    f"{prompt}")
            else:
                content = [{"type": "image", "image": image}]
                effective_prompt = prompt
            content.append({"type": "text", "text": effective_prompt})
            messages.append({"role": "user", "content": content})

            metadata = None
            if video is not None:
                metadata = {
                    "total_num_frames": len(video),
                    "fps": float(fps),
                    "duration": len(video) / float(fps),
                    "frames_indices": list(range(len(video))),
                    "width": video[0].width,
                    "height": video[0].height,
                }
            inputs = self._inputs(messages, video_metadata=metadata)
            model = self.handle.ensure_loaded()
            inputs = move_inputs(inputs, model_device(model))
            generation = {"max_new_tokens": int(max_new_tokens),
                          "do_sample": temperature > 0,
                          "min_new_tokens": min(200, int(max_new_tokens))}
            if temperature > 0:
                generation.update(temperature=temperature, top_p=top_p)
            with torch.inference_mode(), inference_context(model_device(model), self.dtype):
                from transformers import LogitsProcessorList

                output = model.generate(
                    **inputs, **generation,
                    logits_processor=LogitsProcessorList([WindowedRepetitionPenalty(
                        prompt_len=inputs["input_ids"].shape[-1])]))
            results.append(self._decode(output, inputs["input_ids"].shape[-1]))
        if len(results) == 1:
            return results[0]
        return "\n\n".join(f"--- Image {i} ---\n{t}" for i, t in enumerate(results, 1))

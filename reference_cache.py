import hashlib
import json
import logging
import os
import threading
import uuid
from pathlib import Path

import torch
from safetensors import SafetensorError
from safetensors.torch import load_file, save_file

from .library import library_root


CACHE_SCHEMA_VERSION = 1
_LOG = logging.getLogger(__name__)
_CACHE_LOCK = threading.RLock()
_FILE_HASHES = {}


def cache_root():
    return library_root() / "cache" / f"v{CACHE_SCHEMA_VERSION}"


def fingerprint(values):
    payload = json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def hash_file(path, memoize=False):
    path = Path(path).resolve()
    stat = path.stat()
    memo_key = (str(path), stat.st_size, stat.st_mtime_ns)
    if memoize:
        with _CACHE_LOCK:
            cached = _FILE_HASHES.get(memo_key)
        if cached is not None:
            return cached

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    value = digest.hexdigest()
    if memoize:
        with _CACHE_LOCK:
            _FILE_HASHES[memo_key] = value
    return value


def hash_tensor(tensor):
    value = tensor.detach().to("cpu").contiguous()
    digest = hashlib.sha256()
    digest.update(str(value.dtype).encode("ascii"))
    digest.update(json.dumps(list(value.shape)).encode("ascii"))
    digest.update(value.view(torch.uint8).numpy().tobytes())
    return digest.hexdigest()


def hash_audio(audio):
    return fingerprint({
        "sample_rate": int(audio["sample_rate"]),
        "waveform": hash_tensor(audio["waveform"]),
    })


def vae_fingerprint(vae):
    patcher = getattr(vae, "patcher", None)
    cached_init = getattr(patcher, "cached_patcher_init", None)
    if not cached_init or len(cached_init) < 2 or not cached_init[1]:
        return None
    path = Path(cached_init[1][0])
    if not path.is_file():
        return None
    try:
        file_hash = hash_file(path, memoize=True)
    except OSError as error:
        _LOG.warning("H3 reference cache could not identify VAE %s: %s", path, error)
        return None
    model = getattr(vae, "first_stage_model", None)
    return fingerprint({
        "class": type(model).__module__ + "." + type(model).__qualname__,
        "file_sha256": file_hash,
    })


def clip_fingerprint(clip):
    patcher = getattr(clip, "patcher", None)
    if patcher is None:
        return None
    if getattr(patcher, "forced_hooks", None):
        return None
    if getattr(patcher, "patches", None):
        return None

    cached_init = getattr(patcher, "cached_patcher_init", None)
    if not cached_init or len(cached_init) < 2 or not cached_init[1]:
        return None
    paths = cached_init[1][0]
    if isinstance(paths, (str, os.PathLike)):
        paths = [paths]
    if not isinstance(paths, (list, tuple)) or not paths:
        return None

    model_files = []
    try:
        for value in paths:
            path = Path(value)
            if not path.is_file():
                return None
            model_files.append({
                "name": path.name,
                "sha256": hash_file(path, memoize=True),
            })
    except (OSError, TypeError) as error:
        _LOG.warning("H3 reference cache could not identify the Qwen model: %s", error)
        return None

    model = getattr(clip, "cond_stage_model", None)
    dtypes = sorted(str(value) for value in getattr(model, "dtypes", set()))
    return fingerprint({
        "class": type(model).__module__ + "." + type(model).__qualname__,
        "dtypes": dtypes,
        "files": model_files,
    })


def source_fingerprint(entry, fallback):
    if entry:
        source_path = entry.get("source_path")
        if source_path and Path(source_path).is_file():
            try:
                return hash_file(source_path, memoize=True)
            except OSError as error:
                _LOG.warning("H3 reference cache could not hash %s: %s", source_path, error)
    return fallback()


class ReferenceTensorCache:
    @staticmethod
    def _record_dir(entry, key):
        identity = str((entry or {}).get("record_id") or f"external:{key}")
        return cache_root() / hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]

    def load_compiled(self, entry, key, kind):
        """Load a complete reference payload without evaluating source media."""
        record_dir = self._record_dir(entry, key)
        tensor_path = record_dir / "compiled" / f"{key}.safetensors"
        metadata_path = record_dir / "compiled" / f"{key}.json"
        if not tensor_path.is_file() or not metadata_path.is_file():
            return None
        with _CACHE_LOCK:
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                if (
                    metadata.get("cache_schema_version") != CACHE_SCHEMA_VERSION
                    or metadata.get("key") != key
                    or metadata.get("kind") != kind
                ):
                    raise ValueError("compiled reference metadata does not match")
                tensors = load_file(str(tensor_path), device="cpu")
                if not tensors:
                    raise ValueError("compiled reference has no tensors")
                return tensors, metadata
            except (OSError, json.JSONDecodeError, SafetensorError, ValueError) as error:
                _LOG.warning("H3 compiled reference cache ignored %s: %s", tensor_path, error)
                return None

    def save_compiled(self, entry, key, kind, tensors, metadata):
        """Atomically save a packed reference payload for bundle-only reuse."""
        record_dir = self._record_dir(entry, key)
        directory = record_dir / "compiled"
        tensor_path = directory / f"{key}.safetensors"
        metadata_path = directory / f"{key}.json"
        packed = {}
        for name, tensor in tensors.items():
            if not isinstance(tensor, torch.Tensor):
                raise ValueError(f"compiled tensor {name!r} is not a tensor")
            packed[name] = tensor.detach().to("cpu").contiguous()
        if not packed:
            raise ValueError("compiled reference has no tensors")
        document = {
            **metadata,
            "cache_schema_version": CACHE_SCHEMA_VERSION,
            "key": key,
            "kind": kind,
        }
        with _CACHE_LOCK:
            directory.mkdir(parents=True, exist_ok=True)
            tensor_temporary = tensor_path.with_name(
                f".{tensor_path.name}.{uuid.uuid4().hex}.tmp")
            metadata_temporary = metadata_path.with_name(
                f".{metadata_path.name}.{uuid.uuid4().hex}.tmp")
            try:
                save_file(packed, str(tensor_temporary))
                metadata_temporary.write_text(
                    json.dumps(document, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                os.replace(tensor_temporary, tensor_path)
                os.replace(metadata_temporary, metadata_path)
            finally:
                if tensor_temporary.exists():
                    tensor_temporary.unlink()
                if metadata_temporary.exists():
                    metadata_temporary.unlink()

    def get_or_create(self, modality, entry, key, metadata, build, mode="auto"):
        tag = (entry or {}).get("tag") or "external"
        record_dir = self._record_dir(entry, key)
        tensor_path = record_dir / modality / f"{key}.safetensors"

        if mode == "disabled":
            return build(), tag, "DISABLED"

        with _CACHE_LOCK:
            if mode != "rebuild" and tensor_path.is_file():
                try:
                    tensor = load_file(str(tensor_path), device="cpu")["latent"]
                    self._validate(modality, tensor, metadata)
                    return tensor, tag, "HIT"
                except (OSError, SafetensorError, KeyError, ValueError) as error:
                    _LOG.warning("H3 reference cache ignored %s: %s", tensor_path, error)

            tensor = build()
            try:
                if modality == "audio" and "ref_audio_t" not in metadata:
                    metadata = {**metadata, "ref_audio_t": int(tensor.shape[-1])}
                elif modality == "video" and "latent_t" not in metadata:
                    metadata = {**metadata, "latent_t": int(tensor.shape[2])}
                self._validate(modality, tensor, metadata)
                tensor_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = tensor_path.with_name(f".{tensor_path.name}.{uuid.uuid4().hex}.tmp")
                try:
                    save_file({"latent": tensor.detach().to("cpu").contiguous()}, str(temporary))
                    os.replace(temporary, tensor_path)
                finally:
                    if temporary.exists():
                        temporary.unlink()
                self._update_manifest(record_dir, entry, modality, key, metadata, tensor_path)
                state = "REBUILT" if mode == "rebuild" else "MISS -> CREATED"
            except (OSError, SafetensorError, ValueError) as error:
                _LOG.warning("H3 reference cache could not write %s: %s", tensor_path, error)
                state = "MISS (cache write failed)"
            return tensor, tag, state

    def get_or_create_visual(self, entry, key, metadata, build, mode="auto"):
        tag = (entry or {}).get("tag") or "external"
        record_dir = self._record_dir(entry, key)
        tensor_path = record_dir / "qwen" / f"{key}.safetensors"

        if mode == "disabled":
            return build(), tag, "DISABLED"

        with _CACHE_LOCK:
            if mode != "rebuild" and tensor_path.is_file():
                try:
                    tensors = load_file(str(tensor_path), device="cpu")
                    visual = self._visual_from_tensors(tensors)
                    self._validate_visual(visual)
                    return visual, tag, "HIT"
                except (OSError, SafetensorError, KeyError, ValueError) as error:
                    _LOG.warning("H3 Qwen cache ignored %s: %s", tensor_path, error)

            visual = build()
            try:
                self._validate_visual(visual)
                tensors = {
                    "merged": visual["merged"].detach().to("cpu").contiguous(),
                    "grid": visual["grid"].detach().to("cpu").contiguous(),
                }
                for index, tensor in enumerate(visual["deepstack"]):
                    tensors[f"deepstack_{index}"] = tensor.detach().to("cpu").contiguous()
                tensor_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = tensor_path.with_name(f".{tensor_path.name}.{uuid.uuid4().hex}.tmp")
                try:
                    save_file(tensors, str(temporary))
                    os.replace(temporary, tensor_path)
                finally:
                    if temporary.exists():
                        temporary.unlink()
                visual_metadata = {
                    **metadata,
                    "tokens": int(visual["merged"].shape[0]),
                    "hidden_size": int(visual["merged"].shape[-1]),
                    "deepstack_count": len(visual["deepstack"]),
                }
                self._update_manifest(record_dir, entry, "qwen", key,
                                      visual_metadata, tensor_path)
                state = "REBUILT" if mode == "rebuild" else "MISS -> CREATED"
            except (OSError, SafetensorError, ValueError) as error:
                _LOG.warning("H3 Qwen cache could not write %s: %s", tensor_path, error)
                state = "MISS (cache write failed)"
            return visual, tag, state

    @staticmethod
    def _visual_from_tensors(tensors):
        indexes = []
        for name in tensors:
            if name.startswith("deepstack_"):
                try:
                    indexes.append(int(name.rsplit("_", 1)[-1]))
                except ValueError as error:
                    raise ValueError(f"invalid Qwen cache tensor name {name!r}") from error
        indexes.sort()
        if indexes != list(range(len(indexes))):
            raise ValueError("Qwen cache has non-contiguous DeepStack tensors")
        return {
            "merged": tensors["merged"],
            "grid": tensors["grid"],
            "deepstack": [tensors[f"deepstack_{index}"] for index in indexes],
        }

    @staticmethod
    def _validate_visual(visual):
        if not isinstance(visual, dict):
            raise ValueError("Qwen visual cache is not a mapping")
        merged = visual.get("merged")
        grid = visual.get("grid")
        deepstack = visual.get("deepstack")
        if not isinstance(merged, torch.Tensor) or merged.ndim != 2:
            raise ValueError("Qwen merged features have an invalid shape")
        if not isinstance(grid, torch.Tensor) or grid.ndim != 2 or grid.shape[-1] != 3:
            raise ValueError("Qwen grid has an invalid shape")
        if not isinstance(deepstack, (list, tuple)) or not deepstack:
            raise ValueError("Qwen DeepStack features are missing")
        for tensor in deepstack:
            if (not isinstance(tensor, torch.Tensor) or tensor.ndim != 2
                    or tensor.shape != merged.shape):
                raise ValueError("Qwen DeepStack features have an invalid shape")

    @staticmethod
    def _validate(modality, tensor, metadata):
        if not isinstance(tensor, torch.Tensor):
            raise ValueError("cached value is not a tensor")
        if modality == "image":
            if tensor.ndim != 5 or tensor.shape[0] != 1:
                raise ValueError(f"image latent has invalid shape {tuple(tensor.shape)}")
            expected = (int(metadata["latent_h"]), int(metadata["latent_w"]))
            if tuple(tensor.shape[-2:]) != expected:
                raise ValueError(
                    f"image latent is {tuple(tensor.shape[-2:])}, expected {expected}")
        elif modality == "audio":
            if tensor.ndim != 4 or tensor.shape[0] != 1:
                raise ValueError(f"audio latent has invalid shape {tuple(tensor.shape)}")
            if ("ref_audio_t" in metadata
                    and tensor.shape[-1] != int(metadata["ref_audio_t"])):
                raise ValueError("audio latent length does not match the manifest")
        elif modality == "video":
            if tensor.ndim != 5 or tensor.shape[0] != 1:
                raise ValueError(f"video latent has invalid shape {tuple(tensor.shape)}")
            expected = (int(metadata["latent_h"]), int(metadata["latent_w"]))
            if tuple(tensor.shape[-2:]) != expected:
                raise ValueError(
                    f"video latent is {tuple(tensor.shape[-2:])}, expected {expected}")
            if "latent_t" in metadata and tensor.shape[2] != int(metadata["latent_t"]):
                raise ValueError("video latent length does not match the manifest")
        else:
            raise ValueError(f"unknown cache modality {modality!r}")

    @staticmethod
    def _update_manifest(record_dir, entry, modality, key, metadata, tensor_path):
        path = record_dir / "manifest.json"
        manifest = {
            "cache_schema_version": CACHE_SCHEMA_VERSION,
            "record_id": (entry or {}).get("record_id"),
            "tag": (entry or {}).get("tag") or "external",
            "image": {},
            "audio": {},
            "video": {},
            "qwen": {},
        }
        if path.is_file():
            try:
                current = json.loads(path.read_text(encoding="utf-8"))
                if current.get("cache_schema_version") == CACHE_SCHEMA_VERSION:
                    manifest.update(current)
            except (OSError, json.JSONDecodeError):
                pass
        manifest.setdefault("image", {})
        manifest.setdefault("audio", {})
        manifest.setdefault("video", {})
        manifest.setdefault("qwen", {})
        manifest["tag"] = (entry or {}).get("tag") or manifest.get("tag") or "external"
        manifest[modality][key] = {
            **metadata,
            "file": str(tensor_path.relative_to(record_dir)).replace("\\", "/"),
        }

        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()

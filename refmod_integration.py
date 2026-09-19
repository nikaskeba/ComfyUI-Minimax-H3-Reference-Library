"""Optional RefMod integration for the SKEBA H3 Reference Library.

The standard reference library remains the source of truth for image/audio/video
media. RefMod selection is stored separately so switching modes never destroys
or rewrites the standard reference data.

When a record is in ``refmod`` mode its standard media is masked from the H3
prompt compiler, while its descriptions remain available for semantic prompt
replacement. The selected RefMod is attached to the SKEBA reference bundle as
metadata for downstream RefMod-aware nodes.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from pathlib import Path

import folder_paths
from aiohttp import web
from server import PromptServer

from . import h3_tag_references as h3_refs
from .library import get_record, library_root, list_records, media_path


SETTINGS_LOCK = threading.RLock()
SETTINGS_VERSION = 1
ROUTES_REGISTERED = False
_PATCHED = False


def settings_path() -> Path:
    return library_root() / "refmod_settings.json"


def _default_settings():
    return {"version": SETTINGS_VERSION, "revision": 0, "records": {}}


def read_refmod_settings():
    with SETTINGS_LOCK:
        path = settings_path()
        if not path.exists():
            return _default_settings()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError(f"H3 RefMod settings could not be read: {error}") from error
        if not isinstance(payload, dict) or not isinstance(payload.get("records"), dict):
            raise RuntimeError("H3 RefMod settings are invalid.")
        payload.setdefault("version", SETTINGS_VERSION)
        payload.setdefault("revision", 0)
        return payload


def _write_refmod_settings(payload):
    root = library_root()
    root.mkdir(parents=True, exist_ok=True)
    target = settings_path()
    temporary = target.with_suffix(f".{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def _clean_mode(value):
    value = (value or "standard").strip().lower()
    if value not in ("standard", "refmod"):
        raise ValueError("Reference mode must be 'standard' or 'refmod'.")
    return value


def _clean_refmod_name(value):
    value = (value or "").strip().replace("\\", "/")
    if value.startswith("/") or ".." in value.split("/"):
        raise ValueError("RefMod name must be relative to models/refmods.")
    return value


def get_record_refmod_setting(record_id):
    payload = read_refmod_settings()
    current = payload["records"].get(record_id) or {}
    return {
        "reference_mode": _clean_mode(current.get("reference_mode")),
        "refmod_name": _clean_refmod_name(current.get("refmod_name")),
    }


def set_record_refmod_setting(record_id, reference_mode="standard", refmod_name=""):
    # Make sure the record exists before creating sidecar metadata for it.
    get_record(record_id)
    reference_mode = _clean_mode(reference_mode)
    refmod_name = _clean_refmod_name(refmod_name)
    if reference_mode == "refmod" and not refmod_name:
        raise ValueError("Choose a RefMod before enabling RefMod mode.")
    with SETTINGS_LOCK:
        payload = read_refmod_settings()
        payload["records"][record_id] = {
            "reference_mode": reference_mode,
            "refmod_name": refmod_name,
        }
        payload["revision"] = int(payload.get("revision", 0)) + 1
        _write_refmod_settings(payload)
    return payload["records"][record_id]


def set_tag_refmod_setting(tag, reference_mode="standard", refmod_name=""):
    record = next((item for item in list_records() if item.get("tag") == tag), None)
    if record is None:
        raise ValueError(f"Reference library has no record for tag '{{{tag}}}'.")
    return set_record_refmod_setting(record["id"], reference_mode, refmod_name)


def refmod_revision():
    return int(read_refmod_settings().get("revision", 0))


def _refmod_dirs():
    dirs = []
    try:
        dirs.extend(folder_paths.get_folder_paths("refmods"))
    except Exception:
        pass
    fallback = os.path.join(folder_paths.models_dir, "refmods")
    if fallback not in dirs:
        dirs.append(fallback)
    return dirs


def list_refmods():
    names = set()
    for directory in _refmod_dirs():
        if not os.path.isdir(directory):
            continue
        for root, subdirs, files in os.walk(directory):
            subdirs[:] = [name for name in subdirs if name not in {".git", "__pycache__", "graph_presets"}]
            for filename in files:
                if not filename.lower().endswith(".safetensors"):
                    continue
                relative = os.path.relpath(os.path.join(root, filename), directory)
                names.add(relative[:-len(".safetensors")].replace("\\", "/"))
    return sorted(names, key=str.lower)


def _raw_records_by_tag():
    return {record["tag"]: record for record in list_records()}


def mode_aware_records_by_tag():
    """Return compiler records with native media hidden for RefMod-mode records."""
    records = _raw_records_by_tag()
    settings = read_refmod_settings().get("records", {})
    result = {}
    for tag, source in records.items():
        record = dict(source)
        setting = settings.get(record.get("id"), {})
        mode = _clean_mode(setting.get("reference_mode"))
        record["reference_mode"] = mode
        record["refmod_name"] = _clean_refmod_name(setting.get("refmod_name"))
        if mode == "refmod":
            # Preserve descriptions so deterministic and legacy prompt rewriting
            # still knows what the tag represents, but do not inject standard media.
            record["image_file"] = None
            record["audio_file"] = None
            record["video_file"] = None
            record["video_has_audio"] = False
        result[tag] = record
    return result


def _refmods_used_by_prompt(prompt_template):
    settings = read_refmod_settings().get("records", {})
    raw_records = _raw_records_by_tag()
    ordered_tags = []
    seen = set()
    for match in h3_refs.REFERENCE_RE.finditer(prompt_template or ""):
        tag = match.group("reference") or match.group("voice")
        if not tag or tag in seen:
            continue
        seen.add(tag)
        ordered_tags.append(tag)
    selected = []
    for tag in ordered_tags:
        record = raw_records.get(tag)
        if not record:
            continue
        setting = settings.get(record.get("id"), {})
        if _clean_mode(setting.get("reference_mode")) != "refmod":
            continue
        name = _clean_refmod_name(setting.get("refmod_name"))
        if not name:
            continue
        selected.append({
            "record_id": record["id"],
            "tag": tag,
            "name": name,
            "strength": 1.0,
        })
    return selected


def install_prompt_integration():
    """Patch the existing prompt node without changing its saved workflow schema."""
    global _PATCHED
    if _PATCHED:
        return
    _PATCHED = True

    # h3_tag_references imported records_by_tag directly, so replace the module
    # binding used by H3TaggedReferencePrompt and H3PromptListValidator.
    h3_refs.records_by_tag = mode_aware_records_by_tag

    original_build = h3_refs.H3TaggedReferencePrompt.build
    original_changed = h3_refs.H3TaggedReferencePrompt.IS_CHANGED

    def build_with_refmods(self, prompt_template, *args, **kwargs):
        output = original_build(self, prompt_template, *args, **kwargs)
        if not output or not isinstance(output[-1], dict):
            return output
        bundle = dict(output[-1])
        bundle["refmods"] = _refmods_used_by_prompt(prompt_template)
        bundle["refmod_settings_revision"] = refmod_revision()
        return (*output[:-1], bundle)

    @classmethod
    def changed_with_refmods(cls, prompt_template, *args, **kwargs):
        base = original_changed(prompt_template, *args, **kwargs)
        return f"{base}:refmods={refmod_revision()}"

    h3_refs.H3TaggedReferencePrompt.build = build_with_refmods
    h3_refs.H3TaggedReferencePrompt.IS_CHANGED = changed_with_refmods


def _error_response(error):
    if isinstance(error, KeyError):
        return web.json_response({"error": "Reference record was not found."}, status=404)
    if isinstance(error, (ValueError, FileNotFoundError)):
        return web.json_response({"error": str(error)}, status=400)
    return web.json_response({"error": f"RefMod integration error: {error}"}, status=500)


def register_refmod_routes():
    global ROUTES_REGISTERED
    if ROUTES_REGISTERED:
        return
    ROUTES_REGISTERED = True
    routes = PromptServer.instance.routes

    @routes.get("/api/h3-references/refmod-settings")
    async def get_refmod_settings(request):
        del request
        payload = read_refmod_settings()
        valid_ids = {record["id"] for record in list_records()}
        settings = {
            record_id: {
                "reference_mode": _clean_mode(value.get("reference_mode")),
                "refmod_name": _clean_refmod_name(value.get("refmod_name")),
            }
            for record_id, value in payload.get("records", {}).items()
            if record_id in valid_ids
        }
        return web.json_response({
            "revision": payload.get("revision", 0),
            "records": settings,
            "mods": list_refmods(),
        })

    @routes.put("/api/h3-references/records/{record_id}/refmod")
    async def update_refmod_setting(request):
        try:
            payload = await request.json()
            setting = set_record_refmod_setting(
                request.match_info["record_id"],
                payload.get("reference_mode", "standard"),
                payload.get("refmod_name", ""),
            )
            return web.json_response({"setting": setting, "revision": refmod_revision()})
        except Exception as error:
            return _error_response(error)

    @routes.get("/api/h3-references/refmods")
    async def get_refmods(request):
        del request
        return web.json_response({"mods": list_refmods()})

    @routes.get("/h3-refmod-integration/static/refmod.js")
    async def refmod_manager_script(request):
        del request
        return web.FileResponse(Path(__file__).parent / "manager" / "refmod.js")


class _AnyType(str):
    def __ne__(self, _value):
        return False


ANY_TYPE = _AnyType("*")


def _external_node(name):
    import nodes
    node = nodes.NODE_CLASS_MAPPINGS.get(name)
    if node is None:
        raise RuntimeError(
            "ComfyUI-MiniMaxH3Mod is required for RefMod execution. Install/update "
            "Luisacaotica/ComfyUI-MiniMaxH3Mod and restart ComfyUI.")
    return node


def _source_records():
    return [
        record for record in list_records()
        if record.get("image_file") or record.get("video_file")
    ]


class SkebaCreateH3RefModFromLibrary:
    """Create a visual RefMod directly from a managed SKEBA library record."""

    @classmethod
    def INPUT_TYPES(cls):
        tags = sorted((record["tag"] for record in _source_records()), key=str.lower)
        if not tags:
            tags = ["(no visual references saved)"]
        return {
            "required": {
                "tag": (tags,),
                "vae": ("VAE",),
                "name": ("STRING", {"default": "library_refmod"}),
                "mode": (["encode", "training"], {"default": "encode"}),
                "ref_resolution": ("INT", {"default": 1024, "min": 256, "max": 4096, "step": 32}),
                "latent_frames": ("INT", {"default": 16, "min": 1, "max": 240, "step": 1}),
                "max_tokens": ("INT", {"default": 5120, "min": 0, "max": 2147483647, "step": 512}),
                "concept_type": (["generic", "identity", "style", "motion"], {"default": "identity"}),
            },
            "optional": {
                "pool_h": ("INT", {"default": 16, "min": 1, "max": 128, "step": 1}),
                "pool_w": ("INT", {"default": 16, "min": 1, "max": 128, "step": 1}),
                "refinement_steps": ("INT", {"default": 150, "min": 0, "max": 2000, "step": 10}),
                "description": ("STRING", {"multiline": True, "default": ""}),
                "enable_after_create": ("BOOLEAN", {"default": True}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("status",)
    FUNCTION = "create"
    OUTPUT_NODE = True
    CATEGORY = "Skeba AI Nodes - Reference"
    DESCRIPTION = (
        "Create and save a MiniMax H3 RefMod from a visual record already stored in the "
        "SKEBA Reference Library. The standard image/video is preserved."
    )

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def create(self, tag, vae, name="library_refmod", mode="encode",
               ref_resolution=1024, latent_frames=16, max_tokens=5120,
               concept_type="identity", pool_h=16, pool_w=16,
               refinement_steps=150, description="", enable_after_create=True):
        record = next((item for item in list_records() if item.get("tag") == tag), None)
        if record is None:
            raise ValueError(f"Reference library has no record for tag '{{{tag}}}'.")
        extractor = _external_node("MiniMaxH3RefModExtract")
        refs_image = None
        refs_video = None
        if record.get("video_file"):
            frames, _audio = h3_refs.load_video(media_path(record, "video"))
            refs_video = {"ref_video_1": frames}
        elif record.get("image_file"):
            image = h3_refs.load_image(media_path(record, "image"))
            refs_image = {"ref_image_1": image}
        else:
            raise ValueError("This library record has no image or video to encode as a visual RefMod.")

        # The upstream node saves the safetensors file. Its NodeOutput is not
        # forwarded because this SKEBA helper is an output/action node whose job
        # is library creation + binding; use SKEBA Apply H3 RefMod for generation.
        extractor.execute(
            name=name,
            mode=mode,
            refs_image=refs_image,
            refs_video=refs_video,
            vae=vae,
            ref_resolution=int(ref_resolution),
            pool_h=int(pool_h),
            pool_w=int(pool_w),
            latent_frames=int(latent_frames),
            identity=int(refinement_steps),
            max_tokens=int(max_tokens),
            description=(description or record.get("image_description") or record.get("video_description") or tag),
            save=True,
            concept_type=concept_type,
            extraction_preset="manual",
            budget_policy="truncate",
        )
        if enable_after_create:
            set_record_refmod_setting(record["id"], "refmod", name)
        else:
            current = get_record_refmod_setting(record["id"])
            set_record_refmod_setting(record["id"], current["reference_mode"], name)
        status = (
            f"Created RefMod '{name}' from {{{tag}}}. Standard reference media was preserved. "
            + ("RefMod mode enabled." if enable_after_create else "RefMod saved but Standard mode kept.")
        )
        return {"ui": {"text": [status]}, "result": (status,)}


class SkebaApplyH3RefMod:
    """SKEBA-category alias of the upstream Apply H3 RefMod node."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "conditioning": (ANY_TYPE,),
                "mods": ("H3_REF_MODS",),
                "retention": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "curve_direction": (["constant", "concept_at_start", "concept_at_end", "concept_at_middle", "concept_at_ends"], {"default": "constant"}),
                "curve_shape": (["linear", "ease", "sigmoid", "tanh", "quadratic", "cubic", "exponential", "stair", "elastic", "bump", "dip"], {"default": "linear"}),
                "curve_value": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "override": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "scramble_seed": ("INT", {"default": -1, "min": -1, "max": 2147483647}),
            },
        }

    RETURN_TYPES = (ANY_TYPE, "IMAGE")
    RETURN_NAMES = ("conditioning", "curve_graph")
    FUNCTION = "apply"
    CATEGORY = "Skeba AI Nodes - Reference"
    DESCRIPTION = "Apply MiniMax H3 RefMods from the SKEBA node folder. Delegates to ComfyUI-MiniMaxH3Mod."

    def apply(self, conditioning, mods, retention=1.0, curve_direction="constant",
              curve_shape="linear", curve_value=1.0, override=False, scramble_seed=-1):
        upstream = _external_node("MiniMaxH3RefModApply")
        # Modern ComfyUI understands the upstream io.NodeOutput directly.
        return upstream.execute(
            conditioning=conditioning,
            mods=mods,
            retention=retention,
            curve_direction=curve_direction,
            curve_shape=curve_shape,
            curve_value=curve_value,
            override=override,
            scramble_seed=scramble_seed,
        )


install_prompt_integration()
register_refmod_routes()

import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import folder_paths


TAG_RE = re.compile(r"^[A-Za-z0-9_-]+$")
REFERENCE_TYPES = ("character", "location", "object", "music", "uncategorized")
LIBRARY_LOCK = threading.RLock()


def library_root():
    return Path(folder_paths.get_user_directory()) / "h3_reference_library"


def manifest_path():
    return library_root() / "library.json"


def image_directory():
    return library_root() / "images"


def audio_directory():
    return library_root() / "audio"


def ensure_library():
    image_directory().mkdir(parents=True, exist_ok=True)
    audio_directory().mkdir(parents=True, exist_ok=True)
    if not manifest_path().exists():
        _write_manifest({"version": 1, "revision": 0, "records": []})


def clean_tag(tag):
    tag = (tag or "").strip()
    if tag.startswith("{") and tag.endswith("}"):
        tag = tag[1:-1].strip()
    if not tag or not TAG_RE.fullmatch(tag):
        raise ValueError("Tag must contain only letters, numbers, '_' or '-'.")
    return tag


def clean_category(category):
    category = (category or "other").strip().lower().replace(" ", "_")
    if not TAG_RE.fullmatch(category):
        raise ValueError("Category must contain only letters, numbers, '_' or '-'.")
    return category


def clean_reference_type(reference_type):
    reference_type = (reference_type or "uncategorized").strip().lower()
    if reference_type not in REFERENCE_TYPES:
        choices = ", ".join(REFERENCE_TYPES)
        raise ValueError(f"Reference type must be one of: {choices}.")
    return reference_type


def read_manifest():
    with LIBRARY_LOCK:
        ensure_library()
        try:
            with manifest_path().open("r", encoding="utf-8") as handle:
                manifest = json.load(handle)
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError(f"H3 reference library could not be read: {error}") from error

        if not isinstance(manifest, dict) or not isinstance(manifest.get("records"), list):
            raise RuntimeError("H3 reference library manifest is invalid.")
        manifest.setdefault("version", 1)
        manifest.setdefault("revision", 0)
        for record in manifest["records"]:
            if not isinstance(record, dict):
                raise RuntimeError("H3 reference library manifest contains an invalid record.")
            if record.get("reference_type") not in REFERENCE_TYPES:
                record["reference_type"] = "uncategorized"
        return manifest


def library_revision():
    return read_manifest()["revision"]


def list_records():
    return read_manifest()["records"]


def records_by_tag():
    return {record["tag"]: record for record in list_records()}


def get_record(record_id):
    for record in list_records():
        if record["id"] == record_id:
            return record
    raise KeyError(record_id)


def create_record(tag, category="other", image_description="", audio_description="", image_file=None,
                  audio_file=None, reference_type="uncategorized"):
    tag = clean_tag(tag)
    category = clean_category(category)
    reference_type = clean_reference_type(reference_type)
    if image_file is None and audio_file is None:
        raise ValueError("A reference record needs an image, audio clip, or both.")

    with LIBRARY_LOCK:
        manifest = read_manifest()
        _require_unique_tag(manifest["records"], tag)
        now = _timestamp()
        record = {
            "id": uuid.uuid4().hex,
            "tag": tag,
            "category": category,
            "reference_type": reference_type,
            "image_description": (image_description or "").strip(),
            "audio_description": (audio_description or "").strip(),
            "image_file": image_file,
            "audio_file": audio_file,
            "created_at": now,
            "updated_at": now,
        }
        manifest["records"].append(record)
        _commit(manifest)
        return record


def update_record(record_id, tag, category="other", image_description="", audio_description="", image_file=None,
                  audio_file=None, remove_image=False, remove_audio=False,
                  reference_type="uncategorized"):
    tag = clean_tag(tag)
    category = clean_category(category)
    reference_type = clean_reference_type(reference_type)
    with LIBRARY_LOCK:
        manifest = read_manifest()
        record = next((item for item in manifest["records"] if item["id"] == record_id), None)
        if record is None:
            raise KeyError(record_id)
        _require_unique_tag(manifest["records"], tag, record_id)

        old_image = record.get("image_file")
        old_audio = record.get("audio_file")
        next_image = image_file if image_file is not None else (None if remove_image else old_image)
        next_audio = audio_file if audio_file is not None else (None if remove_audio else old_audio)
        if next_image is None and next_audio is None:
            raise ValueError("A reference record needs an image, audio clip, or both.")

        record.update({
            "tag": tag,
            "category": category,
            "reference_type": reference_type,
            "image_description": (image_description or "").strip(),
            "audio_description": (audio_description or "").strip(),
            "image_file": next_image,
            "audio_file": next_audio,
            "updated_at": _timestamp(),
        })
        _commit(manifest)
        return record, old_image if old_image != next_image else None, old_audio if old_audio != next_audio else None


def delete_record(record_id):
    with LIBRARY_LOCK:
        manifest = read_manifest()
        record = next((item for item in manifest["records"] if item["id"] == record_id), None)
        if record is None:
            raise KeyError(record_id)
        manifest["records"] = [item for item in manifest["records"] if item["id"] != record_id]
        _commit(manifest)
        return record


def media_path(record, kind):
    if kind not in ("image", "audio"):
        raise ValueError("Unknown media kind.")
    filename = record.get(f"{kind}_file")
    if not filename or Path(filename).name != filename:
        raise FileNotFoundError(f"Record has no valid {kind} file.")
    root = image_directory() if kind == "image" else audio_directory()
    resolved = (root / filename).resolve()
    if os.path.commonpath((str(root.resolve()), str(resolved))) != str(root.resolve()):
        raise ValueError("Managed media path is outside the library.")
    if not resolved.is_file():
        raise FileNotFoundError(f"Managed {kind} file is missing for tag '{record['tag']}'.")
    return resolved


def remove_media(filename, kind):
    if not filename:
        return
    try:
        record = {"tag": "deleted", f"{kind}_file": filename}
        media_path(record, kind).unlink()
    except FileNotFoundError:
        pass


def _require_unique_tag(records, tag, current_id=None):
    duplicate = next((item for item in records if item["tag"] == tag and item["id"] != current_id), None)
    if duplicate is not None:
        raise ValueError(f"Tag '{tag}' already exists.")


def _commit(manifest):
    manifest["revision"] = int(manifest.get("revision", 0)) + 1
    _write_manifest(manifest)


def _write_manifest(manifest):
    root = library_root()
    root.mkdir(parents=True, exist_ok=True)
    target = manifest_path()
    temporary = target.with_suffix(f".{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, ensure_ascii=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def _timestamp():
    return datetime.now(timezone.utc).isoformat()

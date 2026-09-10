import functools
import hashlib
import json
import os
import re
import threading
import uuid
from collections import Counter
from pathlib import Path


CATALOG_PATH = Path(__file__).with_name("built_in_references.md")
FOLDER_RE = re.compile(r"^##\s+Folder:\s+`([^`]+)`(?:\s+\((.*?)\))?")
CLIP_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
TAG_RE = re.compile(r"(?P<marker>[\^~])(?P<value>[^\^~\r\n]+?)(?P=marker)")
ATTACHMENT_LOCK = threading.RLock()


def catalog_revision():
    stat = CATALOG_PATH.stat()
    return f"{stat.st_mtime_ns}:{stat.st_size}"


def _attachment_manifest_path():
    import folder_paths
    return Path(folder_paths.get_user_directory()) / "h3_reference_library" / "built_in_images.json"


def _read_attachment_manifest():
    with ATTACHMENT_LOCK:
        path = _attachment_manifest_path()
        if not path.exists():
            return {"version": 2, "revision": 0, "images": {}, "image_contexts": {}}
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError(f"Built-in image manifest could not be read: {error}") from error
        if not isinstance(manifest, dict) or not isinstance(manifest.get("images"), dict):
            raise RuntimeError("Built-in image manifest is invalid.")
        if not isinstance(manifest.get("image_contexts", {}), dict):
            raise RuntimeError("Built-in image-context manifest is invalid.")
        manifest["version"] = 2
        manifest.setdefault("revision", 0)
        manifest.setdefault("image_contexts", {})
        return manifest


def _write_attachment_manifest(manifest):
    path = _attachment_manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, ensure_ascii=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def built_in_images_revision():
    manifest = _read_attachment_manifest()
    return int(manifest.get("revision", 0))


def built_in_attachment_id(record):
    value = library_built_in_tag_value(record)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def built_in_image_filename(record):
    return _read_attachment_manifest()["images"].get(library_built_in_tag_value(record))


def built_in_image_context(record):
    manifest = _read_attachment_manifest()
    return manifest.get("image_contexts", {}).get(
        library_built_in_tag_value(record), "")


def set_built_in_image(record, filename):
    if not filename or Path(filename).name != filename:
        raise ValueError("Built-in character image filename is invalid.")
    with ATTACHMENT_LOCK:
        manifest = _read_attachment_manifest()
        tag = library_built_in_tag_value(record)
        previous = manifest["images"].get(tag)
        manifest["images"][tag] = filename
        manifest["revision"] = int(manifest.get("revision", 0)) + 1
        _write_attachment_manifest(manifest)
        return previous


def set_built_in_image_context(record, description):
    with ATTACHMENT_LOCK:
        manifest = _read_attachment_manifest()
        tag = library_built_in_tag_value(record)
        if not manifest["images"].get(tag):
            raise ValueError(
                "Attach an image before adding built-in character image context.")
        description = (description or "").strip()
        contexts = manifest.setdefault("image_contexts", {})
        if description:
            contexts[tag] = description
        else:
            contexts.pop(tag, None)
        manifest["revision"] = int(manifest.get("revision", 0)) + 1
        _write_attachment_manifest(manifest)
        return description


def remove_built_in_image(record):
    with ATTACHMENT_LOCK:
        manifest = _read_attachment_manifest()
        tag = library_built_in_tag_value(record)
        previous = manifest["images"].pop(tag, None)
        manifest.setdefault("image_contexts", {}).pop(tag, None)
        if previous is not None:
            manifest["revision"] = int(manifest.get("revision", 0)) + 1
            _write_attachment_manifest(manifest)
        return previous


def _plain_name(value):
    value = value.strip()
    if value.startswith("**") and value.endswith("**"):
        value = value[2:-2]
    return value.strip()


def _split_row(line):
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


@functools.lru_cache(maxsize=4)
def _parse_catalog(revision):
    del revision
    records = []
    current_folder = None
    current_status = ""
    for line_number, line in enumerate(
            CATALOG_PATH.read_text(encoding="utf-8").splitlines(), start=1):
        folder_match = FOLDER_RE.match(line)
        if folder_match:
            current_folder = folder_match.group(1).strip()
            current_status = (folder_match.group(2) or current_folder).strip()
            continue
        if not line.startswith("|") or current_folder is None:
            continue
        cells = _split_row(line)
        if len(cells) != 5:
            raise ValueError(
                f"Built-in reference catalog line {line_number} must have five columns.")
        if cells[0] == "Character / Subject Name" or cells[0].startswith(":---"):
            continue
        name = _plain_name(cells[0])
        if not name:
            raise ValueError(
                f"Built-in reference catalog line {line_number} has no character name.")
        clips = [
            {"filename": match.group(1).strip("`"), "path": match.group(2)}
            for match in CLIP_RE.finditer(cells[3])
        ]
        records.append({
            "name": name,
            "actor": cells[1],
            "franchise": cells[2],
            "folder": current_folder,
            "status": current_status,
            "clips": clips,
            "date_added": cells[4],
        })

    seen = set()
    for record in records:
        key = (
            record["name"].casefold(),
            record["actor"].casefold(),
            record["franchise"].casefold(),
        )
        if key in seen:
            raise ValueError(
                f"Built-in reference catalog repeats '{record['name']}' with "
                f"{record['actor']} in {record['franchise']}.")
        seen.add(key)
    return tuple(records)


def _with_tags(records):
    records = [dict(record) for record in records]
    name_counts = Counter(record["name"].casefold() for record in records)
    for record in records:
        tag = record["name"]
        if name_counts[record["name"].casefold()] > 1:
            qualifiers = [value for value in (record["actor"], record["franchise"]) if value]
            tag = " | ".join((tag, *qualifiers))
        record["tag"] = tag
    return records


def list_built_in_references():
    return _with_tags(_parse_catalog(catalog_revision()))


def built_in_tag(record):
    value = record.get("tag", record["name"]) if isinstance(record, dict) else record
    return f"^{value}^"


def built_in_voice_tag(record):
    value = record.get("tag", record["name"]) if isinstance(record, dict) else record
    return f"~{value}~"


def library_built_in_tag_value(record):
    """Namespaced tag used when built-ins appear in Reference Library."""
    value = record.get("tag", record["name"]) if isinstance(record, dict) else record
    return f"{value}_BC"


def library_built_in_tag(record):
    return f"{{{library_built_in_tag_value(record)}}}"


def library_built_in_voice_tag(record):
    return f"§{library_built_in_tag_value(record)}§"


def _description(record):
    parts = [record["name"]]
    if record["actor"]:
        parts.append(f"played by {record['actor']}")
    if record["franchise"]:
        parts.append(f"featured on {record['franchise']}")
    return " ".join(parts)


def _voice_description(record):
    description = f"in {record['name']}'s voice"
    if record["actor"]:
        description += f" as played by {record['actor']}"
    return description


def library_built_in_records():
    """Expose catalog characters as H3 Reference Library records."""
    manifest = _read_attachment_manifest()
    attachments = manifest["images"]
    image_contexts = manifest.get("image_contexts", {})
    result = {}
    for record in list_built_in_references():
        tag = library_built_in_tag_value(record)
        result[tag] = {
            "id": f"built-in:{tag}",
            "tag": tag,
            "category": "built-in-characters",
            "reference_type": "character",
            "image_description": (
                f"{_description(record)}. Image context: {image_contexts[tag]}"
                if attachments.get(tag) and image_contexts.get(tag)
                else _description(record)
            ),
            "image_context": image_contexts.get(tag, "") if attachments.get(tag) else "",
            "audio_description": _voice_description(record),
            "image_file": attachments.get(tag),
            "audio_file": None,
            "video_file": None,
            "video_has_audio": False,
            "built_in": True,
            "name": record["name"],
            "actor": record["actor"],
            "franchise": record["franchise"],
        }
    return result


def resolve_built_in_prompt(prompt_template, records=None):
    records = _with_tags(records) if records is not None else list_built_in_references()
    by_tag = {record["tag"].casefold(): record for record in records}
    by_name = {}
    for record in records:
        by_name.setdefault(record["name"].casefold(), []).append(record)
    used = []
    seen = set()

    def replace(match):
        marker = match.group("marker")
        requested = match.group("value").strip()
        record = by_tag.get(requested.casefold())
        if record is None:
            matches = by_name.get(requested.casefold(), [])
            if len(matches) > 1:
                raise ValueError(
                    f"Built-in H3 reference '{requested}' has multiple portrayals. "
                    "Copy the actor-specific tag from the character database.")
            raise ValueError(
                f"Built-in H3 reference catalog has no character '{requested}'.")
        key = (marker, record["tag"].casefold())
        if key not in seen:
            seen.add(key)
            used.append((marker, record))
        return _voice_description(record) if marker == "~" else _description(record)

    prompt = TAG_RE.sub(replace, prompt_template)
    mapping = "\n".join(
        f"{built_in_voice_tag(record) if marker == '~' else built_in_tag(record)} -> "
        f"{_voice_description(record) if marker == '~' else _description(record)}"
        for marker, record in used
    )
    return prompt, mapping


class H3BuiltInReference:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt_template": ("STRING", {
                    "multiline": True,
                    "default": "[Shot 1] ^Abby Sciuto^ works at her desk.",
                    "tooltip": "Use character tags such as ^Abby Sciuto^ or voice tags such as ~Abby Sciuto~.",
                }),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("prompt", "mapping")
    FUNCTION = "build"
    CATEGORY = "Skeba AI Nodes - Reference"
    DESCRIPTION = "Expand bundled MiniMax H3 character and voice tags into prompt descriptions."

    @classmethod
    def IS_CHANGED(cls, prompt_template):
        return f"{catalog_revision()}:{prompt_template}"

    def build(self, prompt_template):
        return resolve_built_in_prompt(prompt_template or "")

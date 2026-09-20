"""RefMod discovery and library source selection; does not load latent tensors."""
import hashlib
import json
import re
from pathlib import Path

import folder_paths
from safetensors import safe_open, SafetensorError


def roots():
    registered = folder_paths.get_folder_paths("refmods") if "refmods" in folder_paths.folder_names_and_paths else []
    return list(dict.fromkeys(Path(p).resolve() for p in [*registered, Path(folder_paths.models_dir) / "refmods"]))


def read_meta(stem):
    with safe_open(str(stem) + ".safetensors", framework="pt", device="cpu") as handle:
        metadata = handle.metadata() or {}
        raw = metadata.get("refmod_meta") or metadata.get("audio_refmod_meta")
        meta = json.loads(raw) if raw else None
    if meta is None and Path(str(stem) + ".json").is_file():
        meta = json.loads(Path(str(stem) + ".json").read_text(encoding="utf-8"))
    if not isinstance(meta, dict):
        raise ValueError("RefMod has no valid metadata: " + str(stem))
    return meta, {}


def bundle_members(meta):
    return meta.get("members", []) if meta.get("kind") == "bundle" else []


def resolve(selection):
    name = selection.get("file", "")
    relative = Path(name)
    if not name or relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Select a RefMod inside a registered refmods folder.")
    for root in roots():
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            continue
        if path.suffix == ".safetensors" and path.is_file():
            meta, _ = read_meta(str(path.with_suffix("")))
            member = selection.get("member")
            if meta.get("kind") == "bundle":
                members = bundle_members(meta)
                if not isinstance(member, int) or isinstance(member, bool) or not 0 <= member < len(members):
                    raise ValueError(f"Select a member of RefMod bundle {name}.")
                meta = members[member]
            elif member is not None:
                raise ValueError(f"{name} is not a RefMod bundle.")
            return path, meta
    raise ValueError(f"RefMod file not found: {name}")


def selection_fields(values):
    result = {}
    for channel in ("appearance", "voice"):
        source = values.get(channel + "_source", "media")
        selection = values.get(channel + "_refmod")
        if source not in ("media", "refmod"):
            raise ValueError("Reference source must be media or refmod.")
        if selection is not None:
            if not isinstance(selection, dict):
                raise ValueError("RefMod attachment must specify a file and optional member.")
            selection = {"file": str(selection.get("file", "")), "member": selection.get("member")}
        if source == "refmod":
            if selection is None:
                raise ValueError(f"Select the {channel} RefMod.")
            _, meta = resolve(selection)
            allowed = ("audio",) if channel == "voice" else ("image", "video")
            if meta.get("kind") not in allowed:
                raise ValueError(f"Invalid {channel} RefMod kind: {meta.get('kind')}")
        result[channel + "_source"] = source
        result[channel + "_refmod"] = selection
    return result


def direct_refmod_records(records, prompt):
    """Resolve filename-based _rm tags without changing the saved library."""
    requested = {a or b for a,b in re.findall(r"\{([^{}]+_rm)\}|§([^§]+_rm)§", prompt)} - records.keys()
    if not requested:
        return records
    groups = {}
    for row in catalog():
        stem = row["file"][:-len(".safetensors")]
        key = re.sub(r"_(visual|video|audio)$", "", stem, flags=re.IGNORECASE) if row["member"] is None else stem
        groups.setdefault(key, []).append(row)
    result = dict(records)
    for tag in requested:
        name = tag[:-3]
        matches = [key for key in groups if key == name or ("/" not in name and key.rsplit("/",1)[-1] == name)]
        if not matches:
            raise ValueError(f"REFMOD_NOT_FOUND: {tag}; use the RefMod filename without .safetensors, followed by _rm.")
        if len(matches) != 1:
            raise ValueError(f"AMBIGUOUS_REFMOD: {tag}; include the folder in the tag.")
        rows = groups[matches[0]]
        record = {"id":"refmod:"+matches[0], "tag":tag, "reference_type":"character"}
        for channel,kinds in (("appearance",("image","video")),("voice",("audio",))):
            choices = [row for row in rows if row["kind"] in kinds]
            if channel == "voice" and "§"+tag+"§" not in prompt:
                continue
            if len(choices)>1:
                raise ValueError(f"AMBIGUOUS_REFMOD: {tag} has multiple {channel} members; select one through a library entry.")
            if choices:
                row=choices[0]
                record[channel+"_source"]="refmod"
                record[channel+"_refmod"]={"file":row["file"],"member":row["member"]}
                record["audio_description" if channel=="voice" else "image_description"]=row.get("voice_description" if channel=="voice" else "appearance") or row.get("description") or row.get("name") or name
        if "§"+tag+"§" in prompt and "voice_refmod" not in record:
            raise ValueError(f"REFMOD_VOICE_MISSING: {tag} has no audio member.")
        if not record.get("appearance_refmod") and not record.get("voice_refmod"):
            raise ValueError(f"REFMOD_INVALID: {tag} has no usable reference member.")
        result[tag]=record
    return result


def project_records(records, prompt):
    """Expose selected RefMod modalities to the existing tag/ownership resolver."""
    records = direct_refmod_records(records, prompt)
    result = dict(records)
    for tag, original in records.items():
        if "{" + tag + "}" not in prompt and "§" + tag + "§" not in prompt:
            continue
        record = dict(original)
        for channel in ("appearance", "voice"):
            if record.get(channel + "_source", "media") != "refmod":
                continue
            # Silent characters need no voice file access or validation.
            if channel == "voice" and "§" + tag + "§" not in prompt:
                record["audio_file"] = None
                continue
            selection = record.get(channel + "_refmod")
            fields = selection_fields({channel + "_source": "refmod", channel + "_refmod": selection})
            path, meta = resolve(fields[channel + "_refmod"])
            if channel == "appearance":
                record.update(image_file=None, video_file=None, video_has_audio=False)
            kind = meta["kind"]
            record[kind + "_file"] = "refmod:" + str(path)
            record["_refmod_" + kind] = {"file": selection["file"], "member": selection.get("member"),
                                        "path": str(path), "kind": kind, "channel": channel}
        result[tag] = record
    return result


def revision():
    stamps = []
    for root in roots():
        if root.is_dir():
            for path in sorted(root.rglob("*")):
                if path.suffix in (".safetensors", ".json") and path.is_file():
                    stat = path.stat()
                    stamps.append((str(path), stat.st_size, stat.st_mtime_ns))
    return hashlib.sha256(repr(stamps).encode()).hexdigest()


def preview_path(path):
    """Prefer an exact sidecar, then the shared visual/audio pair thumbnail."""
    stems = [path.stem]
    shared = re.sub(r"_(visual|video|audio)$", "", path.stem, flags=re.IGNORECASE)
    if shared != path.stem:
        stems.append(shared)
    for stem in stems:
        for extension in (".png", ".jpg", ".jpeg", ".webp"):
            candidate = path.with_name(stem + extension)
            if candidate.is_file() and candidate.resolve().parent == path.resolve().parent:
                return candidate
    return None


def catalog():
    found = {}
    for root in roots():
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.safetensors")):
            name = path.relative_to(root).as_posix()
            if name in found or not path.resolve().is_relative_to(root):
                continue
            try:
                meta, _ = read_meta(str(path.with_suffix("")))
            except (OSError, ValueError, SafetensorError) as error:
                found[name] = [{"file": name, "member": None, "kind": "invalid", "name": path.stem, "error": str(error), "token_count": 0, "preview": False}]
                continue
            members = bundle_members(meta)
            entries = list(enumerate(members)) if meta.get("kind") == "bundle" else [(None, meta)]
            found[name] = [{"file": name, "member": member, "kind": row.get("kind"),
                            "name": row.get("name", path.stem),
                            **{key: row.get(key) for key in ("mode", "latent_t", "latent_h", "latent_w", "description", "subject_name", "appearance", "voice_description")},
                            "token_count": 2 * int(row.get("latent_t", 1)) if row.get("kind") == "audio" else
                            int(row.get("latent_t", 1)) * (int(row.get("latent_h", 0)) // 2) * (int(row.get("latent_w", 0)) // 2),
                            "preview": preview_path(path) is not None}
                           for member, row in entries]
    return [entry for entries in found.values() for entry in entries]


def delete_files(selections):
    """Delete only explicitly selected assets; preserve shared thumbnails and sources."""
    if not isinstance(selections, list) or not selections:
        raise ValueError("Select RefMod files to delete.")
    paths = list(dict.fromkeys(resolve(selection)[0] for selection in selections))
    for path in paths:
        path.unlink()
    return [selection["file"] for selection in selections]

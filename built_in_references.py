import functools
import re
from collections import Counter
from pathlib import Path


CATALOG_PATH = Path(__file__).with_name("built_in_references.md")
FOLDER_RE = re.compile(r"^##\s+Folder:\s+`([^`]+)`(?:\s+\((.*?)\))?")
CLIP_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
TAG_RE = re.compile(r"\^([^\^\r\n]+?)\^")


def catalog_revision():
    stat = CATALOG_PATH.stat()
    return f"{stat.st_mtime_ns}:{stat.st_size}"


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


def _description(record):
    parts = [f"**{record['name']}**"]
    if record["actor"]:
        parts.append(f"played by {record['actor']}")
    if record["franchise"]:
        parts.append(f"featured on {record['franchise']}")
    return " ".join(parts)


def resolve_built_in_prompt(prompt_template, records=None):
    records = _with_tags(records) if records is not None else list_built_in_references()
    by_tag = {record["tag"].casefold(): record for record in records}
    by_name = {}
    for record in records:
        by_name.setdefault(record["name"].casefold(), []).append(record)
    used = []
    seen = set()

    def replace(match):
        requested = match.group(1).strip()
        record = by_tag.get(requested.casefold())
        if record is None:
            matches = by_name.get(requested.casefold(), [])
            if len(matches) > 1:
                raise ValueError(
                    f"Built-in H3 reference '{requested}' has multiple portrayals. "
                    "Copy the actor-specific tag from the character database.")
            raise ValueError(
                f"Built-in H3 reference catalog has no character '{requested}'.")
        key = record["tag"].casefold()
        if key not in seen:
            seen.add(key)
            used.append(record)
        return _description(record)

    prompt = TAG_RE.sub(replace, prompt_template)
    mapping = "\n".join(
        f"{built_in_tag(record)} -> {_description(record)}"
        for record in used
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
                    "tooltip": "Use caret tags copied from the Built-In Characters catalog, such as ^Abby Sciuto^.",
                }),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("prompt", "mapping")
    FUNCTION = "build"
    CATEGORY = "video/text"
    DESCRIPTION = "Expand bundled MiniMax H3 character tags into actor and franchise descriptions."

    @classmethod
    def IS_CHANGED(cls, prompt_template):
        return f"{catalog_revision()}:{prompt_template}"

    def build(self, prompt_template):
        return resolve_built_in_prompt(prompt_template or "")

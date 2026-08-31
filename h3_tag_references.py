import re

import numpy as np
import torch
from PIL import Image, ImageOps

import comfy.model_management
from comfy_extras.nodes_audio import load as load_audio_file

from .library import library_revision, media_path, records_by_tag


MAX_IMAGES = 9
MAX_AUDIO = 3
REFERENCE_RE = re.compile(
    r"\{(?P<reference>[A-Za-z0-9_-]+)\}|§(?P<voice>[A-Za-z0-9_-]+)§")


def _description(record, kind, tag):
    return (record.get(f"{kind}_description") or tag).strip().rstrip(".")


def _replacement_description(record, tag):
    if record.get("image_description"):
        return _description(record, "image", tag)
    return _description(record, "audio", tag)


def _picture_replacement(record, tag, image_index=None, audio_index=None):
    if image_index is not None:
        picture = f"<Picture {image_index + 1}>"
        description = (record.get("image_description") or "").strip().rstrip(".")
        return f"{picture} ({description})" if description else picture
    if record.get("audio_file") or record.get("audio_description"):
        return _voice_replacement(record, tag, audio_index)
    return _replacement_description(record, tag)


def _voice_replacement(record, tag, audio_index=None):
    description = (record.get("audio_description") or "").strip().rstrip(".")
    if audio_index is not None:
        audio = f"<Audio {audio_index + 1}>"
        return f"{audio} ({description})" if description else audio
    return description or tag


def _format_tag(kind, tag):
    return f"§{tag}§" if kind == "voice" else f"{{{tag}}}"


def resolve_prompt(prompt_template, records):
    references = []
    reference_tags = []
    seen_references = set()
    seen_reference_tags = set()
    for match in REFERENCE_RE.finditer(prompt_template):
        kind = "voice" if match.group("voice") else "reference"
        tag = match.group(kind)
        reference = (kind, tag)
        if reference not in seen_references:
            seen_references.add(reference)
            references.append(reference)
        if kind == "reference" and tag not in seen_reference_tags:
            seen_reference_tags.add(tag)
            reference_tags.append(tag)

    if not references:
        return prompt_template, "", [], []

    missing = next(((kind, tag) for kind, tag in references if tag not in records), None)
    if missing:
        kind, tag = missing
        raise ValueError(
            f"H3 reference library has no record for tag '{_format_tag(kind, tag)}'.")

    paired_tags = [
        tag for tag in reference_tags
        if records[tag].get("image_file") and records[tag].get("audio_file")
    ]
    image_tags = paired_tags + [
        tag for tag in reference_tags
        if records[tag].get("image_file") and not records[tag].get("audio_file")
    ]
    voice_tags = [tag for kind, tag in references if kind == "voice"]
    voice_audio_tags = [
        tag for tag in voice_tags if records[tag].get("audio_file")
    ]
    paired_audio_tags = [
        tag for tag in reference_tags
        if records[tag].get("image_file") and records[tag].get("audio_file")
        and tag not in voice_audio_tags
    ]
    standalone_audio_tags = [
        tag for tag in reference_tags
        if records[tag].get("audio_file") and not records[tag].get("image_file")
        and tag not in voice_audio_tags
    ]
    audio_candidates = voice_audio_tags + paired_audio_tags + standalone_audio_tags
    audio_tags = audio_candidates[:MAX_AUDIO]
    image_indexes = {tag: index for index, tag in enumerate(image_tags)}
    audio_indexes = {tag: index for index, tag in enumerate(audio_tags)}
    if len(image_tags) > MAX_IMAGES:
        raise ValueError(f"H3 supports at most {MAX_IMAGES} reference images; this prompt uses {len(image_tags)}.")

    def replacement(kind, tag):
        if kind == "voice":
            return _voice_replacement(records[tag], tag, audio_indexes.get(tag))
        return _picture_replacement(
            records[tag], tag, image_indexes.get(tag), audio_indexes.get(tag))

    def replace_tag(match):
        kind = "voice" if match.group("voice") else "reference"
        return replacement(kind, match.group(kind))

    rewritten = REFERENCE_RE.sub(replace_tag, prompt_template).strip()
    mapping = [
        f"{_format_tag(kind, tag)} -> {replacement(kind, tag)}"
        for kind, tag in references
    ]
    return rewritten, "\n".join(mapping), image_tags, audio_tags


def load_image(path):
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        array = np.asarray(image, dtype=np.float32) / 255.0
    tensor = torch.from_numpy(array).unsqueeze(0)
    return tensor.to(
        device=comfy.model_management.intermediate_device(),
        dtype=comfy.model_management.intermediate_dtype(),
    )


def load_audio(path):
    waveform, sample_rate = load_audio_file(str(path))
    return {"waveform": waveform.unsqueeze(0), "sample_rate": sample_rate}


class H3TaggedReferencePrompt:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt_template": ("STRING", {
                    "multiline": True,
                    "default": "[Shot 1] {news_anchor} is sitting at {news_desk}.",
                    "tooltip": "Use reference tags such as {news_anchor} or voice tags such as §news_anchor§.",
                }),
            },
        }

    RETURN_TYPES = ("STRING", "STRING") + ("IMAGE",) * MAX_IMAGES + ("AUDIO",) * MAX_AUDIO
    RETURN_NAMES = (
        ("prompt", "mapping")
        + tuple(f"image_{i}" for i in range(1, MAX_IMAGES + 1))
        + tuple(f"audio_{i}" for i in range(1, MAX_AUDIO + 1))
    )
    FUNCTION = "build"
    CATEGORY = "Skeba AI Nodes - Reference"

    @classmethod
    def IS_CHANGED(cls, prompt_template):
        return f"{library_revision()}:{prompt_template}"

    def build(self, prompt_template):
        records = records_by_tag()
        prompt, mapping, image_tags, audio_tags = resolve_prompt(prompt_template or "", records)

        images = [load_image(media_path(records[tag], "image")) for tag in image_tags]
        audios = [load_audio(media_path(records[tag], "audio")) for tag in audio_tags]
        images.extend([None] * (MAX_IMAGES - len(images)))
        audios.extend([None] * (MAX_AUDIO - len(audios)))
        return (prompt, mapping, *images, *audios)

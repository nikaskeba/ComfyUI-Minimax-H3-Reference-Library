import re

import numpy as np
import torch
from PIL import Image, ImageOps

import comfy.model_management
from comfy_api.latest import InputImpl
from comfy_extras.nodes_audio import load as load_audio_file

from .library import library_revision, media_path, records_by_tag


MAX_IMAGES = 9
MAX_AUDIO = 3
MAX_VIDEOS = 3
VIDEO_FPS = 24.0
REFERENCE_RE = re.compile(
    r"\{(?P<reference>[A-Za-z0-9_-]+)\}|§(?P<voice>[A-Za-z0-9_-]+)§")


def _description(record, kind, tag):
    return (record.get(f"{kind}_description") or tag).strip().rstrip(".")


def _replacement_description(record, tag):
    if record.get("video_description"):
        return _description(record, "video", tag)
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


def _video_replacement(record, tag, video_index=None):
    if video_index is not None:
        video = f"<Video {video_index + 1}>"
        description = (record.get("video_description") or "").strip().rstrip(".")
        return f"{video} ({description})" if description else video
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
        return prompt_template, "", [], [], []

    missing = next(((kind, tag) for kind, tag in references if tag not in records), None)
    if missing:
        kind, tag = missing
        raise ValueError(
            f"H3 reference library has no record for tag '{_format_tag(kind, tag)}'.")

    video_tags = [
        tag for tag in reference_tags if records[tag].get("video_file")
    ]
    if len(video_tags) > MAX_VIDEOS:
        raise ValueError(
            f"H3 supports at most {MAX_VIDEOS} reference videos; "
            f"this prompt uses {len(video_tags)}.")
    video_indexes = {tag: index for index, tag in enumerate(video_tags)}
    video_audio_tags = [
        tag for tag in video_tags if records[tag].get("video_has_audio")
    ]
    video_audio_indexes = {
        tag: index for index, tag in enumerate(video_audio_tags)
    }

    image_reference_tags = [
        tag for tag in reference_tags
        if records[tag].get("image_file") and not records[tag].get("video_file")
    ]
    paired_tags = [
        tag for tag in image_reference_tags
        if records[tag].get("image_file") and records[tag].get("audio_file")
    ]
    image_tags = paired_tags + [
        tag for tag in image_reference_tags
        if records[tag].get("image_file") and not records[tag].get("audio_file")
    ]
    voice_tags = [tag for kind, tag in references if kind == "voice"]
    voice_audio_tags = [
        tag for tag in voice_tags
        if (records[tag].get("audio_file")
            or (records[tag].get("video_has_audio") and tag not in video_indexes))
    ]
    paired_audio_tags = [
        tag for tag in image_reference_tags
        if records[tag].get("image_file") and records[tag].get("audio_file")
        and tag not in voice_audio_tags
    ]
    standalone_audio_tags = [
        tag for tag in reference_tags
        if records[tag].get("audio_file")
        and not records[tag].get("image_file")
        and not records[tag].get("video_file")
        and tag not in voice_audio_tags
    ]
    audio_candidates = voice_audio_tags + paired_audio_tags + standalone_audio_tags
    audio_tags = audio_candidates[:MAX_AUDIO]
    image_indexes = {tag: index for index, tag in enumerate(image_tags)}
    audio_indexes = {
        tag: len(video_audio_tags) + index
        for index, tag in enumerate(audio_tags)
    }
    if len(image_tags) > MAX_IMAGES:
        raise ValueError(f"H3 supports at most {MAX_IMAGES} reference images; this prompt uses {len(image_tags)}.")

    def replacement(kind, tag):
        if kind == "voice":
            audio_index = audio_indexes.get(tag, video_audio_indexes.get(tag))
            return _voice_replacement(records[tag], tag, audio_index)
        if tag in video_indexes:
            return _video_replacement(records[tag], tag, video_indexes[tag])
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
    return rewritten, "\n".join(mapping), image_tags, audio_tags, video_tags


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


def load_video(path):
    components = InputImpl.VideoFromFile(str(path)).get_components()
    images = components.images
    source_fps = float(components.frame_rate)
    if source_fps <= 0:
        raise ValueError(f"Reference video '{path}' has an invalid frame rate.")
    if images.shape[0] < 1:
        raise ValueError(f"Reference video '{path}' contains no decoded frames.")
    if abs(source_fps - VIDEO_FPS) > 1e-6:
        target_count = max(1, int(round(images.shape[0] / source_fps * VIDEO_FPS)))
        positions = torch.arange(target_count, device=images.device, dtype=torch.float64)
        indexes = torch.floor(positions * source_fps / VIDEO_FPS).long()
        indexes = indexes.clamp(max=images.shape[0] - 1)
        images = images[indexes]
    return images, components.audio


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

    # Video outputs are appended so existing image/audio socket indices remain
    # stable when old workflows reload this expanded node.
    RETURN_TYPES = (
        ("STRING", "STRING")
        + ("IMAGE",) * MAX_IMAGES
        + ("AUDIO",) * MAX_AUDIO
        + ("IMAGE",) * MAX_VIDEOS
        + ("AUDIO",) * MAX_VIDEOS
    )
    RETURN_NAMES = (
        ("prompt", "mapping")
        + tuple(f"image_{i}" for i in range(1, MAX_IMAGES + 1))
        + tuple(f"audio_{i}" for i in range(1, MAX_AUDIO + 1))
        + tuple(f"video_{i}" for i in range(1, MAX_VIDEOS + 1))
        + tuple(f"video_audio_{i}" for i in range(1, MAX_VIDEOS + 1))
    )
    FUNCTION = "build"
    CATEGORY = "Skeba AI Nodes - Reference"

    @classmethod
    def IS_CHANGED(cls, prompt_template):
        return f"{library_revision()}:{prompt_template}"

    def build(self, prompt_template):
        records = records_by_tag()
        prompt, mapping, image_tags, audio_tags, video_tags = resolve_prompt(
            prompt_template or "", records)

        images = [load_image(media_path(records[tag], "image")) for tag in image_tags]
        video_media = {}

        def video_for(tag):
            if tag not in video_media:
                video_media[tag] = load_video(media_path(records[tag], "video"))
            return video_media[tag]

        audios = []
        for tag in audio_tags:
            if records[tag].get("audio_file"):
                audios.append(load_audio(media_path(records[tag], "audio")))
            else:
                audio = video_for(tag)[1]
                if audio is None:
                    raise ValueError(
                        f"Reference video '{{{tag}}}' no longer contains an audio track.")
                audios.append(audio)
        videos = [video_for(tag)[0] for tag in video_tags]
        video_audios = [
            video_for(tag)[1] if records[tag].get("video_has_audio") else None
            for tag in video_tags
        ]
        images.extend([None] * (MAX_IMAGES - len(images)))
        audios.extend([None] * (MAX_AUDIO - len(audios)))
        videos.extend([None] * (MAX_VIDEOS - len(videos)))
        video_audios.extend([None] * (MAX_VIDEOS - len(video_audios)))
        return (prompt, mapping, *images, *audios, *videos, *video_audios)

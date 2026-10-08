"""Literal templates for generated Ref2VA prose; never changes reference allocation."""
import hashlib
import json
import re

VERSION = 1
PLACEHOLDER = re.compile(r"\[\[([a-z_]+)\]\]")
# Group and default wording. All fields share the same placeholder vocabulary.
REGISTRY = {
    "subject_definition": ("Subject/media definitions", "[[subject]] is [[description]]."),
    "subject_media": ("Subject/media definitions", " in [[media]]"),
    "subject_description": ("Subject/media definitions", ", [[description]]"),
    "picture_description": ("Subject/media definitions", ". [[picture]]: [[description]]"),
    "video_reference": ("Subject/media definitions", "[[video]] is a whole-video reference.[[description]]"),
    "video_motion_reference": ("Subject/media definitions", "[[video]] is a camera-motion and temporal-structure reference.[[description]]"),
    "video_continuation": ("Subject/media definitions", "[[video]] is the source video whose ending is continued.[[description]]"),
    "video_editing": ("Subject/media definitions", "[[video]] is the source video for the target video edit.[[description]]"),
    "soundtrack_reference": ("Subject/media definitions", "[[audio]] is the synchronized audio track of [[video]] and is referenced without copying the original signal."),
    "soundtrack_reuse": ("Subject/media definitions", "[[audio]] is the synchronized audio track of [[video]] and is reused in the target video."),
    "media_audio_reference": ("Subject/media definitions", "[[audio]] is the [[role]] reference referenced without copying the original signal.[[description]]"),
    "media_audio_reuse": ("Subject/media definitions", "[[audio]] is the [[role]] reference reused in the target video.[[description]]"),
    "voice_reference": ("Voice definitions and dialogue bindings", "[[audio]] is the voice-timbre reference for [[subject]][[speaker]]."),
    "voice_reuse": ("Voice definitions and dialogue bindings", "[[audio]] is the source of the vocal audio reused for [[subject]][[speaker]]."),
    "voice_exclusive_reference": ("Voice definitions and dialogue bindings", " [[audio]] applies exclusively to [[subject]][[speaker]] and provides [[name]]’s vocal timbre and delivery."),
    "voice_exclusive_reuse": ("Voice definitions and dialogue bindings", " [[audio]] applies exclusively to [[subject]][[speaker]]."),
    "voice_characteristics": ("Voice definitions and dialogue bindings", " Voice characteristics: [[voice_description]]"),
    "dialogue_binding_reference": ("Voice definitions and dialogue bindings", ", using the voice identity referenced exclusively from [[audio]],"),
    "dialogue_binding_reuse": ("Voice definitions and dialogue bindings", ", using vocal audio directly reused from [[audio]],"),
    "voice_cue_reference": ("Voice definitions and dialogue bindings", "the recognizable voice timbre referenced from [[audio]]"),
    "voice_cue_reuse": ("Voice definitions and dialogue bindings", "vocal audio directly reused from [[audio]]"),
    "voice_cue_introduction": ("Voice definitions and dialogue bindings", "using [[phrase]]"),
    "text_voice_introduction": ("Voice definitions and dialogue bindings", "in [[description]]"),
    "global_binding": ("Voice definitions and dialogue bindings", "Voice-identity binding is strict and exclusive throughout the target video: [[bindings]]. These mappings never swap, merge, transfer, or influence one another."),
    "summary_editing": ("Summary additions", "The target video is an edited version of [[sources]]."),
    "summary_voice_reference": ("Summary additions", "[[audio]] exclusively provides the voice-timbre reference for [[identity]]."),
    "summary_voice_reuse": ("Summary additions", "[[audio]] supplies vocal audio reused exclusively for [[identity]]."),
    "summary_task_prefix": ("Summary additions", "[[task_prefix]] "),
    "retention_appearances": ("Retention analysis", " (appears in [[shots]])"),
    "retention_subject": ("Retention analysis", "[[subject]][[appearances]]: fully_preserved - the referenced identity, appearance, wardrobe, and defining visual characteristics are retained."),
    "retention_voice_reference": ("Retention analysis", "[[audio]]: reference - its vocal timbre and delivery guide only the dialogue produced by [[identity]], without copying the original audio signal."),
    "retention_voice_reuse": ("Retention analysis", "[[audio]]: reuse - the supplied vocal signal is reused only for [[identity]]."),
}
DEFAULTS = {name: value[1] for name, value in REGISTRY.items()}
PLACEHOLDERS = sorted({token for text in DEFAULTS.values() for token in PLACEHOLDER.findall(text)} |
                      {"subject_number", "subject_label", "speaker_number", "speaker_id", "speaker_tag"})


class CompilerTemplates:
    def __init__(self, text=""):
        self.values = dict(DEFAULTS)
        if text.strip():
            try:
                data = json.loads(text)
            except (ValueError, TypeError) as error:
                raise ValueError(f"COMPILER_TEMPLATE: invalid JSON: {error}") from error
            if not isinstance(data, dict) or set(data) != {"version", "templates"}:
                raise ValueError("COMPILER_TEMPLATE: expected version and templates fields.")
            if type(data["version"]) is not int or data["version"] != VERSION:
                raise ValueError("COMPILER_TEMPLATE: unsupported version; expected 1.")
            overrides = data["templates"]
            if not isinstance(overrides, dict):
                raise ValueError("COMPILER_TEMPLATE: templates must be an object.")
            for name, value in overrides.items():
                if name not in REGISTRY:
                    raise ValueError(f"COMPILER_TEMPLATE: unknown template {name!r}.")
                if not isinstance(value, str):
                    raise ValueError(f"COMPILER_TEMPLATE: {name} must be text.")
                allowed = set(PLACEHOLDERS)
                unknown = set(PLACEHOLDER.findall(value)) - allowed
                remainder = PLACEHOLDER.sub("", value)
                if unknown or "[[" in remainder or "]]" in remainder:
                    raise ValueError(f"COMPILER_TEMPLATE: {name}: invalid placeholder; allowed: {', '.join(sorted(allowed))}.")
                self.values[name] = value
        self.hash = hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()

    def render(self, template, **values):
        return PLACEHOLDER.sub(lambda match: str(values.get(match[1], "")), self.values[template])

    def to_json(self):
        return json.dumps({"version": VERSION, "templates": self.values}, ensure_ascii=False, sort_keys=True)


class SkebaH3CompilerTemplates:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {name: ("STRING", {"default": default, "multiline": True,
            "tooltip": group + " | Placeholders: " + ", ".join(PLACEHOLDERS) + ". Unavailable context is empty; speaker_id = S1, speaker = (S1) with leading space, subject = <Subject 1>."})
            for name, (group, default) in REGISTRY.items()}}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("compiler_templates",)
    FUNCTION = "build"
    CATEGORY = "Skeba AI Nodes - Reference"
    DESCRIPTION = "Edit compiler-generated wording. Connect to the Tagged Reference Prompt and prompt-list validator. Numbering and source ownership stay automatic."

    def build(self, **templates):
        value = CompilerTemplates(json.dumps({"version": VERSION, "templates": templates}))
        return (value.to_json(),)

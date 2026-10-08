"""Queued voice-only RefMod decoding and description; never writes a RefMod."""
import json
import math

import comfy.model_management as mm
from .refmod_studio import members_from_file, _trimmed_source
from .refmod_training import join_audio
from .voice_description import describe_audio


def describe_refmod(settings, audio_vae=None):
    seconds = float(settings.get("audio_seconds", 15))
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("Max voice seconds must be positive.")
    seconds = min(15., seconds)
    clips = []
    action = settings.get("audio_action", "append")
    if settings.get("existing") and settings.get("keep_voice", True) and action in ("append", "keep"):
        selection = settings.get("companion") or settings["existing"]
        _, _, mods = members_from_file(selection)
        selected = selection.get("member")
        voice = mods[selected] if selected is not None and mods[selected].kind == "audio" else next((m for m in mods if m.kind == "audio"), None)
        if voice is not None:
            if audio_vae is None:
                raise ValueError("Connect the H3 audio VAE to RefMod Studio and open its RefMod Library.")
            mm.throw_exception_if_processing_interrupted()
            decoded = audio_vae.decode(voice.latent).detach().float().cpu().movedim(-1, 1)
            rate = int(getattr(audio_vae, "audio_sample_rate_output", getattr(audio_vae, "audio_sample_rate", 32000)))
            clips.append({"waveform": decoded[..., :int(seconds * rate)].clone(), "sample_rate": rate})
    for source in settings.get("sources", []) if action in ("append", "replace") else []:
        if source.get("kind") != "audio" and not (source.get("kind") == "video" and source.get("include_audio")):
            continue
        sections = source.get("sections", [{}])
        if not isinstance(sections, list) or not sections:
            raise ValueError("Choose at least one audio/video section.")
        for section in sections:
            if sum(c["waveform"].shape[-1] / c["sample_rate"] for c in clips) >= seconds:
                break
            mm.throw_exception_if_processing_interrupted()
            item = {**source, **{key: section[key] for key in ("start", "end") if key in section}, "soundtrack_only": True}
            _, audio = _trimmed_source(item)
            remaining = seconds - sum(c["waveform"].shape[-1] / c["sample_rate"] for c in clips)
            clips.append({**audio, "waveform": audio["waveform"][..., :int(remaining * audio["sample_rate"])].clone()})
    if not clips:
        raise ValueError("Upload voice audio or keep a stored RefMod voice first.")
    audio = join_audio(clips)
    audio["waveform"] = audio["waveform"][..., :int(seconds * audio["sample_rate"])]
    return describe_audio(audio)


class SkebaRefModVoiceDescription:
    CATEGORY = "Skeba AI Nodes - Reference"
    RETURN_TYPES = ("STRING",)
    FUNCTION = "describe"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"spec": ("STRING", {"default": "{}"})}, "optional": {"audio_vae": ("VAE",)}}

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def describe(self, spec, audio_vae=None):
        result = describe_refmod(json.loads(spec), audio_vae)
        return {"ui": {"voice_description": [result]}, "result": (result["description"],)}

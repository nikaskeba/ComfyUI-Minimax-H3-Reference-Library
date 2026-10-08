"""Read-only compiler examples for the template editor; no media/model loading."""
from .reference_compiler import compile_prompt


def preview_reference(tag, records, compiler_templates="", audio_usage="reference", video_usage="reference"):
    if tag not in records:
        raise ValueError("The selected reference is no longer available. Refresh references.")
    record = records[tag]
    kind = record.get("reference_type", "character")
    token = "{" + tag + "}"
    if kind == "character":
        detail = f"[Shot 1: 0s] {token} is visible. [Shot 2: 1.0s] {token} says, <d>[English]Hello.</d>"
        sound = "Room tone."
    elif kind in ("music", "voice"):
        detail = "[Shot 1: 0s] An establishing view."
        sound = "§" + tag + "§"
    else:
        detail = f"[Shot 1: 0s] A view of {token}."
        sound = "§" + tag + "§" if kind == "video" and record.get("video_has_audio") else "Room tone."
    prompt = (f"subject_definitions:\n{token}\n\nsummary:\nA short reference preview.\n\n"
              f"detailed_description:\n{detail}\n\noverall_soundscape:\n{sound}\n\nnon_diegetic_music:\nN/A")
    examples = {}
    result = compile_prompt(prompt, records, compiler_templates=compiler_templates,
                            audio_usage=audio_usage, video_usage=video_usage, template_preview=examples)
    return {"examples": examples, "prompt": result.prompt,
            "name": record.get("name") or tag,
            "voice_description": record.get("audio_description") or "",
            "has_audio": bool(record.get("audio_file") or record.get("video_has_audio"))}

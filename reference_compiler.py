"""Deterministic, section-aware H3 reference compilation. No media loading."""
import json
import re
from dataclasses import dataclass, field


SECTIONS = ("subject_definitions", "summary", "retention_analysis", "detailed_description",
            "overall_soundscape", "non_diegetic_music")
REQUIRED_SECTIONS = tuple(section for section in SECTIONS if section not in ("summary", "retention_analysis"))
TEMP_TYPES = {"character", "voice", "location", "object"}
ENTITY_TYPES = {"character", "location", "object"}
TOKEN_PATTERN = r"\{[^{}\r\n]+\}|§[^§\r\n]+§|<[A-Za-z_]+:[^<>]*>"
TOKEN = re.compile(TOKEN_PATTERN)
TEMP = re.compile(r"<(?P<type>[A-Za-z_]+):(?P<name>[^=<>]*?)(?:\s*=\s*(?P<description>[^<>]*))?>", re.S)
HEADER = re.compile(r"^([a-z][a-z_]*):[ \t]*(?:\r?\n|$)", re.M)
DIALOGUE = re.compile(r"<d>.*?</d>", re.S)
RUNTIME = re.compile(r"<(Subject|Picture|Audio|Video)\s+(\d+)>|\(S(\d+)\)")
VOCAL_CLAUSE = r"(?:(?!\r?\n[ \t]*\r?\n|\[Shot\b)[^{}§<>.!?])*?"
# Best-effort discovery for before-dialogue tags, not a grammar validator.
EVENT = re.compile(
    r"(?P<entity>\{[^{}\r\n]+\}|<character:[^<>]+>)"
    rf"(?P<before>{VOCAL_CLAUSE})"
    rf"(?:(?P<voice>§[^§\r\n]+§|<voice:[^<>]+>)(?P<after>{VOCAL_CLAUSE}))?"
    r"(?P<dialogue><d>.*?</d>)", re.S)
TASKS = ("reference generation", "keyframe completion", "video editing", "video continuation",
         "audio reuse", "audio reference")


def fail(code, message):
    raise ValueError(f"{code}: {message}")


def _sort_summary_entries(text):
    """Sort a summary consisting of separate subject lines; preserve narrative prose."""
    lines = text.splitlines(keepends=True)
    entries = []
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        match = re.match(r"^[ \t]*(?:[-*] )?<Subject (\d+)>(?:\s|:|$)", line)
        subjects = set(re.findall(r"<Subject (\d+)>", line))
        if not match or len(subjects) != 1:
            return text
        entries.append((index, int(match[1]), line.rstrip("\r\n")))
    for (index, _, _), (_, _, value) in zip(entries, sorted(entries, key=lambda entry: entry[1])):
        newline = "\r\n" if lines[index].endswith("\r\n") else "\n" if lines[index].endswith("\n") else ""
        lines[index] = value + newline
    return "".join(lines)


def _sort_retention_entries(text):
    """Sort labeled blocks, keeping annotations and wrapped prose with their owner."""
    starts = list(re.finditer(
        r"^[ \t]*(?:[-*] )?<(Subject|Picture|Video|Audio) (\d+)>"
        r"(?:[ \t]*\([^\n]*?\))?[ \t]*:", text, re.M))
    if not starts:
        return text
    kinds = {"Subject": 0, "Picture": 1, "Video": 2, "Audio": 3}
    blocks = []
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        blocks.append((kinds[match[1]], int(match[2]), text[match.start():end].strip()))
    prefix = text[:starts[0].start()].strip()
    return "\n\n".join(block for block in [prefix] + [
        entry[2] for entry in sorted(blocks, key=lambda entry: entry[:2])
    ] if block)


@dataclass
class Resource:
    id: str
    key: str
    source: str
    type: str
    description: str = ""
    voice_description: str = ""
    name: str = ""
    image: bool = False
    audio: bool = False
    video: bool = False
    embedded_audio: bool = False
    video_usage: str = "reference"
    audio_usage: str = "reference"
    owner: str | None = None
    subject: int | None = None
    picture: int | None = None
    audio_slot: int | None = None
    embedded_slot: int | None = None
    video_slot: int | None = None
    speaker: int | None = None
    audio_used: bool = False
    visual_used: bool = False

    def priority(self):
        if self.image:
            return 0 if self.audio or self.embedded_audio else 1
        return 2 if self.audio or self.embedded_audio else 3


@dataclass
class CompiledPrompt:
    prompt: str
    debug: dict
    images: list[str] = field(default_factory=list)
    audios: list[str] = field(default_factory=list)
    videos: list[str] = field(default_factory=list)

    @property
    def mapping(self):
        return json.dumps(self.debug, indent=2, ensure_ascii=False)


def _temp_parts(match):
    kind = match["type"]
    name = match["name"].strip()
    if kind not in TEMP_TYPES:
        fail("INVALID_TEMPORARY_TYPE", kind)
    if not name or re.search(r"[<>=\[\]{}§|\x00-\x1f\x7f\u0085\u2028\u2029]", name):
        fail("INVALID_TEMPORARY_NAME", f"{name!r}: use a nonempty name without tag delimiters, |, or line breaks.")
    return kind, name


def _parse(prompt):
    if prompt.count("<d>") != len(list(DIALOGUE.finditer(prompt))) or prompt.count("</d>") != prompt.count("<d>"):
        fail("INVALID_DIALOGUE", "Unbalanced or nested <d> tags.")
    if RUNTIME.search(prompt):
        fail("AUTHORED_RUNTIME_SLOT", "Use semantic tags in compiler mode; numbered H3 tags belong to legacy mode.")
    headers = []
    for header in HEADER.finditer(prompt):
        if header[1] == "timeline" and headers and headers[-1][1] == "detailed_description":
            continue
        headers.append(header)
    names = tuple(m[1] for m in headers)
    if not all(section in names for section in REQUIRED_SECTIONS) or names != tuple(section for section in SECTIONS if section in names):
        fail("INVALID_SECTION", "Provide subject_definitions, detailed_description, overall_soundscape, and non_diegetic_music in order; summary and retention_analysis are optional, in that order before detailed_description.")
    prefix = prompt[:headers[0].start()]
    temporary = {}
    warnings = []
    def declaration(match):
        kind, name = _temp_parts(match)
        description = match["description"]
        if description is None or not description.strip():
            fail("MISSING_TEMPORARY_DESCRIPTION", match[0])
        key = f"temporary:{kind}:{name}"
        if key in temporary:
            fail("DUPLICATE_TEMPORARY_DECLARATION", key)
        temporary[key] = Resource(key, name, "temporary", kind,
                                  description=description.strip() if kind != "voice" else "",
                                  voice_description=description.strip() if kind == "voice" else "")
        return ""
    prefix = TEMP.sub(declaration, prefix)
    # This marker belongs to the existing prompt-loop subsystem.
    if re.sub(r"\[s=\d+(?:\.\d+)?\]", "", prefix.replace("[new_location]", "")).strip():
        fail("INVALID_DECLARATION", "Only declarations, [new_location], and [s=seconds] may precede subject_definitions.")
    sections = {}
    for i, header in enumerate(headers):
        end = headers[i+1].start() if i+1 < len(headers) else len(prompt)
        sections[header[1]] = prompt[header.end():end].strip()
    def inline_declaration(match):
        if match["description"] is None:
            return match[0]
        declaration(match)
        kind, name = _temp_parts(match)
        return f"<{kind}:{name}>"
    sections["subject_definitions"] = TEMP.sub(inline_declaration, sections["subject_definitions"])
    names = {}
    for r in temporary.values():
        names.setdefault(r.key, set()).add(r.type)
        if r.type == "voice":
            r.owner = f"temporary:character:{r.key}"
    for name, kinds in names.items():
        if len(kinds) > 1 and kinds != {"character", "voice"}:
            warnings.append(f"TEMPORARY_NAME_COLLISION: {name} uses {', '.join(sorted(kinds))}.")
    return prefix.strip(), sections, temporary, warnings


def compile_prompt(prompt, records, *, video_usage="reference", audio_usage="reference",
                   max_images=9, max_audio=3, max_videos=3, voice_isolation=True):
    if video_usage not in ("reference", "motion_reference", "continuation", "editing"):
        fail("INVALID_VIDEO_USAGE", video_usage)
    if audio_usage not in ("reference", "reuse"):
        fail("INVALID_AUDIO_USAGE", audio_usage)
    prefix, sections, temporary, warnings = _parse(prompt)
    usages = []
    saved_keys = set()
    temporary_ids = set()
    for section, text in sections.items():
        for match in TOKEN.finditer(text):
            token = match[0]
            if token.startswith("<"):
                parsed = TEMP.fullmatch(token)
                kind, key = _temp_parts(parsed)
                if parsed["description"] is not None:
                    fail("INVALID_DECLARATION", "Temporary declarations belong before or inside subject_definitions.")
                rid = f"temporary:{kind}:{key}"
                if rid not in temporary:
                    fail("UNKNOWN_TEMPORARY_RESOURCE", token)
                temporary_ids.add(rid)
                voice = kind == "voice"
            else:
                key = token[1:-1].strip()
                if key not in records:
                    fail("UNKNOWN_SAVED_RESOURCE", token)
                saved_keys.add(key)
                rid, voice = f"saved:{key}", token.startswith("§")
            usages.append((section, match.start(), match.end(), rid, voice))
    # Library insertion order and declaration order are the tie-breakers, never tag occurrence order.
    resources = {}
    for key, record in records.items():
        if key not in saved_keys:
            continue
        kind = record.get("reference_type") or record.get("type") or "uncategorized"
        kind = kind.lower()
        if kind == "uncategorized":
            fail("UNCLASSIFIED_RESOURCE", f"Set a reference type for {{{key}}} in the library.")
        if kind not in ENTITY_TYPES | {"voice", "music", "video"}:
            fail("INVALID_RESOURCE_TYPE", f"{key}: {kind}")
        r = Resource(f"saved:{key}", key, "saved", kind,
            description=(record.get("image_description") or record.get("video_description") or record.get("description") or "").strip(),
            voice_description=(record.get("audio_description") or "").strip(),
            name=(record.get("name") or key).strip(), image=bool(record.get("image_file")),
            audio=bool(record.get("audio_file")), video=bool(record.get("video_file")),
            embedded_audio=bool(record.get("video_file") and record.get("video_has_audio")),
            video_usage=record.get("video_usage", video_usage), audio_usage=record.get("audio_usage", audio_usage))
        if r.video_usage not in ("reference", "motion_reference", "continuation", "editing"):
            fail("INVALID_VIDEO_USAGE", key)
        if r.audio_usage not in ("reference", "reuse"):
            fail("INVALID_AUDIO_USAGE", key)
        if kind == "video" and not r.video:
            fail("VIDEO_SLOT_WITHOUT_VIDEO_ASSET", key)
        if kind == "music" and not r.audio:
            fail("AUDIO_SLOT_WITHOUT_AUDIO_ASSET", key)
        resources[r.id] = r
    for rid, r in temporary.items():
        if rid in temporary_ids:
            resources[rid] = r
    for section, start, end, rid, voice in usages:
        r = resources[rid]
        if voice:
            if r.type == "video" and not r.embedded_audio:
                fail("MISSING_VIDEO_AUDIO", f"{r.key}: a soundtrack tag requires an enabled video audio track.")
        else:
            r.visual_used = True
    def lookup(token):
        if token.startswith("<"):
            m = TEMP.fullmatch(token)
            return resources[f"temporary:{m['type']}:{m['name'].strip()}"]
        return resources[f"saved:{token[1:-1].strip()}"]
    detail = sections["detailed_description"]
    speaker_events = {}
    nonisolated_events = set()
    inline_voice_positions = set()
    for section, text in sections.items():
        for dialogue in DIALOGUE.finditer(text):
            for token in TOKEN.finditer(dialogue[0]):
                inline_voice_positions.add((section, dialogue.start() + token.start()))
    speakers = []
    events = {event.start("dialogue"): event for event in EVENT.finditer(detail)}
    previous_end = 0
    for dialogue in DIALOGUE.finditer(detail):
        event = events.get(dialogue.start())
        entity = lookup(event["entity"]) if event else None
        voice = lookup(event["voice"]) if event and event["voice"] else None
        header = re.match(r"<d>\s*\[([^\]]*)\]", dialogue[0])
        header_voices = [lookup(token[0]) for token in TOKEN.finditer(header[1])
                         if token[0].startswith(("\u00a7", "<voice:"))] if header else []
        if header_voices:
            voice = header_voices[0]
        if entity is None and voice is None:
            # Recognize a separated voice cue without crossing another turn or shot.
            preceding = detail[previous_end:dialogue.start()]
            preceding = re.split(r"\[Shot\b", preceding)[-1]
            voices = [lookup(token[0]) for token in TOKEN.finditer(preceding)
                      if token[0].startswith(("\u00a7", "<voice:"))]
            voice = voices[-1] if voices else None
        previous_end = dialogue.end()
        if entity is None and voice is not None:
            entity = resources.get(voice.owner, voice)
        if entity is None or entity.type != "character":
            continue
        if entity.speaker is None:
            speakers.append(entity)
            entity.speaker = len(speakers)
        if event:
            position = event.start("entity")
            speaker_events[position] = entity.speaker
            if voice is not None and (voice.owner or voice.id) != entity.id:
                nonisolated_events.add(position)
    for section, start, end, rid, voice in usages:
        r = resources[rid]
        if section != "subject_definitions" and (voice or r.type in ("music", "voice")):
            r.audio_used = bool(r.audio or r.embedded_audio)
    # Allocate every stream after identifying speakers. Spoken subjects share their
    # Speaker ID; their real images and audio follow the same first-speech order.
    # Silent resources retain media priority and library/declaration tie-breakers.
    ordered = sorted(resources.values(), key=lambda r: (
        resources.get(r.owner, r).speaker or float("inf"), r.priority()))
    images = [r for r in ordered if r.image]
    videos = [r for r in ordered if r.video]
    embedded = [r for r in videos if r.embedded_audio]
    subjects = [r for r in ordered if r.type in ENTITY_TYPES]
    for label, values, limit in (("images", images, max_images), ("videos", videos, max_videos)):
        raw_values = [r for r in values if not records.get(r.key, {}).get("_refmod_" + ("image" if label == "images" else "video"))]
        if len(raw_values) > limit:
            fail("REFERENCE_LIMIT", f"{len(values)} {label}; supported maximum is {limit}.")
    for i, r in enumerate(subjects, 1): r.subject = i
    for i, r in enumerate(images, 1): r.picture = i
    for i, r in enumerate(videos, 1): r.video_slot = i
    # H3 emits enabled video soundtrack labels before standalone audio labels.
    for i, r in enumerate(embedded, 1): r.embedded_slot = i
    audios = [r for r in ordered if r.audio and (r.type != "character" or r.audio_used)]
    if len(audios) > max_audio:
        fail("REFERENCE_LIMIT", f"{len(audios)} audio files; supported maximum is {max_audio}.")
    for i, r in enumerate(audios, len(embedded)+1):
        r.audio_slot = i
    task_types = set()
    for r in ordered:
        if r.picture and r.visual_used:
            task_types.add("reference generation")
        if r.video_slot and r.visual_used:
            task_types.add({"reference": "reference generation", "motion_reference": "reference generation",
                            "continuation": "video continuation", "editing": "video editing"}[r.video_usage])
        if r.audio_used:
            task_types.add("audio reuse" if r.audio_usage == "reuse" else "audio reference")
            if r.audio_usage == "reference":
                task_types.add("reference generation")
    definitions = set()
    audio_definitions = set()
    media_definitions = set()
    voice_owners = [r for r in speakers if r.audio_used and (r.audio_slot or r.embedded_slot)]
    def isolate_speaker(r):
        if not voice_isolation or not voice_owners:
            return ""
        identity = f"<Subject {r.subject}> (S{r.speaker})"
        rules = []
        if r in voice_owners:
            slot = r.audio_slot or r.embedded_slot
            role = "reused vocal audio" if r.audio_usage == "reuse" else "voice-timbre reference"
            rules.append(f"{identity} is the only speaker using <Audio {slot}> as its {role}.")
        others = [f"<Audio {owner.audio_slot or owner.embedded_slot}>" for owner in voice_owners if owner is not r]
        if others:
            rules.append(f"{identity} uses its own assigned voice identity and must not use or imitate " + " or ".join(others) + ".")
        return " ".join(rules) + (" " if rules else "")

    def render(r, section, voice, position):
        audio_slot = r.embedded_slot if r.type == "video" else r.audio_slot or r.embedded_slot
        if voice:
            if (section, position) in inline_voice_positions:
                return f"<Audio {audio_slot}>" if audio_slot and r.audio_used else (r.voice_description or r.description or r.name)
            if r.type == "video":
                if section == "subject_definitions":
                    if not r.audio_used:
                        return ""
                    audio_definitions.add(r.id)
                    usage = "is reused in the target video" if r.audio_usage == "reuse" else "is referenced without copying the original signal"
                    return f"<Audio {audio_slot}> is the synchronized audio track of <Video {r.video_slot}> and {usage}."
                return f"<Audio {audio_slot}>"
            owner = resources.get(r.owner, r)
            if section == "subject_definitions":
                if not r.audio_used or not audio_slot:
                    return ""
                audio_definitions.add(r.id)
                speaker = f" (S{owner.speaker})" if owner.speaker else ""
                isolation = (f" This vocal reference applies only to <Subject {owner.subject}>{speaker} and must not influence any other speaker's timbre, accent, cadence, pitch, or delivery."
                             if voice_isolation else "")
                if r.audio_usage == "reuse":
                    return f"<Audio {audio_slot}> is the source of the vocal audio reused for <Subject {owner.subject}>{speaker}." + isolation
                return f"<Audio {audio_slot}> is the voice-timbre reference for <Subject {owner.subject}>{speaker}." + isolation
            if section == "summary":
                return f"<Audio {audio_slot}>" if audio_slot and r.audio_used else r.voice_description
            if section == "detailed_description":
                introduced = re.search(r"\b(?:using|in|with)\s*$", detail[:position], re.I)
                if audio_slot:
                    if r.audio_usage == "reuse":
                        phrase = f"vocal audio directly reused from <Audio {audio_slot}>"
                    else:
                        phrase = f"the recognizable voice timbre referenced from <Audio {audio_slot}>"
                    return phrase if introduced else "using " + phrase
                description = (r.voice_description or r.description or r.name).rstrip(".")
                if introduced:
                    return re.sub(r"^(?:in|using|with)\s+", "", description, flags=re.I)
                return description if description.lower().startswith(("in ", "using ")) else f"in {description}"
            return f"<Audio {audio_slot}>" if audio_slot and r.audio_used else ""
        if r.subject:
            subject = f"<Subject {r.subject}>"
            if section == "subject_definitions":
                if r.id in definitions:
                    fail("DUPLICATE_SUBJECT_DEFINITION", r.id)
                definitions.add(r.id)
                if r.source == "temporary":
                    description = r.description
                else:
                    description = r.name
                    if r.picture:
                        description += f" in <Picture {r.picture}>"
                    elif r.video_slot:
                        description += f" in <Video {r.video_slot}>"
                    if r.description:
                        description += ", " + r.description
                return f"{subject} is {description.rstrip('.')}."
            if section == "detailed_description" and position in speaker_events:
                return ("" if position in nonisolated_events else isolate_speaker(r)) + f"{subject} (S{speaker_events[position]})"
            return subject
        if r.type == "video":
            if section == "subject_definitions":
                if r.id in media_definitions:
                    fail("DUPLICATE_MEDIA_DEFINITION", r.id)
                media_definitions.add(r.id)
                role = {"reference": "a whole-video reference", "motion_reference": "a camera-motion and temporal-structure reference",
                        "continuation": "the source video whose ending is continued", "editing": "the source video for the target video edit"}[r.video_usage]
                description = f" {r.description}" if r.description else ""
                return f"<Video {r.video_slot}> is {role}.{description}"
            return f"<Video {r.video_slot}>"
        if audio_slot:
            if section == "subject_definitions":
                if r.id in media_definitions:
                    fail("DUPLICATE_MEDIA_DEFINITION", r.id)
                media_definitions.add(r.id)
                role = "music" if r.type == "music" else "audio"
                usage = "reused in the target video" if r.audio_usage == "reuse" else "referenced without copying the original signal"
                description = f" {r.voice_description}" if r.voice_description else ""
                return f"<Audio {audio_slot}> is the {role} reference {usage}.{description}"
            return f"<Audio {audio_slot}>"
        fail("UNRESOLVED_TAG", r.id)
    rendered = {}
    definition_blocks = []
    definition_prefix = ""
    for section, text in sections.items():
        spans = [usage for usage in usages if usage[0] == section]
        if section == "subject_definitions":
            definition_prefix = text[:spans[0][1]] if spans else text
            for i, (_, start, end, rid, voice) in enumerate(spans):
                r = resources[rid]
                owner = resources.get(r.owner, r)
                next_start = spans[i+1][1] if i+1 < len(spans) else len(text)
                block = render(r, section, voice, start) + text[end:next_start]
                definition_blocks.append((owner.subject or float("inf"), int(voice), block))
            continue
        pieces, previous = [], 0
        for _, start, end, rid, voice in spans:
            pieces.extend((text[previous:start], render(resources[rid], section, voice, start)))
            previous = end
        pieces.append(text[previous:])
        rendered[section] = "".join(pieces).strip()
    missing = [r.id for r in subjects if r.id not in definitions]
    if missing:
        fail("MISSING_SUBJECT_DEFINITION", ", ".join(missing))
    # Add only mechanical voice relationships, never retention or creative prose.
    for r in ordered:
        if r.audio_used and r.type in ("character", "video") and r.id not in audio_definitions:
            line = render(r, "subject_definitions", True, 0)
            definition_blocks.append((r.subject or float("inf"), 1, line))
        if r.type in ("video", "music", "voice") and r.id not in media_definitions and r.visual_used:
            line = render(r, "subject_definitions", False, 0)
            definition_blocks.append((float("inf"), 0, line))
    # Sort complete definition blocks; attached authored text stays with its resource.
    rendered["subject_definitions"] = "\n\n".join(
        block.strip() for block in [definition_prefix] + [
            entry[2] for entry in sorted(definition_blocks, key=lambda entry: entry[:2])
        ] if block.strip())
    task_list = [task for task in TASKS if task in task_types]
    summary = rendered.get("summary", "")
    header = re.match(r"^\[([^]\n]+)\]", summary)
    if header and all(t.strip() in TASKS for t in header[1].split("+")):
        summary = summary[header.end():].lstrip()
    summary = _sort_summary_entries(summary)
    summary = " ".join(re.sub(r"^\s*[-*] +", "", line).strip()
                       for line in summary.splitlines() if line.strip())
    editing_videos = [r for r in videos if r.visual_used and r.video_usage == "editing"]
    if editing_videos:
        sources = " and ".join(f"<Video {r.video_slot}>" for r in editing_videos)
        opening = f"The target video is an edited version of {sources}."
        if not summary.startswith(opening):
            summary = opening + (" " + summary if summary else "")
    if "summary" in rendered:
        rendered["summary"] = summary
    elif summary:
        rendered["detailed_description"] = summary + "\n\n" + rendered["detailed_description"]
    if "retention_analysis" in rendered:
        rendered["retention_analysis"] = _sort_retention_entries(rendered["retention_analysis"])
    output = "\n\n".join(f"{section}:\n\n{rendered[section]}" for section in sections)
    if prefix:
        output = prefix + "\n\n" + output
    if TOKEN.search(output) or re.search(r"[{}§]|<(?:character|voice|location|object):", output):
        fail("UNRESOLVED_TAG", "An authoring tag remains after compilation.")
    limits = {"Subject": len(subjects), "Picture": len(images), "Audio": len(embedded)+len(audios), "Video": len(videos)}
    for match in RUNTIME.finditer(output):
        if match[3]:
            if not 1 <= int(match[3]) <= len(speakers): fail("INVALID_SPEAKER_SLOT", match[0])
        elif not 1 <= int(match[2]) <= limits[match[1]]:
            fail(f"{match[1].upper()}_SLOT_WITHOUT_ASSET", match[0])
    debug = {"resources": {r.id: {
        "source": r.source, "type": r.type, "subject": r.subject, "picture": r.picture,
        "audio": r.audio_slot or r.embedded_slot, "video": r.video_slot, "speaker": r.speaker,
        "audio_used": r.audio_used, "has_image": r.image, "has_audio": r.audio or r.embedded_audio,
        "has_video": r.video, "has_visual_description": bool(r.description),
        "has_voice_description": bool(r.voice_description),
    } for r in ordered},
        "pictures": {str(r.picture): r.id for r in images},
        "audio": {**{str(r.embedded_slot): r.id for r in embedded}, **{str(r.audio_slot): r.id for r in audios}},
        "video": {str(r.video_slot): r.id for r in videos},
        "speakers": {str(r.speaker): r.id for r in speakers}, "task_types": task_list, "warnings": warnings,
        "voice_isolation": bool(voice_isolation), "generated_voice_retention": []}
    return CompiledPrompt(output, debug, [r.key for r in images], [r.key for r in audios], [r.key for r in videos])

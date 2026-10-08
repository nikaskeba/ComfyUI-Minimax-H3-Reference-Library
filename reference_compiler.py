"""Deterministic, section-aware H3 reference compilation. No media loading."""
from .compiler_templates import CompilerTemplates
from .reference_images import reference_images
import json
import re
from dataclasses import dataclass, field


SECTIONS = ("subject_definitions", "summary", "retention_analysis", "detailed_description",
            "overall_soundscape", "non_diegetic_music")
REQUIRED_SECTIONS = tuple(section for section in SECTIONS if section not in ("summary", "retention_analysis"))
TEMP_TYPES = {"character", "voice", "location", "object"}
ENTITY_TYPES = {"character", "location", "object", "clothing"}
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
    pictures: list = field(default_factory=list)
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
    # Older authoring prompts used detailed_description for the setup and timeline for shots.
    if not any(m[1] == "detailed_description" for m in HEADER.finditer(prompt)):
        prompt = re.sub(r"^timeline:[ \t]*(?=\r?\n|$)", "detailed_description:", prompt, flags=re.M)
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
    timeline = re.search(r"^timeline:[ \t]*(?:\r?\n|$)", sections["detailed_description"], re.M)
    if timeline:
        setup = sections["detailed_description"][:timeline.start()].strip()
        sections["summary"] = "\n\n".join(part for part in (sections.get("summary", ""), setup) if part)
        sections["detailed_description"] = sections["detailed_description"][timeline.end():].strip()
        sections = {name:sections[name] for name in SECTIONS if name in sections}
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


def _implicitly_uses_voice(event):
    clause = event["before"].strip()
    return bool(re.search(
        r"\b(?:says?|said|speaks?|asks?|replies|reply|responds?|exclaims?|whispers?|shouts?|yells?|murmurs?|mutters?|screams?|sings?|snaps?\s+back|retorts?|answers?)\b",
        clause, re.I) or clause in (":", ",", ""))


def _dialogue_events(detail, is_character):
    events = {event.start("dialogue"): {**event.groupdict(), "position": event.start("entity")}
              for event in EVENT.finditer(detail)}
    shots = list(re.finditer(r"\[Shot\s+\d+(?:\s*:\s*\d+(?:\.\d+)?s)?\]", detail, re.I))
    for dialogue in DIALOGUE.finditer(detail):
        direct = events.get(dialogue.start())
        if direct and (is_character(direct["entity"]) or direct["voice"]):
            continue
        preceding_shots = [shot for shot in shots if shot.end() <= dialogue.start()]
        if not preceding_shots:
            continue
        start = preceding_shots[-1].end()
        preceding = detail[start:dialogue.start()]
        # Keep source offsets while excluding words and tags inside earlier dialogue.
        staging = DIALOGUE.sub(lambda match: " " * len(match[0]), preceding)
        characters = {}
        for token in TOKEN.finditer(staging):
            if is_character(token[0]):
                characters.setdefault(token[0], token.start())
        clause = re.split(r"[.!?]", staging)[-1].strip()
        if len(characters) != 1 or not clause or not _implicitly_uses_voice({"before": clause}):
            continue
        if re.search(r"\b(?:does\s+not|doesn't|never|without)\s+(?:say|speak|reply|shout)\b", clause, re.I):
            continue
        entity, position = next(iter(characters.items()))
        voices = [token[0] for token in TOKEN.finditer(clause) if token[0].startswith(("§", "<voice:"))]
        events[dialogue.start()] = {"entity": entity, "position": start + position,
                                   "before": clause, "voice": voices[-1] if voices else None,
                                   "dialogue": dialogue[0]}
    return events


def inferred_saved_voice_tags(prompt, records=None):
    """Discover implicit voice sources before RefMod assets are projected."""
    try:
        _, sections, _, _ = _parse(prompt)
    except ValueError:
        # Legacy/free-form prompts retain their explicit voice-tag behavior.
        return set()
    tags = set()
    records = records or {}
    def is_character(token):
        return token.startswith("<character:") or (token.startswith("{") and
            records.get(token[1:-1].strip(), {}).get("reference_type", "character") == "character")
    for event in _dialogue_events(sections["detailed_description"], is_character).values():
        header = re.match(r"<d>\s*\[([^\]]*)\]", event["dialogue"])
        if event["voice"] or (header and any(
                t[0].startswith(("§", "<voice:")) for t in TOKEN.finditer(header[1]))):
            continue
        if event["entity"].startswith("{") and _implicitly_uses_voice(event):
            tags.add(event["entity"][1:-1].strip())
    return tags


def compile_prompt(prompt, records, *, video_usage="reference", audio_usage="reference",
                   max_images=9, max_audio=3, max_videos=3, voice_isolation=True,
                   refmod_subject_only=False, reference_order="first_speech", compiler_templates="", template_preview=None):
    templates = CompilerTemplates(compiler_templates)
    def wording(template_key, resource=None, **values):
        context = template_context(resource)
        context.update(values)
        text = templates.render(template_key, **context)
        if template_preview is not None:
            template_preview.setdefault(template_key, []).append(text)
        return text
    if reference_order not in ("first_speech", "library_order"):
        fail("INVALID_REFERENCE_ORDER", reference_order)
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
            name=(record.get("name") or key).strip(), image=bool(reference_images(record)),
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
    events = _dialogue_events(detail, lambda token: token.startswith(("{", "<character:")) and lookup(token).type == "character")
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
        # A directly attributed speaking turn can use its owner's attached voice
        # without putting an audio tag into the dialogue language header.
        if voice is None and event:
            if _implicitly_uses_voice(event):
                entity.audio_used = bool(entity.audio or entity.embedded_audio)
        if entity.speaker is None:
            speakers.append(entity)
            entity.speaker = len(speakers)
        if event:
            position = event["position"]
            speaker_events[position] = entity.speaker
            if voice is not None and (voice.owner or voice.id) != entity.id:
                nonisolated_events.add(position)
    for section, start, end, rid, voice in usages:
        r = resources[rid]
        if section != "subject_definitions" and (voice or r.type in ("music", "voice")):
            r.audio_used = bool(r.audio or r.embedded_audio)
    # Speaker IDs above come only from first dialogue occurrence, not asset slots.
    # Allocate subjects/media afterward in first-speech order; missing voices and
    # video soundtracks mean Audio N need not equal Subject N or SN.
    # Silent resources retain media priority and library/declaration tie-breakers.
    ordered = sorted(resources.values(), key=lambda r: (
        (resources.get(r.owner, r).speaker or float("inf")) if reference_order == "first_speech" else 0, r.priority()))
    images = [r for r in ordered if r.image for _ in reference_images(records.get(r.key, {}))]
    videos = [r for r in ordered if r.video]
    embedded = [r for r in videos if r.embedded_audio]
    subjects = [r for r in ordered if r.type in ENTITY_TYPES]
    for label, values, limit in (("images", images, max_images), ("videos", videos, max_videos)):
        raw_values = [r for r in values if not records.get(r.key, {}).get("_refmod_" + ("image" if label == "images" else "video"))]
        if len(raw_values) > limit:
            fail("REFERENCE_LIMIT", f"{len(values)} {label}; supported maximum is {limit}.")
    for i, r in enumerate(subjects, 1): r.subject = i
    for i, r in enumerate(images, 1):
        r.pictures.append(i)
        if r.picture is None:
            r.picture = i
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
    def unlabelled_refmod_voice(r):
        return bool(refmod_subject_only and records.get(r.key, {}).get("_refmod_audio"))

    voice_owners = [r for r in speakers if r.audio_used and (r.audio_slot or r.embedded_slot)
                    and not unlabelled_refmod_voice(r)]

    def template_context(r):
        context = {
            "task_prefix": "[" + " + ".join(task for task in TASKS if task in task_types) + "]" if task_types else "",
            "bindings": "; ".join(f"<Subject {v.subject}> = S{v.speaker} = <Audio {v.audio_slot or v.embedded_slot}>" for v in voice_owners),
            "sources": " and ".join(f"<Video {v.video_slot}>" for v in videos if v.visual_used and v.video_usage == "editing"),
        }
        if r is None:
            return context
        owner = resources.get(r.owner, r)
        voice = r
        if not r.audio_used:
            voice = next((v for v in ordered if v.owner == owner.id and v.audio_used), r)
        slot = voice.audio_slot or voice.embedded_slot
        subject = f"<Subject {owner.subject}>" if owner.subject else ""
        speaker = f" (S{owner.speaker})" if owner.speaker else ""
        description = voice.voice_description.strip()
        if description and not description.endswith((".", "!", "?")):
            description += "."
        pictures = ", ".join(f"<Picture {number}>" for number in owner.pictures)
        video = f"<Video {owner.video_slot}>" if owner.video_slot else ""
        context.update(
            subject=subject, speaker=speaker, identity=subject + speaker,
            subject_number=str(owner.subject) if owner.subject else "",
            subject_label=f"Subject {owner.subject}" if owner.subject else "",
            speaker_number=str(owner.speaker) if owner.speaker else "",
            speaker_id=f"S{owner.speaker}" if owner.speaker else "",
            speaker_tag=f"<S{owner.speaker}>" if owner.speaker else "",
            audio=f"<Audio {slot}>" if slot and voice.audio_used and not unlabelled_refmod_voice(voice) else "",
            voice_description=description,
            name=re.sub(r"_(?:rm|BC)$", "", owner.name or owner.key, flags=re.I).rsplit("/", 1)[-1].replace("_", " "),
            description=r.description, picture=f"<Picture {owner.picture}>" if owner.picture else "",
            video=video, media=pictures or video,
            role="music" if r.type == "music" else "audio",
        )
        return context
    def isolate_speaker(r):
        if not voice_isolation or r not in voice_owners:
            return ""
        slot = r.audio_slot or r.embedded_slot
        return wording("dialogue_binding_" + r.audio_usage, resource=r, audio=f"<Audio {slot}>")

    def render(r, section, voice, position):
        audio_slot = r.embedded_slot if r.type == "video" else r.audio_slot or r.embedded_slot
        if voice:
            if unlabelled_refmod_voice(r):
                if section == "subject_definitions":
                    audio_definitions.add(r.id)
                return ""
            if (section, position) in inline_voice_positions:
                return f"<Audio {audio_slot}>" if audio_slot and r.audio_used else (r.voice_description or r.description or r.name)
            if r.type == "video":
                if section == "subject_definitions":
                    if not r.audio_used:
                        return ""
                    audio_definitions.add(r.id)
                    return wording("soundtrack_" + r.audio_usage, resource=r, audio=f"<Audio {audio_slot}>", video=f"<Video {r.video_slot}>")
                return f"<Audio {audio_slot}>"
            owner = resources.get(r.owner, r)
            if section == "subject_definitions":
                if not r.audio_used or not audio_slot:
                    return ""
                audio_definitions.add(r.id)
                speaker = f" (S{owner.speaker})" if owner.speaker else ""
                voice_name = owner.name or owner.key
                voice_name = re.sub(r"_(?:rm|BC)$", "", voice_name, flags=re.I).rsplit("/", 1)[-1].replace("_", " ")
                voice_description = r.voice_description.strip()
                if voice_description and not voice_description.endswith((".", "!", "?")):
                    voice_description += "."
                values = dict(audio=f"<Audio {audio_slot}>", subject=f"<Subject {owner.subject}>", speaker=speaker, name=voice_name)
                characteristics = wording("voice_characteristics", resource=r, voice_description=voice_description) if voice_description else ""
                isolation = wording("voice_exclusive_" + r.audio_usage, resource=r, **values) if r.audio_usage != "reuse" or voice_isolation else ""
                return wording("voice_" + r.audio_usage, resource=r, **values) + isolation + characteristics
            if section == "summary":
                return f"<Audio {audio_slot}>" if audio_slot and r.audio_used else r.voice_description
            if section == "detailed_description":
                introduced = re.search(r"\b(?:using|in|with)\s*$", detail[:position], re.I)
                if audio_slot:
                    phrase = wording("voice_cue_" + r.audio_usage, resource=r, audio=f"<Audio {audio_slot}>")
                    return phrase if introduced or not phrase else wording("voice_cue_introduction", resource=r, phrase=phrase)
                description = (r.voice_description or r.description or r.name).rstrip(".")
                if introduced:
                    return re.sub(r"^(?:in|using|with)\s+", "", description, flags=re.I)
                return description if description.lower().startswith(("in ", "using ")) else wording("text_voice_introduction", resource=r, description=description)
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
                    record = records.get(r.key, {})
                    subject_only = (
                        record.get("_refmod_image") or record.get("_refmod_video"))
                    if r.picture and not subject_only:
                        description += wording("subject_media", resource=r, media=", ".join(f"<Picture {number}>" for number in r.pictures))
                    elif r.video_slot and not subject_only:
                        description += wording("subject_media", resource=r, media=f"<Video {r.video_slot}>")
                    if len(r.pictures) > 1 or (r.picture and not record.get("image_file")):
                        for number, attachment in zip(r.pictures, reference_images(record)):
                            if attachment.get("description"):
                                description += wording("picture_description", resource=r, picture=f"<Picture {number}>", description=attachment["description"].rstrip("."))
                    elif r.description:
                        description += wording("subject_description", resource=r, description=r.description)
                return wording("subject_definition", resource=r, subject=subject, description=description.rstrip("."))
            if section == "detailed_description" and position in speaker_events:
                binding = "" if position in nonisolated_events else isolate_speaker(r)
                token = TOKEN.match(detail, position)
                if binding and detail[token.end():].lstrip().startswith((",", ".", "!", "?")):
                    binding = binding.rstrip(",")
                return f"{subject} (S{speaker_events[position]})" + binding
            return subject
        if r.type == "video":
            if section == "subject_definitions":
                if r.id in media_definitions:
                    fail("DUPLICATE_MEDIA_DEFINITION", r.id)
                media_definitions.add(r.id)
                description = f" {r.description}" if r.description else ""
                return wording("video_" + r.video_usage, resource=r, video=f"<Video {r.video_slot}>", description=description)
            return f"<Video {r.video_slot}>"
        if audio_slot:
            if section == "subject_definitions":
                if r.id in media_definitions:
                    fail("DUPLICATE_MEDIA_DEFINITION", r.id)
                media_definitions.add(r.id)
                role = "music" if r.type == "music" else "audio"
                description = f" {r.voice_description}" if r.voice_description else ""
                return wording("media_audio_" + r.audio_usage, resource=r, audio=f"<Audio {audio_slot}>", role=role, description=description)
            return f"<Audio {audio_slot}>"
        fail("UNRESOLVED_TAG", r.id)
    rendered = {}
    definition_blocks = []
    definition_prefix = ""
    for section, text in sections.items():
        spans = [usage for usage in usages if usage[0] == section]
        if section == "subject_definitions":
            # A tag inside authored prose is a cross-reference, not another definition.
            # Adjacent bare tags remain supported as a compact definition list.
            starts = [i for i, (_, start, _, _, _) in enumerate(spans)
                      if i == 0 or re.fullmatch(r"[ \t]*(?:[-*][ \t]+)?", text[text.rfind("\n", 0, start)+1:start])
                      or (i and not text[spans[i-1][2]:start].strip())]
            definition_prefix = text[:spans[starts[0]][1]] if starts else text
            for index, i in enumerate(starts):
                _, start, end, rid, voice = spans[i]
                r = resources[rid]
                owner = resources.get(r.owner, r)
                stop = starts[index+1] if index+1 < len(starts) else len(spans)
                next_start = spans[stop][1] if stop < len(spans) else len(text)
                pieces = [render(r, section, voice, start)]
                previous = end
                for _, nested_start, nested_end, nested_id, nested_voice in spans[i+1:stop]:
                    pieces.extend((text[previous:nested_start],
                                   render(resources[nested_id], "definition_reference", nested_voice, nested_start)))
                    previous = nested_end
                pieces.append(text[previous:next_start])
                definition_blocks.append((owner.subject or float("inf"), int(voice), "".join(pieces)))
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
    # Add resolved voice relationships without changing asset allocation.
    for r in ordered:
        if r.audio_used and r.type in ("character", "video") and r.id not in audio_definitions:
            line = render(r, "subject_definitions", True, 0)
            definition_blocks.append((r.subject or float("inf"), 1, line))
        if r.type in ("video", "music", "voice") and r.id not in media_definitions and r.visual_used:
            line = render(r, "subject_definitions", False, 0)
            definition_blocks.append((float("inf"), 0, line))
    # Keep each subject's complete authored block beside its voice definition.
    def definition_order(entry):
        if entry[0] != float("inf"):
            return (0, entry[0], entry[1])
        match = re.match(r"\s*<(Subject|Picture|Video|Audio) (\d+)>", entry[2])
        if match:
            return (1, {"Subject": 0, "Picture": 1, "Video": 1, "Audio": 2}[match[1]], int(match[2]))
        return (2, entry[0], 0)

    rendered["subject_definitions"] = "\n\n".join(
        block.strip() for block in [definition_prefix] + [
            entry[2] for entry in sorted(definition_blocks, key=definition_order)
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
        opening = wording("summary_editing", sources=sources)
        if not summary.startswith(opening):
            summary = opening + (" " + summary if summary else "")
    if voice_isolation:
        for r in voice_owners:
            slot = r.audio_slot or r.embedded_slot
            identity = f"<Subject {r.subject}> (S{r.speaker})"
            binding = wording("summary_voice_" + r.audio_usage, resource=r, audio=f"<Audio {slot}>", identity=identity)
            if binding not in summary:
                summary = (summary + " " + binding).strip()
    rendered["summary"] = (wording("summary_task_prefix", task_prefix="[" + " + ".join(task_list) + "]") + summary).strip() if task_list else summary
    if voice_isolation and len(voice_owners) >= 2:
        bindings = "; ".join(f"<Subject {r.subject}> = S{r.speaker} = <Audio {r.audio_slot or r.embedded_slot}>" for r in voice_owners)
        binding = wording("global_binding", bindings=bindings)
        if binding:
            rendered["subject_definitions"] += "\n\n" + binding
    retention = rendered.get("retention_analysis", "").strip()
    if retention == "N/A":
        retention = ""
    generated_voice_retention = []
    shot_detail = DIALOGUE.sub(lambda match: " " * len(match[0]), detail)
    shot_spans = list(re.finditer(r"\[Shot\s+(\d+)(?:\s*:\s*\d+(?:\.\d+)?s)?\]", shot_detail, re.I))
    for r in subjects:
        if not r.visual_used or re.search(rf"<Subject {r.subject}>(?:[^\n]*?):", retention):
            continue
        appearances = []
        for index, shot in enumerate(shot_spans):
            end = shot_spans[index+1].start() if index+1 < len(shot_spans) else len(detail)
            staging = shot_detail[shot.end():end]
            for token in TOKEN.finditer(staging):
                if token[0].startswith(("\u00a7", "<voice:")) or lookup(token[0]).id != r.id:
                    continue
                # An explicitly off-screen voice is not a visual appearance.
                clause = staging[token.end():].split(".", 1)[0]
                if re.match(r"\s*(?:\([^)]*)?(?:off[- ]screen|off[- ]camera|unseen)\b", clause, re.I):
                    continue
                label = f"[Shot {shot[1]}]"
                if label not in appearances:
                    appearances.append(label)
        where = wording("retention_appearances", resource=r, shots=", ".join(appearances)) if appearances else ""
        retention += "\n\n" + wording("retention_subject", resource=r, subject=f"<Subject {r.subject}>", appearances=where, shots=", ".join(appearances))
    for r in voice_owners:
        slot = r.audio_slot or r.embedded_slot
        if re.search(rf"<Audio {slot}>\s*:", retention):
            continue
        identity = f"<Subject {r.subject}> (S{r.speaker})"
        line = wording("retention_voice_" + r.audio_usage, resource=r, audio=f"<Audio {slot}>", identity=identity)
        generated_voice_retention.append(line)
        retention += "\n\n" + line
    rendered["retention_analysis"] = _sort_retention_entries(retention.strip())
    output = "\n\n".join(f"{section}:\n\n{rendered.get(section, '')}" for section in SECTIONS)
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
        "pictures": {str(i): r.id for i, r in enumerate(images, 1)},
        "audio": {**{str(r.embedded_slot): r.id for r in embedded}, **{str(r.audio_slot): r.id for r in audios}},
        "video": {str(r.video_slot): r.id for r in videos},
        "speakers": {str(r.speaker): r.id for r in speakers}, "task_types": task_list, "warnings": warnings,
        "compiler_templates": {"version": 1, "hash": templates.hash}, "reference_order": reference_order, "voice_isolation": bool(voice_isolation), "generated_voice_retention": generated_voice_retention}
    return CompiledPrompt(output, debug, [r.key for r in images], [r.key for r in audios], [r.key for r in videos])

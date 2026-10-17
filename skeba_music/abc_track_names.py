"""Recover declared ABC voice names after abc2midi adds chord tracks."""

import re

from symusic import Score


VOICE_LINE = re.compile(r"^\s*V:\s*([^\s\]]+)(.*)$")
NAME = re.compile(r'\bname\s*=\s*"([^"]+)"')
QUOTED_CHORD = re.compile(r'"[^"\n]*"')


def _signature(track):
    return tuple((note.time, note.duration, note.pitch) for note in track.notes)


def _voice_sections(abc):
    """Return headers and music for each declared voice, preserving its bars."""
    lines = abc.splitlines()
    first_voice = next((index for index, line in enumerate(lines) if VOICE_LINE.match(line)), None)
    if first_voice is None:
        return [], None, {}
    header = [line for line in lines[:first_voice] if not line.startswith("K:")]
    key = next((line for line in lines if line.startswith("K:")), None)
    voices = {}
    current = None
    for line in lines[first_voice:]:
        match = VOICE_LINE.match(line)
        if match:
            current = match.group(1)
            name = NAME.search(match.group(2))
            entry = voices.setdefault(current, {"name": current, "declaration": line, "music": []})
            if name:
                entry["name"] = name.group(1)
                entry["declaration"] = line
        elif current is not None and line.strip() and not line.lstrip().startswith(("%", "K:")):
            voices[current]["music"].append(QUOTED_CHORD.sub("", line))
    return header, key, voices


def label_abc_tracks(abc, score):
    """Name matched voices; identify extra tracks produced by chord symbols."""
    header, key, voices = _voice_sections(abc)
    if not voices or key is None:
        # Preserve the prior simple mapping for ABC using inline [V:...] tags.
        inline = {}
        for match in re.finditer(r'\[V:\s*([^\s\]]+)([^\]]*)\]', abc):
            name = NAME.search(match.group(2))
            inline.setdefault(match.group(1), name.group(1) if name else match.group(1))
        if len(inline) == len(score.tracks):
            for track, name in zip(score.tracks, inline.values()):
                track.name = name
        return
    available = {}
    for index, track in enumerate(score.tracks):
        available.setdefault(_signature(track), []).append(index)
    matched = set()
    for voice in voices.values():
        isolated = "\n".join(header + [voice["declaration"], key] + voice["music"]) + "\n"
        try:
            decoded = Score.from_abc(isolated)
        except Exception:
            continue
        for track in decoded.tracks:
            options = available.get(_signature(track), [])
            while options and options[0] in matched:
                options.pop(0)
            if options:
                index = options.pop(0)
                score.tracks[index].name = voice["name"]
                matched.add(index)

    chord_counter = 0
    for index, track in enumerate(score.tracks):
        if index not in matched and not track.name:
            chord_counter += 1
            track.name = f"Chord-derived {chord_counter}" if QUOTED_CHORD.search(abc) else f"ABC Part {index + 1}"

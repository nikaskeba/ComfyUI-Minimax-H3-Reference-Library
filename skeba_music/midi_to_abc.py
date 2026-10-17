"""Convert connected MIDI bytes to editable ABC with Symusic's bundled midi2abc."""

from io import BytesIO
from pathlib import Path
import os
import re
import subprocess
import tempfile

import mido
import symusic
from comfy_api.latest import io


def _converter_path():
    binary = "midi2abc.exe" if os.name == "nt" else "midi2abc"
    path = Path(symusic.__file__).resolve().parent / "bin" / binary
    if not path.is_file():
        raise RuntimeError(f"Symusic's bundled MIDI-to-ABC converter is missing: {path}")
    return path


def _label_voices(abc, source):
    tracks = []
    for track in source.tracks:
        if not any(message.type == "note_on" and message.velocity > 0 for message in track):
            continue
        name = next((message.name for message in track if message.type == "track_name"), "")
        tracks.append(" ".join(name.replace('"', "'").split()))
    voice_ids = list(dict.fromkeys(re.findall(r"(?m)^V:\s*([^\s]+)", abc)))
    if len(tracks) != len(voice_ids):
        return abc
    names = dict(zip(voice_ids, tracks))
    seen = set()

    def add_name(match):
        voice_id = match.group(1)
        if voice_id in seen:
            return match.group(0)
        seen.add(voice_id)
        name = names.get(voice_id)
        return match.group(0) + f' name="{name}"' if name else match.group(0)

    return re.sub(r"(?m)^V:\s*([^\s]+)[^\n]*", add_name, abc)


def midi_to_abc(midi, title="MIDI transcription"):
    if not isinstance(midi, bytes) or not midi:
        raise ValueError("Connect MIDI bytes to the midi input.")
    try:
        source_midi = mido.MidiFile(file=BytesIO(midi))
    except Exception as error:
        raise ValueError(f"Input is not a readable MIDI file: {error}") from error
    title = " ".join(str(title).split()) or "MIDI transcription"
    converter = _converter_path()
    with tempfile.TemporaryDirectory(prefix="skeba_midi_to_abc_") as directory:
        source = Path(directory) / "source.mid"
        output = Path(directory) / "score.abc"
        source.write_bytes(midi)
        try:
            completed = subprocess.run(
                [str(converter), str(source), "-o", str(output), "-title", title],
                capture_output=True, text=True, timeout=120, check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("MIDI-to-ABC conversion exceeded two minutes.") from error
        if completed.returncode != 0 or not output.is_file():
            detail = (completed.stderr or completed.stdout).strip()
            raise RuntimeError(f"MIDI-to-ABC conversion failed: {detail or f'exit code {completed.returncode}'}")
        abc = output.read_text(encoding="utf-8", errors="replace").strip()
    if not abc or "X:" not in abc or "K:" not in abc:
        raise RuntimeError("MIDI-to-ABC converter returned no usable score.")
    return _label_voices(abc, source_midi) + "\n"


class SkebaMIDIToABC(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="SkebaMIDIToABC",
            display_name="Skeba MIDI to ABC",
            category="Skeba Music",
            description="Convert connected MIDI to editable ABC notation locally. The original MIDI is unchanged.",
            inputs=[
                io.Custom("YUE2_MIDI").Input("midi"),
                io.String.Input("title", default="MIDI transcription"),
            ],
            outputs=[io.String.Output(display_name="abc")],
        )

    @classmethod
    def execute(cls, midi, title="MIDI transcription"):
        return io.NodeOutput(midi_to_abc(midi, title))

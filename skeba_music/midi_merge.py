"""Put independent SheetSage and MuScriptor transcriptions in one MIDI file."""

from collections import defaultdict
from io import BytesIO
import math

import mido
import pretty_midi
from comfy_api.latest import io


TICKS_PER_BEAT = 480
ALIGNMENTS = ("Nearest 16th", "Preserve original timing")


def _single_tempo_and_meter(data, label):
    midi = mido.MidiFile(file=BytesIO(data))
    tempos = {message.tempo for track in midi.tracks for message in track if message.type == "set_tempo"}
    meters = {(message.numerator, message.denominator) for track in midi.tracks for message in track
              if message.type == "time_signature"}
    if len(tempos) != 1 or len(meters) != 1:
        raise ValueError(f"{label} MIDI must have one constant tempo and time signature.")
    tempo = tempos.pop()
    numerator, denominator = meters.pop()
    if tempo <= 0 or numerator <= 0 or denominator <= 0:
        raise ValueError(f"{label} MIDI has invalid tempo or meter.")
    return tempo, numerator, denominator


def _ticks(seconds, tempo, alignment):
    tick = round(seconds * 1_000_000 / tempo * TICKS_PER_BEAT)
    if alignment == "Nearest 16th":
        step = TICKS_PER_BEAT // 4
        tick = round(tick / step) * step
    return max(0, tick)


def _normalized_notes(instrument, tempo, alignment):
    notes = []
    for note in instrument.notes:
        if not all(math.isfinite(value) for value in (note.start, note.end)) or note.start < 0 or note.end <= note.start:
            continue
        start = _ticks(note.start, tempo, alignment)
        end = _ticks(note.end, tempo, alignment)
        if end <= start:
            end = start + (TICKS_PER_BEAT // 4 if alignment == "Nearest 16th" else 1)
        notes.append([start, end, note.pitch, note.velocity])
    notes.sort(key=lambda item: (item[2], item[0], item[1]))
    # Retiggered notes of the same pitch must not overlap after snapping.
    previous = {}
    resolved = []
    for note in notes:
        prior = previous.get(note[2])
        if prior is not None and prior[1] > note[0]:
            if prior[0] == note[0]:
                prior[1] = max(prior[1], note[1])
                continue
            prior[1] = note[0]
        previous[note[2]] = note
        resolved.append(note)
    return sorted(resolved, key=lambda item: (item[0], item[2], item[1]))


def merge_transcriptions(sheetsage_midi, muscriptor_midi, alignment="Nearest 16th"):
    if alignment not in ALIGNMENTS:
        raise ValueError(f"Unknown alignment: {alignment}")
    if not isinstance(sheetsage_midi, bytes) or not isinstance(muscriptor_midi, bytes):
        raise ValueError("Connect MIDI bytes from both SheetSage ABC to MIDI and SKEBA MuScriptor.")

    tempo, numerator, denominator = _single_tempo_and_meter(sheetsage_midi, "SheetSage")
    other_tempo, other_num, other_den = _single_tempo_and_meter(muscriptor_midi, "MuScriptor")
    if (numerator, denominator) != (other_num, other_den):
        raise ValueError("SheetSage and MuScriptor meters differ. Feed the same SheetSage ABC to MuScriptor.")
    source_parts = (("SheetSage", pretty_midi.PrettyMIDI(BytesIO(sheetsage_midi))),
                    ("MuScriptor", pretty_midi.PrettyMIDI(BytesIO(muscriptor_midi))))
    if not any(source.instruments for _, source in source_parts):
        raise ValueError("Both transcription MIDIs are empty.")

    output = mido.MidiFile(type=1, ticks_per_beat=TICKS_PER_BEAT)
    meta = mido.MidiTrack()
    meta.append(mido.MetaMessage("track_name", name="Tempo and meter", time=0))
    meta.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))
    meta.append(mido.MetaMessage("time_signature", numerator=numerator, denominator=denominator, time=0))
    output.tracks.append(meta)

    musical_count = sum(not instrument.is_drum for _, source in source_parts for instrument in source.instruments)
    if musical_count > 15:
        raise ValueError("Combined MIDI has more than 15 melodic tracks, exceeding MIDI's available channels. Narrow the MuScriptor instrument selection.")
    melodic_channels = iter(channel for channel in range(16) if channel != 9)
    counts = defaultdict(int)
    for label, source in source_parts:
        for index, instrument in enumerate(source.instruments, 1):
            name = (instrument.name or f"Part {index}").strip()
            track = mido.MidiTrack()
            track.append(mido.MetaMessage("track_name", name=name, time=0))
            channel = 9 if instrument.is_drum else next(melodic_channels)
            if not instrument.is_drum:
                track.append(mido.Message("program_change", channel=channel, program=instrument.program, time=0))
            changes = []
            notes = _normalized_notes(instrument, tempo, alignment)
            counts[label] += len(notes)
            for start, end, pitch, velocity in notes:
                changes.extend(((start, 1, pitch, velocity), (end, 0, pitch, 0)))
            previous_tick = 0
            for tick, on, pitch, velocity in sorted(changes):
                track.append(mido.Message("note_on" if on else "note_off", channel=channel, note=pitch,
                                          velocity=velocity, time=tick - previous_tick))
                previous_tick = tick
            output.tracks.append(track)

    stream = BytesIO()
    output.save(file=stream)
    bpm = 60_000_000 / tempo
    warning = ""
    if abs(other_tempo - tempo) > 1:
        warning = f" MuScriptor tempo differed; absolute note times were mapped to SheetSage's {bpm:.3f} BPM."
    report = (f"{len(output.tracks) - 1} separate music tracks; SheetSage {counts['SheetSage']} notes; "
              f"MuScriptor {counts['MuScriptor']} notes; {bpm:.3f} BPM, {numerator}/{denominator}; "
              f"alignment: {alignment}.{warning} Both models remain on separate instrument-named tracks; this does not correct differing transcription choices.")
    return stream.getvalue(), report


class SkebaCombineTranscriptionMIDIs(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="SkebaCombineTranscriptionMIDIs",
            display_name="SKEBA Combine Transcription MIDIs",
            category="Skeba Music",
            description="Combine SheetSage score MIDI and MuScriptor MIDI as separate instrument-named tracks on the SheetSage tempo grid.",
            inputs=[
                io.Custom("YUE2_MIDI").Input("sheetsage_midi"),
                io.Custom("YUE2_MIDI").Input("muscriptor_midi"),
                io.Combo.Input("alignment", options=list(ALIGNMENTS), default="Nearest 16th"),
            ],
            outputs=[io.Custom("YUE2_MIDI").Output(display_name="midi"),
                     io.String.Output(display_name="report")],
        )

    @classmethod
    def execute(cls, sheetsage_midi, muscriptor_midi, alignment="Nearest 16th"):
        midi, report = merge_transcriptions(sheetsage_midi, muscriptor_midi, alignment)
        return io.NodeOutput(midi, report)

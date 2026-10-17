from io import BytesIO
from fractions import Fraction
import json
import logging

import numpy as np
import pretty_midi
import torchaudio

import comfy.model_management
from comfy.audio_encoders.sheetsage2_abc import events_to_abc
from comfy.audio_encoders.sheetsage2_abc import BeatEvent, MelodyVoiceError, infer_measures, _build_grid, _quantize_time


def beat_map_from_events(events, duration):
    """Export the same decoded rhythm grid that SheetSage uses to write ABC."""
    beats, meter = [], None
    for event in events:
        rhythm = event["values"].get("rhythm", {})
        meter = rhythm.get("meter", meter)
        eighth = rhythm.get("eighth_position")
        if eighth is not None and meter is not None:
            position = Fraction(eighth * meter[1], 8)
            if position.denominator != 1 or not 0 <= position < meter[0]:
                raise ValueError("SheetSage decoded an invalid beat position.")
            beats.append(BeatEvent(event["time"], int(position) + 1, meter[0], meter[1]))
    if len(beats) < 2 or any(b.time <= a.time for a, b in zip(beats, beats[1:])):
        raise ValueError("SheetSage did not decode a usable increasing beat map.")
    period = float(np.median(np.diff([beat.time for beat in beats[-9:]])))
    while beats[-1].time < duration - 1e-6:
        previous = beats[-1]
        beats.append(BeatEvent(previous.time + period, previous.beat_id % previous.declared_numerator + 1,
                               previous.declared_numerator, previous.denominator))
    measures, _ = infer_measures(beats)
    times, quarters, _ = _build_grid(beats, measures)
    first = measures[0]
    leading_quarters = (4 * (first.abc_numerator / first.abc_denominator
                             - first.numerator / first.denominator)) if first.pad_before else 0
    return json.dumps({"version": 1, "source_duration": duration,
                       "times": times.tolist(),
                       "quarters": (quarters + leading_quarters).tolist()}, separators=(",", ":"))


def abc_from_events(events, duration, melody_only, abc_error_mode="skip_invalid_notes"):
    try:
        return events_to_abc(events, duration, melody_only=melody_only)
    except MelodyVoiceError:
        if abc_error_mode == "strict":
            raise

    # Reuse the native beat grid; only remove notes that collapse to zero grid length.
    beats, meter = [], None
    for event in events:
        rhythm = event["values"].get("rhythm", {})
        meter = rhythm.get("meter", meter)
        eighth = rhythm.get("eighth_position")
        if eighth is not None and meter is not None:
            position = Fraction(eighth * meter[1], 8)
            beats.append(BeatEvent(event["time"], int(position) + 1, meter[0], meter[1]))
    period = float(np.median(np.diff([beat.time for beat in beats[-9:]])))
    while beats[-1].time < duration - 1e-6:
        previous = beats[-1]
        beats.append(BeatEvent(previous.time + period, previous.beat_id % previous.declared_numerator + 1,
                               previous.declared_numerator, previous.denominator))
    measures, _ = infer_measures(beats)
    times, _, _ = _build_grid(beats, measures)
    cleaned = [{**event, "values": {**event["values"], "melody": []}} for event in events]
    skipped = 0
    for track in (0, 1):
        notes = [(event["time"], min(duration, note["end_time"]), note["pitch"], index, note)
                 for index, event in enumerate(events) for note in event["values"].get("melody", ())
                 if note["track"] == track and min(duration, note["end_time"]) > event["time"]]
        notes.sort(key=lambda row: (row[0], row[2], row[1]))
        for i, (start, end, pitch, index, note) in enumerate(notes):
            if i + 1 < len(notes) and end > notes[i + 1][0] + 1e-6:
                end = notes[i + 1][0]
            if end <= start + 1e-6:
                continue
            start_t, end_t = _quantize_time(start, times), _quantize_time(end, times)
            if end_t <= start_t and start_t < len(times) - 1:
                skipped += 1
                continue
            cleaned[index]["values"]["melody"].append({**note, "end_time": end})
    abc = events_to_abc(cleaned, duration, melody_only=melody_only)
    logging.warning("[Skeba Music] ABC omitted %d notes shorter than the decoded grid. Raw MIDI is unchanged. Use abc_error_mode=strict to reject these scores.", skipped)
    return abc


def events_to_midi(events, duration):
    midi = pretty_midi.PrettyMIDI(resolution=960)
    tracks = [pretty_midi.Instrument(program=0, name=name) for name in ("Vocal", "Ins")]
    for event in events:
        for note in event["values"].get("melody", ()):
            start = event["time"]
            end = min(duration, note["end_time"])
            if end > start:
                tracks[note["track"]].notes.append(pretty_midi.Note(100, note["pitch"], start, end))
    midi.instruments.extend(tracks)
    stream = BytesIO()
    midi.write(stream)
    return stream.getvalue()


def transcribe(audio_encoder, audio, sample_rate, melody_only, abc_error_mode="skip_invalid_notes"):
    audio = torchaudio.functional.resample(audio.float().mean(dim=1), sample_rate, audio_encoder.model_sample_rate)
    comfy.model_management.load_model_gpu(audio_encoder.patcher)
    scores, midis, beat_maps = [], [], []
    for waveform in audio:
        events = audio_encoder.model.transcribe(waveform[None].to(audio_encoder.load_device))
        duration = waveform.shape[-1] / audio_encoder.model_sample_rate
        scores.append(abc_from_events(events, duration, melody_only, abc_error_mode))
        midis.append(events_to_midi(events, duration))
        beat_maps.append(beat_map_from_events(events, duration))
    return scores, midis, beat_maps

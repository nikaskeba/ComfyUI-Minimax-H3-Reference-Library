"""Conservatively repair isolated MIDI onset errors in established pulse runs."""

from collections import Counter, defaultdict, deque
from io import BytesIO

import mido
from comfy_api.latest import io


SUBDIVISIONS = {"Eighth": 2, "Sixteenth": 4, "Thirty-second": 8}


def _notes_and_events(track):
    absolute = 0
    events = []
    active = defaultdict(deque)
    notes = []
    for order, message in enumerate(track):
        absolute += message.time
        if message.type == "end_of_track":
            continue
        event = {"tick": absolute, "order": order, "message": message}
        events.append(event)
        if message.type == "note_on" and message.velocity > 0:
            active[(message.channel, message.note)].append(event)
        elif message.type == "note_off" or (message.type == "note_on" and message.velocity == 0):
            starts = active[(message.channel, message.note)]
            if starts:
                start = starts.popleft()
                notes.append({"start": start, "end": event, "channel": message.channel, "pitch": message.note})
    return events, notes


def _grid_phase(onsets, step):
    phases = Counter(tick % step for tick in onsets)
    return max(phases, key=lambda phase: (phases[phase], -min(phase, step - phase)))


def _safe_move(group, notes_by_pitch, destination, source):
    shift = destination - source
    for note in group:
        start = note["start"]["tick"]
        end = note["end"]["tick"]
        if start + shift < 0:
            return False
        for other in notes_by_pitch[(note["channel"], note["pitch"])]:
            if other is note:
                continue
            other_start = other["start"]["tick"]
            other_end = other["end"]["tick"]
            if start + shift < other_end and end + shift > other_start:
                return False
    return True


def _group_signature(group):
    return tuple(sorted((note["channel"], note["pitch"], note["end"]["tick"] - note["start"]["tick"])
                        for note in group))


def _stabilize_track(track, step, tolerance_ticks, min_prior_intervals, correct_on_grid_step):
    events, notes = _notes_and_events(track)
    by_onset = defaultdict(list)
    by_pitch = defaultdict(list)
    for note in notes:
        by_onset[note["start"]["tick"]].append(note)
        by_pitch[(note["channel"], note["pitch"])].append(note)
    onsets = sorted(by_onset)
    if len(onsets) < min_prior_intervals + 2:
        return track, []
    phase = _grid_phase(onsets, step)
    corrected_onsets = []
    changes = []
    for index, onset in enumerate(onsets):
        destination = onset
        if len(corrected_onsets) >= min_prior_intervals + 1:
            previous = corrected_onsets[-(min_prior_intervals + 1):]
            intervals = [b - a for a, b in zip(previous, previous[1:])]
            interval = intervals[0]
            if interval > 0 and interval % step == 0 and all(value == interval for value in intervals):
                expected = previous[0] + (min_prior_intervals + 1) * interval
                next_onset = onsets[index + 1] if index + 1 < len(onsets) else None
                nearest = phase + round((onset - phase) / step) * step
                near_grid = ((onset - phase) % step != 0
                             and 0 < abs(onset - expected) <= tolerance_ticks
                             and nearest == expected)
                repeated_notes = (next_onset is not None and next_onset == expected + interval
                                  and all(_group_signature(by_onset[onsets[prior]]) == _group_signature(by_onset[onset])
                                          for prior in range(index - min_prior_intervals - 1, index))
                                  and _group_signature(by_onset[next_onset]) == _group_signature(by_onset[onset]))
                one_step = (correct_on_grid_step and (onset - phase) % step == 0
                            and abs(onset - expected) == step and repeated_notes)
                if ((near_grid or one_step)
                        and (next_onset is None or expected < next_onset)
                        and _safe_move(by_onset[onset], by_pitch, expected, onset)):
                    destination = expected
                    shift = destination - onset
                    for note in by_onset[onset]:
                        note["start"]["tick"] += shift
                        note["end"]["tick"] += shift
                    changes.append((onset, destination))
        corrected_onsets.append(destination)

    if not changes:
        return track, changes
    ordered = sorted(events, key=lambda event: (
        event["tick"],
        2 if event["message"].type == "note_on" and event["message"].velocity > 0 else
        1 if event["message"].type in ("note_on", "note_off") else 0,
        event["order"],
    ))
    output = mido.MidiTrack()
    previous_tick = 0
    for event in ordered:
        tick = event["tick"]
        output.append(event["message"].copy(time=tick - previous_tick))
        previous_tick = tick
    output.append(mido.MetaMessage("end_of_track", time=0))
    return output, changes


def stabilize_midi(midi_bytes, enabled=True, subdivision="Sixteenth", tolerance_ticks=20,
                   min_prior_intervals=3, correct_on_grid_step=False):
    if not isinstance(midi_bytes, bytes):
        raise ValueError("Connect a YUE2_MIDI byte output to midi.")
    if subdivision not in SUBDIVISIONS:
        raise ValueError(f"Unknown subdivision: {subdivision}")
    if not 0 <= tolerance_ticks <= 240 or not 2 <= min_prior_intervals <= 8:
        raise ValueError("tolerance_ticks must be 0–240 and min_prior_intervals must be 2–8.")
    source = mido.MidiFile(file=BytesIO(midi_bytes))
    step, remainder = divmod(source.ticks_per_beat, SUBDIVISIONS[subdivision])
    if remainder:
        raise ValueError(f"MIDI PPQ {source.ticks_per_beat} cannot be divided into exact {subdivision.lower()} notes.")
    if tolerance_ticks >= step / 2:
        raise ValueError("tolerance_ticks must be less than half a subdivision to preserve distinct grid positions.")
    if not enabled:
        return midi_bytes, "Pattern stabilization is off; MIDI bytes are unchanged."

    result = mido.MidiFile(type=source.type, ticks_per_beat=source.ticks_per_beat)
    summaries = []
    for index, track in enumerate(source.tracks):
        corrected, changes = _stabilize_track(track, step, tolerance_ticks, min_prior_intervals,
                                              correct_on_grid_step)
        result.tracks.append(corrected)
        if changes:
            name = next((message.name for message in track if message.type == "track_name"), f"Track {index}")
            examples = ", ".join(f"{old}→{new}" for old, new in changes[:6])
            summaries.append(f"{name}: {len(changes)} onset groups ({examples})")
    if not summaries:
        return midi_bytes, (f"No high-confidence timing corrections; original MIDI bytes retained. "
                            f"Grid: {subdivision.lower()}, {step} ticks; on-grid step: "
                            f"{'enabled' if correct_on_grid_step else 'off'}.")
    stream = BytesIO()
    result.save(file=stream)
    report = (f"Grid: {subdivision.lower()}, {step} ticks at PPQ {source.ticks_per_beat}; "
              f"tolerance: {tolerance_ticks} ticks; on-grid step: "
              f"{'enabled' if correct_on_grid_step else 'off'}; "
              + "; ".join(summaries) + ". Note pitches, velocities, and durations are unchanged.")
    return stream.getvalue(), report


class SkebaMIDIPatternStabilizer(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="SkebaMIDIPatternStabilizer",
            display_name="SKEBA MIDI Pattern Stabilizer",
            category="Skeba Music",
            description="Correct isolated near-grid onsets only after a repeated spacing pattern is established; preserves note durations.",
            inputs=[
                io.Custom("YUE2_MIDI").Input("midi"),
                io.Boolean.Input("enabled", default=True),
                io.Combo.Input("subdivision", options=list(SUBDIVISIONS), default="Sixteenth"),
                io.Int.Input("tolerance_ticks", default=20, min=0, max=240, step=1),
                io.Int.Input("min_prior_intervals", default=3, min=2, max=8, step=1),
                io.Boolean.Input("correct_on_grid_step", default=False),
            ],
            outputs=[io.Custom("YUE2_MIDI").Output(display_name="midi"),
                     io.String.Output(display_name="report")],
        )

    @classmethod
    def execute(cls, midi, enabled=True, subdivision="Sixteenth", tolerance_ticks=20,
                min_prior_intervals=3, correct_on_grid_step=False):
        data, report = stabilize_midi(midi, enabled, subdivision, tolerance_ticks,
                                      min_prior_intervals, correct_on_grid_step)
        return io.NodeOutput(data, report)

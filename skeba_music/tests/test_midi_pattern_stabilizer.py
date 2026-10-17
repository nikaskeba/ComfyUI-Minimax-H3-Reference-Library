import importlib.util
from io import BytesIO
from pathlib import Path
import sys
import unittest

import mido


sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
spec = importlib.util.spec_from_file_location("skeba_midi_pattern_stabilizer", Path(__file__).parents[1] / "midi_pattern_stabilizer.py")
stabilizer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stabilizer)


def make_midi(onsets, duration=100, phase=0, pitches=None):
    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    meta = mido.MidiTrack()
    meta.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    meta.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))
    midi.tracks.append(meta)
    track = mido.MidiTrack()
    track.append(mido.MetaMessage("track_name", name="Repeated rhythm", time=0))
    events = []
    for index, onset in enumerate(onsets):
        pitch = pitches[index] if pitches else 60
        velocity = 60 + index % 60
        events.extend(((onset + phase, 1, pitch, velocity), (onset + phase + duration, 0, pitch, 0)))
    previous = 0
    for tick, on, pitch, velocity in sorted(events):
        track.append(mido.Message("note_on" if on else "note_off", channel=0, note=pitch,
                                  velocity=velocity, time=tick - previous))
        previous = tick
    midi.tracks.append(track)
    output = BytesIO()
    midi.save(file=output)
    return output.getvalue()


def notes(data):
    midi = mido.MidiFile(file=BytesIO(data))
    track = midi.tracks[1]
    tick = 0
    active = {}
    result = []
    for message in track:
        tick += message.time
        if message.type == "note_on" and message.velocity:
            active[message.note] = (tick, message.velocity)
        elif message.type in ("note_off", "note_on") and message.note in active:
            start, velocity = active.pop(message.note)
            result.append((start, tick - start, message.note, velocity))
    return result


class StabilizerTests(unittest.TestCase):
    def test_premature_note_near_bar_five_corrects_without_changing_properties(self):
        original = make_midi([6720, 6960, 7200, 7440, 7665])
        data, report = stabilizer.stabilize_midi(original)
        self.assertEqual([note[0] for note in notes(data)], [6720, 6960, 7200, 7440, 7680])
        self.assertEqual([note[1:] for note in notes(data)], [note[1:] for note in notes(original)])
        self.assertIn("7665→7680", report)

    def test_late_note_and_repeated_corrections_do_not_accumulate_drift(self):
        onsets = [step * 240 for step in range(100)]
        onsets[4] += 15
        onsets[49] -= 12
        data, _ = stabilizer.stabilize_midi(make_midi(onsets))
        self.assertEqual([note[0] for note in notes(data)], [step * 240 for step in range(100)])

    def test_intentional_syncopation_on_grid_and_nonpattern_notes_stay_unchanged(self):
        for onsets in ([0, 240, 480, 720, 840], [0, 240, 480, 720, 1100], [0, 240, 600, 840, 1065]):
            original = make_midi(onsets)
            data, _ = stabilizer.stabilize_midi(original)
            self.assertEqual(data, original)

    def test_existing_phase_and_tolerance_are_respected(self):
        original = make_midi([0, 240, 480, 720, 945], phase=1)
        corrected, _ = stabilizer.stabilize_midi(original)
        self.assertEqual([note[0] for note in notes(corrected)], [1, 241, 481, 721, 961])
        not_corrected, _ = stabilizer.stabilize_midi(original, tolerance_ticks=10)
        self.assertEqual(not_corrected, original)

    def test_disable_returns_identical_bytes(self):
        original = make_midi([0, 240, 480, 720, 945])
        data, report = stabilizer.stabilize_midi(original, enabled=False)
        self.assertEqual(data, original)
        self.assertIn("off", report)

    def test_optional_one_grid_step_correction_requires_rejoining_same_note_pattern(self):
        onsets = [0, 240, 480, 720, 840, 1200]
        original = make_midi(onsets)
        self.assertEqual(stabilizer.stabilize_midi(original)[0], original)
        corrected, report = stabilizer.stabilize_midi(original, correct_on_grid_step=True)
        self.assertEqual([note[0] for note in notes(corrected)], [0, 240, 480, 720, 960, 1200])
        self.assertEqual([note[1:] for note in notes(corrected)], [note[1:] for note in notes(original)])
        self.assertIn("840→960", report)

        # A different pitch is a plausible intentional syncopation, even with the option on.
        variation = make_midi(onsets, pitches=[60, 60, 60, 60, 64, 60])
        self.assertEqual(stabilizer.stabilize_midi(variation, correct_on_grid_step=True)[0], variation)
        # Without a confirming note after the candidate, an on-grid shift is ambiguous.
        tail = make_midi(onsets[:-1])
        self.assertEqual(stabilizer.stabilize_midi(tail, correct_on_grid_step=True)[0], tail)

    def test_tolerance_must_not_span_distinct_grid_steps(self):
        with self.assertRaisesRegex(ValueError, "half a subdivision"):
            stabilizer.stabilize_midi(make_midi([0, 240, 480, 720, 945]), tolerance_ticks=60)


if __name__ == "__main__":
    unittest.main()

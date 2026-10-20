import importlib.util
from io import BytesIO
from pathlib import Path
import sys
import unittest

import mido
import pretty_midi

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

spec = importlib.util.spec_from_file_location("skeba_midi_merge", Path(__file__).parents[1] / "midi_merge.py")
merge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(merge)


def midi_bytes(tempo=468750, meter=(4, 4), parts=(("voice", 0, False),), offset=0.001):
    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    meta = mido.MidiTrack()
    meta.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))
    meta.append(mido.MetaMessage("time_signature", numerator=meter[0], denominator=meter[1], time=0))
    midi.tracks.append(meta)
    for index, (name, program, drums) in enumerate(parts):
        track = mido.MidiTrack()
        track.append(mido.MetaMessage("track_name", name=name, time=0))
        channel = 9 if drums else index
        if not drums:
            track.append(mido.Message("program_change", channel=channel, program=program, time=0))
        start = round((1.875 + offset) * 1_000_000 / tempo * 480)
        track.append(mido.Message("note_on", channel=channel, note=36 if drums else 60 + index,
                                  velocity=90, time=start))
        track.append(mido.Message("note_off", channel=channel, note=36 if drums else 60 + index,
                                  velocity=0, time=480))
        midi.tracks.append(track)
    output = BytesIO()
    midi.save(file=output)
    return output.getvalue()


class MergeTests(unittest.TestCase):
    def setUp(self):
        self.sheet = midi_bytes(parts=(("Vocal", 0, False), ("Chords", 48, False), ("Ins", 0, False)))
        self.muscriptor = midi_bytes(parts=(("drums", 0, True), ("synth_pad", 88, False)), offset=0)

    def test_labeled_tracks_share_tempo_grid_and_preserve_instruments(self):
        data, report = merge.merge_transcriptions(self.sheet, self.muscriptor)
        parsed = mido.MidiFile(file=BytesIO(data))
        self.assertEqual(parsed.type, 1)
        self.assertEqual(parsed.ticks_per_beat, 480)
        self.assertEqual(len(parsed.tracks), 6)
        self.assertEqual(parsed.tracks[0][1].tempo, 468750)
        names = [next(message.name for message in track if message.type == "track_name") for track in parsed.tracks[1:]]
        self.assertEqual(names, ["Vocal", "Chords", "Ins", "drums", "synth_pad"])
        self.assertTrue(any(message.type == "note_on" and message.channel == 9 for message in parsed.tracks[4]))
        self.assertTrue(any(message.type == "program_change" and message.program == 88 for message in parsed.tracks[5]))
        notes = pretty_midi.PrettyMIDI(BytesIO(data))
        self.assertTrue(all(abs(track.notes[0].start - 1.875) < 0.0001 for track in notes.instruments))
        self.assertIn("5 separate music tracks", report)

    def test_original_timing_option_keeps_one_tick_difference(self):
        data, _ = merge.merge_transcriptions(self.sheet, self.muscriptor, "Preserve original timing")
        notes = pretty_midi.PrettyMIDI(BytesIO(data)).instruments
        self.assertGreater(notes[0].notes[0].start, notes[3].notes[0].start)

    def test_different_tempo_uses_sheet_master_without_drifting_in_seconds(self):
        slower = midi_bytes(tempo=500000, parts=(("drums", 0, True),), offset=0)
        data, report = merge.merge_transcriptions(self.sheet, slower)
        self.assertIn("tempo differed", report)
        notes = pretty_midi.PrettyMIDI(BytesIO(data)).instruments
        self.assertAlmostEqual(notes[-1].notes[0].start, 1.875, places=3)

    def test_mismatched_meter_is_rejected(self):
        other = midi_bytes(meter=(3, 4))
        with self.assertRaisesRegex(ValueError, "meters differ"):
            merge.merge_transcriptions(self.sheet, other)


if __name__ == "__main__":
    unittest.main()

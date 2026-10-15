import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import mido


MODULE_PATH = Path(__file__).resolve().parents[1] / "midi_for_ableton.py"


def load_node(output_dir):
    spec = importlib.util.spec_from_file_location("skeba_midi_for_ableton_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"folder_paths": types.SimpleNamespace(get_output_directory=lambda: str(output_dir))}):
        spec.loader.exec_module(module)
    return module.SkebaMidiForAbleton()


def note_times(path):
    midi = mido.MidiFile(path)
    tempo = next(message.tempo for message in midi.tracks[0] if message.type == "set_tempo")
    result = []
    for track in midi.tracks:
        ticks = 0
        for message in track:
            ticks += message.time
            if message.type in ("note_on", "note_off"):
                result.append((message.type, message.note, ticks * tempo / 1_000_000 / midi.ticks_per_beat))
    return sorted(result), tempo


class MidiForAbletonTests(unittest.TestCase):
    def test_preserves_note_seconds_and_separate_tracks(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "muscriptor.mid"
            midi = mido.MidiFile(type=1, ticks_per_beat=480)
            midi.tracks.append(mido.MidiTrack([mido.MetaMessage("set_tempo", tempo=500000, time=0)]))
            midi.tracks.append(mido.MidiTrack([
                mido.MetaMessage("track_name", name="acoustic piano", time=0),
                mido.Message("note_on", note=60, velocity=100, time=960),
                mido.Message("note_off", note=60, velocity=0, time=480),
            ]))
            midi.tracks.append(mido.MidiTrack([
                mido.MetaMessage("track_name", name="drums", time=0),
                mido.Message("note_on", note=36, velocity=100, channel=9, time=480),
                mido.Message("note_off", note=36, velocity=0, channel=9, time=240),
            ]))
            midi.save(source)
            original_events, original_tempo = note_times(source)

            output, bpm = load_node(directory).prepare(str(source), 112.34714673912777, "2 decimals")
            converted = mido.MidiFile(output)
            converted_events, _ = note_times(output)
            self.assertEqual(len(converted.tracks), 3)
            self.assertEqual([track[0].name for track in converted.tracks[1:]], ["acoustic piano", "drums"])
            self.assertAlmostEqual(bpm, 112.35, places=3)
            self.assertEqual(original_tempo, 500000)
            self.assertEqual(note_times(source)[0], original_events)
            for before, after in zip(original_events, converted_events):
                self.assertEqual(before[:2], after[:2])
                self.assertAlmostEqual(before[2], after[2], delta=0.002)

    def test_rejects_midi_outside_output_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "output"
            output_dir.mkdir()
            outside = Path(directory) / "other.mid"
            outside.write_bytes(b"")
            with self.assertRaisesRegex(ValueError, "inside ComfyUI/output"):
                load_node(output_dir).prepare(str(outside), 112.0, "whole BPM")


if __name__ == "__main__":
    unittest.main()

import importlib.util
from pathlib import Path
import sys
import unittest

from symusic import Score


ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
MUSIC = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("skeba_midi_to_abc", MUSIC / "midi_to_abc.py")
converter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(converter)


class MIDIToABCTests(unittest.TestCase):
    def test_local_conversion_preserves_input_and_round_trips(self):
        data = (MUSIC / "examples" / "two_voices.mid").read_bytes()
        original = bytes(data)
        abc = converter.midi_to_abc(data, "Two voices")
        self.assertIn("T: Two voices", abc)
        self.assertRegex(abc, r"(?m)^M:\s*4/4")
        self.assertRegex(abc, r"(?m)^Q:")
        self.assertRegex(abc, r"(?m)^V:")
        self.assertIn('name="Vocal Melody"', abc)
        self.assertIn('name="Ins Melody"', abc)
        self.assertGreater(sum(len(track.notes) for track in Score.from_abc(abc).tracks), 0)
        self.assertEqual(data, original)
        self.assertEqual(converter.SkebaMIDIToABC.execute(data, "Two voices").result[0], abc)

    def test_invalid_midi_has_actionable_error(self):
        with self.assertRaisesRegex(ValueError, "Connect MIDI bytes"):
            converter.midi_to_abc(b"")
        with self.assertRaisesRegex(ValueError, "not a readable MIDI"):
            converter.midi_to_abc(b"not midi")

    def test_empty_title_uses_default(self):
        data = (MUSIC / "examples" / "two_voices.mid").read_bytes()
        abc = converter.midi_to_abc(data, "   ")
        self.assertIn("T: MIDI transcription", abc)


if __name__ == "__main__":
    unittest.main()

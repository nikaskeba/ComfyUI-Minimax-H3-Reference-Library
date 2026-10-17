import importlib.util
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("skeba_music_transcription", Path(__file__).parents[1] / "transcription.py")
transcription = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transcription)


class SheetSageBeatMapTests(unittest.TestCase):
    def test_exports_decoded_beats_and_pickup_padding(self):
        beats = [
            (0.5, 6), (1.0, 0), (1.5, 2), (2.0, 4), (2.5, 6), (3.0, 0),
            (3.5, 2), (4.0, 4), (4.5, 6), (5.0, 0),
        ]
        events = [{"time": time, "values": {"rhythm": {
            "meter": (4, 4), "eighth_position": position}}} for time, position in beats]
        result = json.loads(transcription.beat_map_from_events(events, 5.0))
        self.assertEqual(result["version"], 1)
        self.assertEqual(result["source_duration"], 5.0)
        self.assertEqual(result["times"][0], 0.5)
        self.assertEqual(result["quarters"][0], 3.0)
        self.assertEqual(result["times"][-1], 5.0)
        self.assertEqual(result["quarters"][-1], 12.0)

    def test_rejects_unusable_rhythm(self):
        with self.assertRaisesRegex(ValueError, "beat map"):
            transcription.beat_map_from_events([], 2.0)


if __name__ == "__main__":
    unittest.main()

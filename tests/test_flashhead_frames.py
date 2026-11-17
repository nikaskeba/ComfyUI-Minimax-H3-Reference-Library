import importlib.util
from pathlib import Path
import unittest

import torch


MODULE_PATH = Path(__file__).resolve().parents[1] / "flashhead_frames.py"
SPEC = importlib.util.spec_from_file_location("flashhead_frames_test", MODULE_PATH)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class FlashHeadFramesTests(unittest.TestCase):
    def test_concatenates_and_normalizes_frame_chunks(self):
        first = torch.full((2, 4, 4, 3), 255, dtype=torch.uint8)
        second = torch.zeros((1, 4, 4, 3), dtype=torch.uint8)
        frames = module._frames_from_chunks([first, second])
        self.assertEqual(tuple(frames.shape), (3, 4, 4, 3))
        self.assertEqual(frames.dtype, torch.float32)
        self.assertEqual(frames[0, 0, 0, 0].item(), 1.0)
        self.assertEqual(frames[2, 0, 0, 0].item(), 0.0)

    def test_empty_frames_report_short_audio(self):
        with self.assertRaisesRegex(ValueError, "no frames"):
            module._frames_from_chunks([])

    def test_audio_tracks_frame_duration_without_changing_input(self):
        source = torch.arange(1000, dtype=torch.float32).reshape(1, 2, 500)
        original = source.clone()
        output = module._matching_audio({"waveform": source, "sample_rate": 100}, 50, 25)
        self.assertEqual(tuple(output["waveform"].shape), (1, 2, 200))
        self.assertTrue(torch.equal(source, original))
        self.assertEqual(output["sample_rate"], 100)

    def test_input_and_outputs_match_upstream_connections(self):
        inputs = module.SkebaFlashHeadFrames.INPUT_TYPES()
        self.assertEqual(inputs["required"]["pipeline"][0], "RH_FlashHead_Pipeline")
        self.assertEqual(module.SkebaFlashHeadFrames.RETURN_TYPES, ("IMAGE", "AUDIO", "FLOAT"))


if __name__ == "__main__":
    unittest.main()

import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

import numpy as np
import torch
from PIL import Image

spec = importlib.util.spec_from_file_location("palette_sampling", Path(__file__).parents[1] / "palette_sampling.py")
module = importlib.util.module_from_spec(spec)
with mock.patch.dict(sys.modules, {"folder_paths": types.SimpleNamespace(get_temp_directory=lambda: "unused")}):
    spec.loader.exec_module(module)


class SamplingTests(unittest.TestCase):
    def test_exact_coordinate_mapping_and_hex(self):
        frame = np.zeros((5, 9, 4), dtype=np.float32)
        frame[2, 4, :3] = np.array([12, 231, 18]) / 255
        sample = module.sample_frame(frame, 0.5, 0.5, "Exact Pixel")
        self.assertEqual(sample, {"x": 4, "y": 2, "rgb": [12, 231, 18], "hex": "#0CE712"})

    def test_region_average_edges_and_round_after_average(self):
        frame = np.arange(7*7*3, dtype=np.float32).reshape(7, 7, 3) / 255
        for mode, radius in module.SAMPLING_MODES.items():
            for u, v, x, y in [(0, 0, 0, 0), (1, 1, 6, 6), (0.5, 0.5, 3, 3)]:
                patch = frame[max(0,y-radius):min(7,y+radius+1), max(0,x-radius):min(7,x+radius+1)]
                expected = np.floor(patch.astype(np.float64).mean((0,1))*255+0.5).astype(int).tolist()
                self.assertEqual(module.sample_frame(frame, u, v, mode)["rgb"], expected)
        self.assertEqual(module.sample_frame(frame, -2, 5, "Exact Pixel")["x"], 0)
        with self.assertRaises(ValueError):
            module.sample_frame(frame, float("nan"), 0, "Exact Pixel")

    def test_preview_clamps_selected_frame_and_samples_original(self):
        image = torch.zeros((3, 4, 6, 4))
        image[2, ..., :3] = torch.tensor([0.049, 0.906, 0.071])
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(module, "preview_directory", return_value=Path(directory)):
            result = module.PaletteFramePreview().preview(image, 500)["ui"]["palette_preview"][0]
            self.assertEqual(result["frame"], 2)
            self.assertEqual((result["width"], result["height"]), (6, 4))
            original = np.load(Path(directory) / (result["token"] + ".npy"))
            np.testing.assert_array_equal(original, image[2, ..., :3].numpy())
            self.assertEqual(module.sample_preview(result["token"], 1, 1, "5x5 Average")["hex"], "#0CE712")
            self.assertTrue((Path(directory) / result["filename"]).exists())
            self.assertEqual(module.PaletteFramePreview().preview(image, -4)["ui"]["palette_preview"][0]["frame"], 0)
            with self.assertRaises(ValueError):
                module.sample_preview("../outside", 0, 0, "Exact Pixel")
            with self.assertRaises(FileNotFoundError):
                module.sample_preview("a"*32, 0, 0, "Exact Pixel")


if __name__ == "__main__":
    unittest.main()

import importlib.util
from pathlib import Path
import unittest

import numpy as np
import torch


path = Path(__file__).resolve().parents[1] / "h3_square_avatar.py"
spec = importlib.util.spec_from_file_location("h3_square_avatar_test", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SquareAvatarTests(unittest.TestCase):
    def test_square_crop_stays_on_canvas_without_padding(self):
        image = torch.rand(1, 720, 1280, 3)
        crop, info = module._crop_square(image, {"x": 1100, "y": 100, "width": 150, "height": 400})
        self.assertEqual(tuple(crop.shape), (1, 512, 512, 3))
        self.assertEqual(info["side"], 400)
        self.assertEqual(info["left"], 880)
        self.assertEqual(info["top"], 100)

    def test_composite_preserves_pixels_outside_square(self):
        image = torch.full((1, 720, 1280, 3), .25)
        crop, info = module._crop_square(image, {"x": 500, "y": 100, "width": 150, "height": 400})
        generated = torch.ones((3, 512, 512, 3))
        result = module._paste_square(image, generated, info, feather=12)
        self.assertEqual(tuple(result.shape), (3, 720, 1280, 3))
        self.assertTrue(torch.all(result[:, 0, 0] == .25))
        self.assertTrue(torch.all(result[:, info["top"] + 100, info["left"] + 100] == 1))
        self.assertEqual(image[0, 200, 550, 0].item(), .25)

    def test_edge_feather_stays_inside_crop(self):
        alpha = module._inner_alpha(64, 8)
        self.assertEqual(alpha[0, 10, 0], 0)
        self.assertEqual(alpha[10, 10, 0], 1)

    def test_missing_box_is_clear_error(self):
        with self.assertRaisesRegex(ValueError, "0 box"):
            module.SkebaAvatarSquareCrop().crop(torch.zeros((1, 20, 20, 3)), [[]])


if __name__ == "__main__":
    unittest.main()

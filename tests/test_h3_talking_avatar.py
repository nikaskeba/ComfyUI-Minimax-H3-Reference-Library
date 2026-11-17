import importlib.util
from pathlib import Path
import sys
import types
import unittest

import numpy as np
import torch


ROOT = Path(__file__).resolve().parents[1]
package = types.ModuleType("avatar_test_package")
package.__path__ = [str(ROOT)]
sys.modules[package.__name__] = package
mask_module = types.ModuleType("avatar_test_package.h3_person_reference_mask")
sys.modules[mask_module.__name__] = mask_module
spec = importlib.util.spec_from_file_location("avatar_test_package.h3_talking_avatar", ROOT / "h3_talking_avatar.py")
avatar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(avatar)


class Face:
    def __init__(self, box):
        self.bbox = np.array(box, dtype=np.float32)
        x0, y0, x1, y1 = box
        self.kps = np.array([
            [x0 + .3 * (x1 - x0), y0 + .35 * (y1 - y0)],
            [x0 + .7 * (x1 - x0), y0 + .35 * (y1 - y0)],
            [(x0 + x1) / 2, (y0 + y1) / 2],
            [x0 + .35 * (x1 - x0), y0 + .7 * (y1 - y0)],
            [x0 + .65 * (x1 - x0), y0 + .7 * (y1 - y0)],
        ], dtype=np.float32)
        self.normed_embedding = np.array([1., 0.], dtype=np.float32)


class Detector:
    def get(self, bgr):
        height, width = bgr.shape[:2]
        if width == 32:
            return [Face((8, 8, 24, 24))]
        shift = 16 if bgr[0, 0, 0] else 0
        return [Face((16 + shift, 16, 32 + shift, 32))]


mask_module._face_recogniser = lambda: Detector()
mask_module._yolo = lambda *args: None


class TalkingAvatarTests(unittest.TestCase):
    def test_still_body_over_background_with_moving_head_frames(self):
        person = torch.zeros(1, 64, 64, 3)
        person[..., 1] = 1
        background = torch.zeros(1, 64, 64, 3)
        background[..., 2] = 1
        head = torch.zeros(2, 32, 32, 3)
        head[..., 0] = 1
        mask = torch.zeros(1, 64, 64)
        mask[:, 8:56, 8:56] = 1
        frames, status = avatar.SkebaTalkingAvatarComposite().composite(
            person, background, head, person_mask=mask, feather=0)
        self.assertEqual(tuple(frames.shape), (2, 64, 64, 3))
        self.assertGreater(float(frames[0, 24, 24, 0]), .8)
        self.assertGreater(float(frames[0, 5, 5, 2]), .9)
        self.assertIn("2/2", status)

    def test_video_face_moves_and_short_video_fails(self):
        person = torch.zeros(2, 64, 64, 3)
        person[..., 1] = 1
        person[1, 0, 0, 2] = 1 / 255
        background = torch.zeros(1, 64, 64, 3)
        head = torch.zeros(2, 32, 32, 3)
        head[..., 0] = 1
        mask = torch.ones(2, 64, 64)
        frames, _ = avatar.SkebaTalkingAvatarComposite().composite(
            person, background, head, person_mask=mask, feather=0)
        self.assertGreater(float(frames[0, 24, 24, 0]), .8)
        self.assertGreater(float(frames[1, 24, 40, 0]), .8)
        with self.assertRaisesRegex(ValueError, "ends before FlashHead"):
            avatar.SkebaTalkingAvatarComposite().composite(
                person, background, torch.zeros(4, 32, 32, 3), person_mask=mask)


if __name__ == "__main__":
    unittest.main()

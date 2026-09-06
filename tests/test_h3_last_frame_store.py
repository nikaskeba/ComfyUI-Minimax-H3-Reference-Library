import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import torch


ROOT = Path(__file__).resolve().parents[1]


class H3LastFrameStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        folder_paths = types.SimpleNamespace(
            get_output_directory=lambda: self.temp.name
        )
        self.modules_patch = mock.patch.dict(sys.modules, {"folder_paths": folder_paths})
        self.modules_patch.start()
        spec = importlib.util.spec_from_file_location(
            "h3_last_frame_store_test", ROOT / "h3_last_frame_store.py"
        )
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def tearDown(self):
        self.modules_patch.stop()
        self.temp.cleanup()

    def test_saves_last_frame_and_loads_it_for_continuation(self):
        images = torch.stack([
            torch.zeros((3, 4, 3)),
            torch.ones((3, 4, 3)),
        ])
        path, = self.module.SkebaH3SaveLastFrame().save(images, "frames/clip", 2)
        self.assertTrue(Path(path).is_file())
        loaded, = self.module.SkebaH3LoopGuideImage().select(
            images[:1], False, 2, "frames/clip"
        )
        self.assertTrue(torch.equal(loaded, images[-1:]))

    def test_new_scene_uses_original_without_saved_file(self):
        original = torch.rand((1, 3, 4, 3))
        selected, = self.module.SkebaH3LoopGuideImage().select(
            original, True, 0, "frames/clip"
        )
        self.assertIs(selected, original)

    def test_missing_previous_frame_is_actionable(self):
        with self.assertRaisesRegex(FileNotFoundError, "no stored final frame"):
            self.module.SkebaH3LoopGuideImage().select(
                torch.zeros((1, 3, 4, 3)), False, 3, "frames/clip"
            )

    def test_original_image_is_lazy_on_continuations(self):
        node = self.module.SkebaH3LoopGuideImage()
        self.assertEqual(node.check_lazy_status(None, False), [])
        self.assertEqual(node.check_lazy_status(None, True), ["original_image"])


if __name__ == "__main__":
    unittest.main()

import importlib.util
import math
import sys
import tempfile
import types
import unittest
from pathlib import Path

import torch
from safetensors.torch import save_file


ROOT = Path(__file__).resolve().parents[1]


class H3LastFrameExposureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        folder_paths = types.ModuleType("folder_paths")
        folder_paths.get_output_directory = lambda: cls.temp.name
        sys.modules["folder_paths"] = folder_paths

        package = types.ModuleType("h3_tag_references")
        package.__path__ = [str(ROOT)]
        sys.modules.setdefault("h3_tag_references", package)

        for name in ("h3_last_frame_store", "h3_last_frame_exposure"):
            fullname = f"h3_tag_references.{name}"
            spec = importlib.util.spec_from_file_location(
                fullname, ROOT / f"{name}.py"
            )
            module = importlib.util.module_from_spec(spec)
            sys.modules[fullname] = module
            spec.loader.exec_module(module)
        cls.module = sys.modules["h3_tag_references.h3_last_frame_exposure"]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def _save_reference(self, clip_index, value):
        path = Path(self.temp.name) / "h3_context_frame" / f"clip_{clip_index:05d}.safetensors"
        path.parent.mkdir(parents=True, exist_ok=True)
        save_file({"image": torch.full((1, 3, 4, 3), value)}, str(path))

    def test_bypass_does_not_require_a_saved_frame(self):
        images = torch.full((8, 3, 4, 3), 0.55)
        (result,) = self.module.SkebaH3LastFrameExposureMatch().match(
            images, previous_clip_index=999, bypass=True
        )
        self.assertIs(result, images)

    def test_matches_first_frame_without_a_deadband_and_fades(self):
        self._save_reference(1, 0.5)
        images = torch.full((8, 3, 4, 3), 0.51)
        (result,) = self.module.SkebaH3LastFrameExposureMatch().match(
            images, previous_clip_index=1, bypass=False,
            strength=1.0, fade_frames=5, max_adjust_ev=0.125,
        )
        self.assertTrue(math.isclose(float(result[0].mean()), 0.5, rel_tol=1e-5))
        self.assertTrue(torch.equal(result[4], images[4]))
        self.assertTrue(torch.equal(result[5:], images[5:]))

    def test_adjustment_is_clamped(self):
        self._save_reference(2, 0.9)
        images = torch.full((4, 3, 4, 3), 0.1)
        (result,) = self.module.SkebaH3LastFrameExposureMatch().match(
            images, previous_clip_index=2, bypass=False,
            strength=1.0, fade_frames=2, max_adjust_ev=0.125,
        )
        expected = 0.1 * (2.0 ** 0.125)
        self.assertTrue(math.isclose(float(result[0].mean()), expected, rel_tol=1e-5))


if __name__ == "__main__":
    unittest.main()

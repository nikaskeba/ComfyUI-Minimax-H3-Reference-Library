import importlib.util
from pathlib import Path
import unittest

import torch


ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("skeba_h3_video_latent_resize_test", ROOT / "h3_video_latent_resize.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class VideoLatentResizeTests(unittest.TestCase):
    def test_aspect_match_keeps_exact_two_times_grid(self):
        source = {"samples": torch.randn(1, 24, 7, 52, 92)}
        result, = module.SkebaH3VideoLatentAspectMatch().match(source, 736, 416)
        self.assertIs(result, source)
        self.assertEqual((result["samples"].shape[-1] * 16,
                          result["samples"].shape[-2] * 16), (1472, 832))

    def test_aspect_match_prefers_nearby_exact_grid_at_two_times(self):
        source = {"samples": torch.randn(1, 24, 7, 50, 90)}
        result, = module.SkebaH3VideoLatentAspectMatch().match(source, 736, 416)
        self.assertEqual(tuple(result["samples"].shape[-2:]), (52, 92))

    def test_aspect_match_keeps_even_patch_grid_near_requested_scale(self):
        source = {"samples": torch.randn(1, 24, 7, 38, 68)}
        result, = module.SkebaH3VideoLatentAspectMatch().match(source, 736, 416)
        self.assertEqual(tuple(result["samples"].shape), (1, 24, 7, 38, 68))
        self.assertEqual(result["samples"].shape[-1] % 2, 0)
        self.assertEqual(result["samples"].shape[-2] % 2, 0)
        self.assertEqual(tuple(source["samples"].shape), (1, 24, 7, 38, 68))

    def test_loaded_av_context_preserves_audio_and_metadata(self):
        video = torch.randn(1, 24, 7, 39, 69)
        audio = torch.randn(1, 32, 2, 37)
        source = {"samples": [video, audio], "skeba_h3_original_audio_overhang_steps": 2.5}
        result, = module.SkebaH3AVContextResize().resize(736, 416, source)
        self.assertEqual(tuple(result["samples"][0].shape), (1, 24, 7, 26, 46))
        self.assertIs(result["samples"][1], audio)
        self.assertEqual(result["skeba_h3_original_audio_overhang_steps"], 2.5)
        self.assertIs(source["samples"][0], video)

    def test_first_prompt_bypass_stays_empty(self):
        placeholder = {"samples": None, "skeba_h3_motion_context_bypassed": True}
        result, = module.SkebaH3AVContextResize().resize(736, 416, placeholder)
        self.assertIs(result, placeholder)

    def test_loaded_context_rejects_ratio_drift(self):
        source = {"samples": [torch.zeros(1, 24, 7, 40, 68), torch.zeros(1, 32, 2, 37)]}
        with self.assertRaisesRegex(ValueError, "differ in aspect ratio"):
            module.SkebaH3AVContextResize().resize(736, 416, source)

    def test_downsizes_on_h3_sixteen_pixel_grid(self):
        source = {"samples": torch.randn(1, 24, 7, 40, 68), "marker": "unchanged"}
        result, = module.SkebaH3VideoLatentResize().resize(source, 736, 416)
        self.assertEqual(tuple(result["samples"].shape), (1, 24, 7, 26, 46))
        self.assertEqual(result["marker"], "unchanged")
        self.assertEqual(tuple(source["samples"].shape), (1, 24, 7, 40, 68))

    def test_rejects_ambiguous_grid_or_audio_stream(self):
        node = module.SkebaH3VideoLatentResize()
        with self.assertRaisesRegex(ValueError, "multiples of 16"):
            node.resize({"samples": torch.zeros(1, 24, 7, 40, 68)}, 735, 416)
        with self.assertRaisesRegex(ValueError, "Separate AV Latent"):
            node.resize({"samples": torch.zeros(1, 32, 2, 37)}, 736, 416)


if __name__ == "__main__":
    unittest.main()

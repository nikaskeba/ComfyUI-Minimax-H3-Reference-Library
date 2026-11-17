import importlib.util
from pathlib import Path
import sys
import unittest

import torch


ROOT = Path(__file__).resolve().parents[1]
COMFY_ROOT = ROOT.parents[1]
sys.path.insert(0, str(COMFY_ROOT))
spec = importlib.util.spec_from_file_location("h3_inpaint_source_scrub_test",
                                              ROOT / "h3_inpaint_source_scrub.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SourceScrubTests(unittest.TestCase):
    def test_clears_only_selected_video_region(self):
        video = torch.ones((1, 24, 2, 8, 8))
        mask = torch.zeros((4, 16, 16))
        mask[:, 4:12, 4:12] = 1
        result, selected, total = module._scrub_video(video, mask)
        self.assertEqual(selected, 2 * 4 * 4)
        self.assertEqual(total, 2 * 8 * 8)
        self.assertEqual(float(result[0, 0, 0, 3, 3]), 0)
        self.assertEqual(float(result[0, 0, 0, 0, 0]), 1)
        self.assertTrue(torch.all(video == 1))

    def test_joint_av_keeps_audio_and_mask_unchanged(self):
        import comfy.nested_tensor
        video = torch.ones((1, 24, 2, 8, 8))
        audio = torch.randn((1, 32, 2, 20))
        mask = torch.zeros((4, 16, 16))
        mask[:, 4:12, 4:12] = 1
        latent = {"samples": comfy.nested_tensor.NestedTensor((video, audio)),
                  "noise_mask": comfy.nested_tensor.NestedTensor((mask, torch.zeros_like(audio))),
                  "other": "retained"}
        result, status = module.SkebaH3InpaintSourceScrub().scrub(latent, True, 0, 0)
        actual_video, actual_audio = result["samples"].unbind()
        self.assertTrue(torch.equal(actual_audio, audio))
        self.assertIs(result["noise_mask"], latent["noise_mask"])
        self.assertEqual(result["other"], "retained")
        self.assertEqual(float(actual_video[0, 0, 0, 3, 3]), 0)
        self.assertEqual(float(video[0, 0, 0, 3, 3]), 1)
        self.assertIn("audio untouched", status)
        bypassed, _ = module.SkebaH3InpaintSourceScrub().scrub(latent, False)
        self.assertIs(bypassed, latent)


if __name__ == "__main__":
    unittest.main()

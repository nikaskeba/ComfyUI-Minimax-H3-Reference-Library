"""The continuation refiner samples only the tail and preserves the full clip."""

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent.parent))
try:
    import torch
    spec = importlib.util.spec_from_file_location("skeba_h3_tail_refiner_test", ROOT / "h3_tail_refiner.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
except ImportError:
    torch = module = None


@unittest.skipUnless(module is not None, "ComfyUI runtime required")
class TailRefinerTests(unittest.TestCase):
    def setUp(self):
        self.video = torch.arange(107, dtype=torch.float32).reshape(1, 1, 107, 1, 1)
        self.audio = torch.arange(604, dtype=torch.float32).reshape(1, 1, 1, 604)
        self.latent = {"samples": module.comfy.nested_tensor.NestedTensor(
            (self.video, self.audio))}

    def test_refines_seven_step_tail_and_splices_only_video(self):
        seen = {}

        def fake_refine(tail, strength, frames, **kwargs):
            video, audio = tail["samples"].unbind()
            seen["shapes"] = (tuple(video.shape), tuple(audio.shape))
            seen["positive"] = kwargs["positive"][0][1]
            return {"samples": (video + 10, audio + 10)}, "sampled"

        positive = [[None, {
            "minimax_keyframes": [{"latent": "full clip"}],
            "minimax_frame_count": 362,
            "minimax_refs": [
                {"kind": "audio", "motion_context_audio_end_frame": 22},
                {"kind": "image", "latent": "character reference"},
            ],
        }]]
        with patch.object(module.H3ClipRefiner, "refine", side_effect=fake_refine):
            result, report = module.SkebaH3TailClipRefiner.refine(
                self.latent, 1.0, "22", positive=positive)
        actual_video, actual_audio = result["samples"].unbind()
        self.assertEqual(seen["shapes"], ((1, 1, 7, 1, 1), (1, 1, 1, 37)))
        self.assertNotIn("minimax_keyframes", seen["positive"])
        self.assertNotIn("minimax_frame_count", seen["positive"])
        self.assertEqual(len(seen["positive"]["minimax_refs"]), 1)
        self.assertTrue(torch.equal(actual_video[:, :, :-7], self.video[:, :, :-7]))
        self.assertTrue(torch.equal(actual_video[:, :, -7:], self.video[:, :, -7:] + 10))
        self.assertTrue(torch.equal(actual_audio, self.audio))
        self.assertTrue(torch.equal(self.video[:, :, -7:],
                                    torch.arange(100, 107).reshape(1, 1, 7, 1, 1)))
        self.assertIn("22 frames / 7 steps", report)

    def test_unmodified_tail_passes_original_latent_through(self):
        with patch.object(module.H3ClipRefiner, "refine", return_value=(
            {"samples": (self.video[:, :, -7:], self.audio[..., -37:])}, "measured")):
            result, _ = module.SkebaH3TailClipRefiner.refine(self.latent, 1, "22")
        self.assertIs(result, self.latent)

    def test_final_prompt_skips_refine_sample(self):
        with patch.object(module.H3ClipRefiner, "refine") as sample:
            result, report = module.SkebaH3TailClipRefiner.refine(
                self.latent, 1, "22", refine_if_next_prompt=False)
        self.assertIs(result, self.latent)
        self.assertIn("final prompt", report)
        sample.assert_not_called()

    def test_rejects_off_grid_video(self):
        latent = {"samples": (self.video[:, :, :-1], self.audio)}
        with self.assertRaisesRegex(ValueError, "five-step temporal grid"):
            module.SkebaH3TailClipRefiner.refine(latent, 1, "22")

    def test_sampling_receives_only_the_tail_av_window(self):
        torch.manual_seed(7)
        video = torch.randn(1, 24, 107, 8, 8)
        audio = torch.randn(1, 32, 2, 604)
        latent = {"samples": module.comfy.nested_tensor.NestedTensor((video, audio))}
        seen = {}

        def fake_sample(model, noise, steps, cfg, sampler_name, scheduler,
                        positive, negative, work, **kwargs):
            v, a = work.unbind()
            seen["video_steps"] = v.shape[2]
            seen["audio_steps"] = a.shape[-1]
            return module.comfy.nested_tensor.NestedTensor((v * 1.5, a))

        with patch.object(module.comfy.sample, "prepare_noise", return_value=None), \
             patch.object(module.comfy.sample, "sample", side_effect=fake_sample), \
             patch.object(module.comfy.model_management, "soft_empty_cache"), \
             patch.object(module, "get_original_node_id", None):
            result, report = module.SkebaH3TailClipRefiner.refine(
                latent, 1, "22", model=SimpleNamespace(load_device="cpu"),
                positive=[[None, {}]], negative=[[None, {}]],
                refine_denoise=0.15, refine_steps=3, detail_strength=1)
        result_video, result_audio = result["samples"].unbind()
        self.assertEqual(seen, {"video_steps": 7, "audio_steps": 37})
        self.assertTrue(torch.equal(result_video[:, :, :-7], video[:, :, :-7]))
        self.assertFalse(torch.equal(result_video[:, :, -7:], video[:, :, -7:]))
        self.assertTrue(torch.equal(result_audio, audio))
        self.assertIn("refine+detail", report)


if __name__ == "__main__":
    unittest.main()

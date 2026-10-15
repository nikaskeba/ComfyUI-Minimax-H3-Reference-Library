import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parents[1]))
SPEC = importlib.util.spec_from_file_location("audio_refine_test", ROOT / "h3_audio_refine.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
Nested = MODULE.comfy.nested_tensor.NestedTensor


def latent():
    return {"samples": Nested((torch.randn(1, 24, 2, 2, 2), torch.randn(1, 32, 2, 20))), "metadata": "kept"}


class AudioRefineTests(unittest.TestCase):
    def test_finish_inpaint_latent_removes_only_stale_mask(self):
        value = latent()
        mask = Nested(tuple(torch.ones_like(t) for t in value["samples"].tensors))
        value["noise_mask"] = mask
        result, status = MODULE.SkebaH3FinishInpaintLatent().finish(value)
        self.assertIs(result["samples"], value["samples"])
        self.assertEqual(result["metadata"], "kept")
        self.assertNotIn("noise_mask", result)
        self.assertIs(value["noise_mask"], mask)
        self.assertIn("removed old noise mask", status)
        self.assertNotIn("noise_mask", MODULE.SkebaH3FinishInpaintLatent().finish(latent())[0])

    def run_refine(self, value, **kwargs):
        def sample(*args, **kw):
            return Nested(tuple(t + 5 for t in args[8].tensors))
        with patch.object(MODULE.comfy.sample, "sample", side_effect=sample) as sampler, \
             patch.object(MODULE.comfy.sample, "prepare_noise", return_value=None) as noise, \
             patch.object(MODULE.latent_preview, "prepare_callback", return_value=None):
            out = MODULE.SkebaH3AudioRefine().refine(value, model=object(), positive=[], negative=[], **kwargs)[0]
        return out, sampler, noise

    def test_off_and_zero_are_exact_pass_through(self):
        for options in ({"enabled": False}, {"enabled": True, "audio_denoise": 0}):
            value = latent()
            out, sampler, noise = self.run_refine(value, **options)
            self.assertIs(out, value)
            sampler.assert_not_called()
            noise.assert_not_called()

    def test_refine_freezes_video_and_preserves_both_audio_boundaries(self):
        value = latent()
        v, a = value["samples"].tensors
        original = a.clone()
        mask = torch.ones(1, 1, 2, 20)
        mask[..., :3] = 0
        mask[..., -4:] = 0
        mask[..., 5] = 0.5
        value["noise_mask"] = Nested((torch.ones_like(v), mask))
        out, sampler, noise = self.run_refine(value, enabled=True, seed=123, steps=6)
        self.assertIs(out["samples"].tensors[0], v)
        refined = out["samples"].tensors[1]
        torch.testing.assert_close(refined[..., :3], a[..., :3], rtol=0, atol=0)
        torch.testing.assert_close(refined[..., -4:], a[..., -4:], rtol=0, atol=0)
        torch.testing.assert_close(refined[..., 3:-4], a[..., 3:-4] + 5)
        torch.testing.assert_close(a, original)
        self.assertIs(out["noise_mask"], value["noise_mask"])
        self.assertEqual(out["metadata"], "kept")
        passed = sampler.call_args.kwargs["noise_mask"]
        self.assertFalse(torch.any(passed.tensors[0]))
        self.assertEqual(passed.tensors[1][0, 0, 0, 5], 0.5)
        self.assertEqual(sampler.call_args.kwargs["seed"], 123)

    def test_external_boundary_mask_and_mask_intersection(self):
        value = latent()
        boundary = latent()
        boundary["noise_mask"] = Nested((torch.ones_like(boundary["samples"].tensors[0]), torch.ones(1, 1, 2, 20)))
        boundary["noise_mask"].tensors[1][..., -5:] = 0
        out, _, _ = self.run_refine(value, enabled=True, boundary_latent=boundary)
        torch.testing.assert_close(out["samples"].tensors[1][..., -5:], value["samples"].tensors[1][..., -5:])
        value["noise_mask"] = Nested((torch.ones_like(value["samples"].tensors[0]), torch.ones(1, 1, 2, 20)))
        value["noise_mask"].tensors[1][..., :4] = 0
        mask = MODULE.refinement_mask(value, boundary).tensors[1]
        self.assertFalse(torch.any(mask[..., :4]))
        self.assertFalse(torch.any(mask[..., -5:]))
        self.assertTrue(torch.all(mask[..., 4:-5] == 1))

    def test_all_protected_skips_sampling(self):
        value = latent()
        value["noise_mask"] = Nested(tuple(torch.zeros_like(t) for t in value["samples"].tensors))
        out, sampler, _ = self.run_refine(value, enabled=True)
        self.assertIs(out, value)
        sampler.assert_not_called()

    def test_no_boundary_refines_all_audio_without_adding_freeze_mask(self):
        value = latent()
        out, _, _ = self.run_refine(value, enabled=True)
        self.assertIs(out["samples"].tensors[0], value["samples"].tensors[0])
        torch.testing.assert_close(out["samples"].tensors[1], value["samples"].tensors[1] + 5)
        self.assertNotIn("noise_mask", out)

    def test_invalid_boundary_rejected(self):
        value = latent()
        with self.assertRaisesRegex(ValueError, "no noise mask"):
            MODULE.refinement_mask(value, latent())
        boundary = latent()
        boundary["samples"].tensors[1] = torch.zeros(1, 32, 2, 10)
        boundary["noise_mask"] = Nested((torch.ones(1), torch.ones(1, 1, 2, 10)))
        with self.assertRaisesRegex(ValueError, "length differs"):
            MODULE.refinement_mask(value, boundary)
        with self.assertRaisesRegex(ValueError, "sampled H3"):
            MODULE.refinement_mask({"samples": torch.zeros(1)})

    def test_lazy_and_missing_inputs(self):
        node = MODULE.SkebaH3AudioRefine()
        self.assertEqual(node.check_lazy_status(False, 0.3, model=None), [])
        self.assertEqual(node.check_lazy_status(True, 0.3, model=None, positive=None), ["model", "positive"])
        with self.assertRaisesRegex(ValueError, "connect model"):
            node.refine(latent(), enabled=True)

    def test_connected_noise_overrides_numeric_seed(self):
        value = latent()
        for seed in (0, 123456):
            source = Mock(seed=seed)
            source.generate_noise.return_value = object()
            _, sampler, prepare_noise = self.run_refine(value, enabled=True, seed=99, noise=source)
            source.generate_noise.assert_called_once_with(value)
            prepare_noise.assert_not_called()
            self.assertIs(sampler.call_args.args[1], source.generate_noise.return_value)
            self.assertEqual(sampler.call_args.kwargs["seed"], seed)

    def test_noise_is_lazy_and_unused_when_off(self):
        source = Mock(seed=123)
        value = latent()
        out, _, _ = self.run_refine(value, enabled=False, noise=source)
        self.assertIs(out, value)
        source.generate_noise.assert_not_called()
        node = MODULE.SkebaH3AudioRefine()
        self.assertEqual(node.check_lazy_status(False, 0.3, noise=None), [])
        self.assertEqual(node.check_lazy_status(True, 0.3, noise=None), ["noise"])
        self.assertEqual(node.INPUT_TYPES()["optional"]["noise"][0], "NOISE")

    def test_inpaint_range_reopens_locked_audio_and_keeps_rest_exact(self):
        value = latent()
        video, audio = value["samples"].tensors
        value["noise_mask"] = Nested((torch.ones_like(video), torch.zeros_like(audio)))
        out, sampler, _ = self.run_refine(value, enabled=True, edit_start_seconds=0.1,
            edit_end_seconds=0.3, replace_locked_audio=True)
        self.assertIs(out["samples"].tensors[0], video)
        refined = out["samples"].tensors[1]
        torch.testing.assert_close(refined[..., :4], audio[..., :4], rtol=0, atol=0)
        torch.testing.assert_close(refined[..., 4:12], audio[..., 4:12] + 5)
        torch.testing.assert_close(refined[..., 12:], audio[..., 12:], rtol=0, atol=0)
        passed = sampler.call_args.kwargs["noise_mask"].tensors
        self.assertFalse(torch.any(passed[0]))
        self.assertTrue(torch.all(passed[1][..., 4:12] == 1))

    def test_inpaint_range_validation_and_boundary_protection(self):
        value = latent()
        boundary = latent()
        boundary["noise_mask"] = Nested((torch.ones_like(value["samples"].tensors[0]),
                                         torch.ones_like(value["samples"].tensors[1])))
        boundary["noise_mask"].tensors[1][..., 8:10] = 0
        mask = MODULE.refinement_mask(value, boundary, edit_start_seconds=0.1,
            edit_end_seconds=0.3, replace_locked_audio=True).tensors[1]
        self.assertFalse(torch.any(mask[..., :4]))
        self.assertFalse(torch.any(mask[..., 8:10]))
        self.assertFalse(torch.any(mask[..., 12:]))
        for start, end in ((0.2, 0.2), (-1, 0.2), (0, 0.6), (0.101, 0.102)):
            with self.assertRaisesRegex(ValueError, "Audio Inpaint"):
                MODULE.refinement_mask(value, edit_start_seconds=start, edit_end_seconds=end)
        self.assertEqual(MODULE.SkebaH3AudioInpaintRange.INPUT_TYPES()["required"]["replace_locked_audio"][1]["default"], True)

    def test_pre_sampler_audio_edit_mask_keeps_video_mask_and_locks_outside(self):
        value = latent()
        video, audio = value["samples"].tensors
        original_video_mask = torch.ones((1, 1, *video.shape[2:]))
        value["noise_mask"] = Nested((original_video_mask, torch.zeros((1, 1, 2, 20))))
        out, status = MODULE.SkebaH3AudioEditMask().apply(value, True, 0.1, 0.3, 0.5)
        self.assertIs(out["samples"], value["samples"])
        self.assertIs(out["noise_mask"].tensors[0], original_video_mask)
        mask = out["noise_mask"].tensors[1]
        self.assertEqual(tuple(mask.shape), (1, 1, 2, 20))
        self.assertFalse(torch.any(mask[..., :4]))
        self.assertTrue(torch.all(mask[..., 4:12] == 0.5))
        self.assertFalse(torch.any(mask[..., 12:]))
        self.assertFalse(torch.any(value["noise_mask"].tensors[1]))
        self.assertIn('"audio_mask_strength": 0.5', status)
        self.assertIs(MODULE.SkebaH3AudioEditMask().apply(value, False)[0], value)

    def test_pre_sampler_audio_edit_mask_rejects_invalid_ranges(self):
        node = MODULE.SkebaH3AudioEditMask()
        for start, end, strength in ((0.2, 0.2, 0.5), (-1, 0.2, 0.5),
                                     (0, 0.6, 0.5), (0.101, 0.102, 0.5),
                                     (0, 0.2, 1.1)):
            with self.assertRaisesRegex(ValueError, "Audio Edit Mask"):
                node.apply(latent(), True, start, end, strength)

    def test_pre_sampler_video_edit_mask_preserves_audio_and_audio_edit_preserves_video(self):
        video = torch.randn(1, 24, 65, 2, 2)
        audio = torch.randn(1, 32, 2, 440)
        value = {"samples": Nested((video, audio))}
        original_audio_mask = torch.zeros(1, 1, 2, 440)
        original_audio_mask[..., 20:30] = 0.75
        value["noise_mask"] = Nested((torch.ones(1, 1, 65, 2, 2), original_audio_mask))
        video_out, status = MODULE.SkebaH3VideoEditMask().apply(value, True, 3, 10, 0.25)
        self.assertIs(video_out["samples"], value["samples"])
        self.assertIs(video_out["noise_mask"].tensors[1], original_audio_mask)
        video_mask = video_out["noise_mask"].tensors[0]
        self.assertFalse(torch.any(video_mask[:, :, :18]))
        self.assertTrue(torch.all(video_mask[:, :, 18:61] == 0.25))
        self.assertFalse(torch.any(video_mask[:, :, 61:]))
        self.assertIn('"audio_mask": "preserved"', status)
        both, _ = MODULE.SkebaH3AudioEditMask().apply(video_out, True, 3, 10, 1)
        self.assertIs(both["noise_mask"].tensors[0], video_mask)
        self.assertFalse(torch.any(both["noise_mask"].tensors[1][..., :120]))
        self.assertTrue(torch.all(both["noise_mask"].tensors[1][..., 120:400] == 1))
        self.assertFalse(torch.any(both["noise_mask"].tensors[1][..., 400:]))
        self.assertIs(value["noise_mask"].tensors[1], original_audio_mask)
        self.assertIs(MODULE.SkebaH3VideoEditMask().apply(value, False)[0], value)
        locked, _ = MODULE.SkebaH3VideoEditMask().apply(value, True, 3, 10, 0)
        self.assertFalse(torch.any(locked["noise_mask"].tensors[0]))
        self.assertIs(locked["noise_mask"].tensors[1], original_audio_mask)

    def test_pre_sampler_video_edit_mask_rejects_invalid_ranges(self):
        node = MODULE.SkebaH3VideoEditMask()
        for start, end, strength in ((0.2, 0.2, 0.25), (-1, 0.2, 0.25),
                                     (0, 1, 0.25), (0, 0.2, 1.1)):
            with self.assertRaisesRegex(ValueError, "Video Edit Mask"):
                node.apply(latent(), True, start, end, strength)

    def test_video_edit_can_include_h3_tail_after_nominal_ten_seconds(self):
        video = torch.randn(1, 24, 62, 2, 2)  # 245-frame latent envelope
        audio = torch.randn(1, 32, 2, 440)
        value = {"samples": Nested((video, audio))}
        node = MODULE.SkebaH3VideoEditMask()
        ordinary, _ = node.apply(value, True, 2, 10, 0.25)
        through_end, status = node.apply(value, True, 2, 10, 0.25, True)
        self.assertEqual(ordinary["noise_mask"].tensors[0][0, 0, -1, 0, 0], 0)
        self.assertEqual(through_end["noise_mask"].tensors[0][0, 0, -1, 0, 0], 0.25)
        self.assertIn('"extend_to_last_frame": true', status)
        self.assertIn('"masked_video_tokens": [', status)
        self.assertIn('"video_token_count": 62', status)
        self.assertEqual(tuple(through_end["noise_mask"].tensors[0].shape), (1, 1, 62, 2, 2))

    def test_video_latent_anchor_blend_preserves_base_and_learned_inputs(self):
        base = {"samples": torch.full((1, 24, 3, 2, 2), 2.0)}
        learned = {"samples": torch.full((1, 24, 3, 4, 4), 10.0)}
        out, status = MODULE.SkebaH3VideoLatentAnchorBlend().blend(learned, base, 0.3)
        self.assertEqual(tuple(out["samples"].shape), (1, 24, 3, 4, 4))
        torch.testing.assert_close(out["samples"], torch.full_like(out["samples"], 7.6))
        torch.testing.assert_close(base["samples"], torch.full_like(base["samples"], 2.0))
        torch.testing.assert_close(learned["samples"], torch.full_like(learned["samples"], 10.0))
        self.assertIn('"audio": "not processed"', status)
        self.assertIs(MODULE.SkebaH3VideoLatentAnchorBlend().blend(learned, base, 0)[0], learned)
        with self.assertRaisesRegex(ValueError, "matching H3 video latents"):
            MODULE.SkebaH3VideoLatentAnchorBlend().blend(learned, {"samples": torch.zeros(1, 24, 4, 2, 2)}, 0.3)

    def test_av_inpaint_uses_independent_ranges_and_preserves_other_latents(self):
        video = torch.randn(1, 24, 65, 2, 2)  # 257 decoded frames
        audio = torch.randn(1, 32, 2, 400)    # 10 seconds
        value = {"samples": Nested((video, audio)), "metadata": "kept"}

        def sample(*args, **kwargs):
            return Nested(tuple(t + 5 for t in args[8].tensors))

        with patch.object(MODULE.comfy.sample, "sample", side_effect=sample) as sampler, \
             patch.object(MODULE.comfy.sample, "prepare_noise", return_value=None), \
             patch.object(MODULE.latent_preview, "prepare_callback", return_value=None):
            out, status = MODULE.SkebaH3AVInpaintRange().inpaint(
                value, model=object(), positive=[], negative=[],
                video_start_seconds=4, video_end_seconds=8, video_mask_strength=0.25,
                audio_start_seconds=3, audio_end_seconds=7, audio_mask_strength=1.0)
        passed_v, passed_a = sampler.call_args.kwargs["noise_mask"].tensors
        self.assertTrue(torch.all(passed_v[:, :, 24:49] == 0.25))
        self.assertFalse(torch.any(passed_v[:, :, :24]))
        self.assertFalse(torch.any(passed_v[:, :, 49:]))
        self.assertTrue(torch.all(passed_a[..., 120:280] == 1))
        self.assertFalse(torch.any(passed_a[..., :120]))
        self.assertFalse(torch.any(passed_a[..., 280:]))
        out_v, out_a = out["samples"].tensors
        torch.testing.assert_close(out_v[:, :, :24], video[:, :, :24], rtol=0, atol=0)
        torch.testing.assert_close(out_v[:, :, 49:], video[:, :, 49:], rtol=0, atol=0)
        torch.testing.assert_close(out_a[..., :120], audio[..., :120], rtol=0, atol=0)
        torch.testing.assert_close(out_a[..., 280:], audio[..., 280:], rtol=0, atol=0)
        self.assertEqual(out["metadata"], "kept")
        self.assertIn('"video_mask_strength": 0.25', status)
        self.assertIn('"audio_mask_strength": 1.0', status)

    def test_av_inpaint_off_and_invalid_ranges(self):
        value = latent()
        node = MODULE.SkebaH3AVInpaintRange()
        self.assertIs(node.inpaint(value, enabled=False)[0], value)
        self.assertIs(node.inpaint(value, sampling_denoise=0)[0], value)
        self.assertNotIn("boundary_latent", node.INPUT_TYPES()["optional"])
        for overrides in ({"video_start_seconds": 0.2, "video_end_seconds": 0.1},
                          {"audio_start_seconds": 0.1, "audio_end_seconds": 1.0},
                          {"video_mask_strength": 1.1}):
            options = dict(video_start_seconds=0, video_end_seconds=0.1,
                           audio_start_seconds=0, audio_end_seconds=0.2)
            options.update(overrides)
            with self.assertRaisesRegex(ValueError, "SKEBA AV Inpaint"):
                node.inpaint(value, model=object(), positive=[], negative=[], **options)


if __name__ == "__main__":
    unittest.main()

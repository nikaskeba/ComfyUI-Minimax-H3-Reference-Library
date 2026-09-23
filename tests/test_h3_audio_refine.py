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


if __name__ == "__main__":
    unittest.main()

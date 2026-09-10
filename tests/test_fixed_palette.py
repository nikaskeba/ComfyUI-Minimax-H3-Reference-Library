import importlib.util
from pathlib import Path
import unittest
from unittest import mock

import torch

spec = importlib.util.spec_from_file_location("fixed_palette", Path(__file__).parents[1] / "fixed_palette.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PaletteTests(unittest.TestCase):
    def test_nearest_and_palette_format(self):
        image = torch.tensor([[[[0.1]*3, [0.9]*3, [0.5]*3]]])
        result, palette = module.FixedPaletteQuantize().quantize(image, 2, color_1="000000", color_2="#ffffff")
        self.assertEqual(palette, "#000000,#FFFFFF")
        self.assertTrue(torch.equal(result, torch.tensor([[[[0.]*3, [1.]*3, [0.]*3]]])))

    def test_chunks_batch_alpha_noncontiguous(self):
        image = torch.rand(3, 19, 13, 4).transpose(1, 2)
        before = image.clone()
        with mock.patch.object(module, "CHUNK_PIXELS", 7):
            output, _ = module.FixedPaletteQuantize().quantize(image)
        palette = torch.tensor([[0., 1., 0.], [0., 0., 0.], [1., 1., 1.]])
        expected = palette[(image[..., None, :3] - palette).square().sum(-1).argmin(-1)]
        self.assertTrue(torch.equal(output[..., :3], expected))
        self.assertTrue(torch.equal(output[..., 3], image[..., 3]))
        self.assertTrue(torch.equal(image, before))

    def test_hex_errors_duplicates_and_unused(self):
        for value in ("green", "#GGFF00", "123"):
            with self.assertRaisesRegex(ValueError, "Expected #RRGGBB"):
                module.parse_color(value)
        output, palette = module.FixedPaletteQuantize().quantize(torch.rand(1, 2, 2, 3), 2,
            color_1="#0066FF", color_2="0066ff", color_3="unused")
        self.assertEqual(palette, "#0066FF,#0066FF")
        self.assertTrue(torch.equal(output, torch.tensor([0., 102/255, 1.]).expand_as(output)))

    @unittest.skipUnless(torch.cuda.is_available(), "CUDA unavailable")
    def test_1080p_batch_cuda_memory_and_membership(self):
        image = torch.rand(2, 1080, 1920, 3, device="cuda")
        torch.cuda.reset_peak_memory_stats()
        baseline = torch.cuda.memory_allocated()
        output, _ = module.FixedPaletteQuantize().quantize(image)
        torch.cuda.synchronize()
        extra = torch.cuda.max_memory_allocated() - baseline
        self.assertLess(extra, 160 * 1024**2)
        self.assertEqual(output.device, image.device)
        for frame in output:
            unique = torch.unique(frame.reshape(-1, 3), dim=0)
            palette = torch.tensor([[0.,1.,0.],[0.,0.,0.],[1.,1.,1.]], device="cuda")
            self.assertTrue(((unique[:,None] == palette).all(-1).any(-1)).all().item())
        print(f"1080p x2 CUDA peak additional allocation: {extra / 1024**2:.1f} MiB")


if __name__ == "__main__":
    unittest.main()

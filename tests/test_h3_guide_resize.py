import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import torch


ROOT = Path(__file__).resolve().parents[1]
COMFY_ROOT = ROOT.parents[1]
if str(COMFY_ROOT) not in sys.path:
    sys.path.insert(0, str(COMFY_ROOT))
SPEC = importlib.util.spec_from_file_location(
    "h3_guide_resize_test", ROOT / "h3_guide_resize.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class H3GuideResizeTests(unittest.TestCase):
    @staticmethod
    def latent(height, width):
        nested = SimpleNamespace(
            is_nested=True,
            tensors=[
                torch.zeros((1, 24, 2, height, width)),
                torch.zeros((1, 32, 2, 4)),
            ],
        )
        return {"samples": nested}

    def test_resizes_to_exact_h3_canvas(self):
        image = torch.zeros((1, 12, 20, 3))
        result, = MODULE.SkebaH3GuideResizeToLatent().resize(
            image, self.latent(4, 6), "center crop"
        )
        self.assertEqual(tuple(result.shape), (1, 64, 96, 3))

    def test_edge_pad_carries_normalized_composition_to_upscaled_canvas(self):
        image = torch.zeros((1, 64, 96, 3))
        result, = MODULE.SkebaH3GuideResizeToLatent().resize(
            image, self.latent(6, 10), "edge pad"
        )
        self.assertEqual(tuple(result.shape), (1, 96, 160, 3))

    def test_rejects_non_h3_latent(self):
        with self.assertRaisesRegex(ValueError, "MiniMax H3 AV latent"):
            MODULE.SkebaH3GuideResizeToLatent().resize(
                torch.zeros((1, 8, 8, 3)), {"samples": torch.zeros(1)}
            )


if __name__ == "__main__":
    unittest.main()

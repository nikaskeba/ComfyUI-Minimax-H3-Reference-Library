import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
COMFY_ROOT = ROOT.parents[1]
if str(COMFY_ROOT) not in sys.path:
    sys.path.insert(0, str(COMFY_ROOT))

SPEC = importlib.util.spec_from_file_location(
    "h3_guide_bypass_test", ROOT / "h3_guide_bypass.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class H3GuideBypassTests(unittest.TestCase):
    def test_bypass_returns_conditioning_without_requesting_lazy_inputs(self):
        conditioning = [[object(), {}]]
        self.assertEqual(
            MODULE.SkebaMiniMaxH3AddGuideBypass.check_lazy_status(
                conditioning, 22, True, latent=None, image=None, vae=None
            ),
            [],
        )
        result = MODULE.SkebaMiniMaxH3AddGuideBypass.execute(
            conditioning, 22, True
        )
        self.assertIs(result[0], conditioning)

    def test_active_image_guide_requests_only_needed_inputs(self):
        conditioning = [[object(), {}]]
        needed = MODULE.SkebaMiniMaxH3AddGuideBypass.check_lazy_status(
            conditioning, 22, False, latent=None, image=None, vae=None
        )
        self.assertEqual(needed, ["latent", "image", "vae"])

    def test_active_mode_delegates_to_native_guide(self):
        expected = object()
        with mock.patch.object(
            MODULE.MiniMaxH3AddGuide, "execute", return_value=expected
        ) as execute:
            result = MODULE.SkebaMiniMaxH3AddGuideBypass.execute(
                "conditioning", 22, False,
                latent="latent", vae="vae", image="image"
            )
        self.assertIs(result, expected)
        execute.assert_called_once_with(
            positive="conditioning", latent="latent", frame_idx=22,
            vae="vae", audio_vae=None, image="image", audio=None,
        )


if __name__ == "__main__":
    unittest.main()

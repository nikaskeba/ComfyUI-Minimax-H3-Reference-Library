import importlib.util
from pathlib import Path
import unittest
import torch

spec = importlib.util.spec_from_file_location("reference_audio_preview", Path(__file__).parents[1] / "reference_audio_preview.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AudioPreviewTests(unittest.TestCase):
    def test_mixed_refs_select_native_third_audio_and_preserve_source(self):
        class VAE:
            audio_sample_rate_output = 32000
            def decode(self, latent):
                self.selected = latent.clone()
                latent.zero_()  # Even an in-place decoder must not damage conditioning.
                return torch.ones(1, 320, 2)
        vae = VAE()
        refs = [{"kind": "image"}, {"kind": "video", "ref_audio_t": 0}]
        for value in (1, 2, 3):
            refs.append({"kind": "audio", "ref_audio_t": 200, "audio_latent": torch.full((1, 32, 2, 200), float(value))})
        cond = [[None, {"minimax_refs": refs}]]
        audio, details = module.SkebaH3ReferenceAudioPreview().decode(cond, vae, 3)
        self.assertEqual(vae.selected.mean(), 3)
        self.assertEqual(refs[-1]["audio_latent"].mean(), 3)
        self.assertEqual(audio["waveform"].shape, (1, 2, 320))
        self.assertEqual(audio["sample_rate"], 32000)
        self.assertIn("block 4", details)
        with self.assertRaisesRegex(ValueError, "contains 3"):
            module.SkebaH3ReferenceAudioPreview().decode(cond, vae, 4)

    def test_missing_conditioning_and_references_have_actionable_errors(self):
        node = module.SkebaH3ReferenceAudioPreview()
        with self.assertRaisesRegex(ValueError, "Connect SKEBA Apply"):
            node.decode(None, None)
        with self.assertRaisesRegex(ValueError, "contains 0"):
            node.decode([[None, {}]], None)


if __name__ == "__main__":
    unittest.main()

import importlib
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import torch
import test_refmod_studio as fixtures

module = importlib.import_module(fixtures.PACKAGE + ".voice_description_refmod")


class RefModDescriptionTests(unittest.TestCase):
    def test_source_sections_order_and_cap(self):
        calls = []
        def source(item):
            calls.append(item)
            return "audio", {"waveform": torch.ones(1, 1, 32000 * 4), "sample_rate": 32000}
        settings = {"keep_voice": False, "audio_seconds": 7, "sources": [
            {"file": "movie", "kind": "video", "include_audio": False},
            {"file": "voice", "kind": "audio", "start": 1},
            {"file": "movie", "kind": "video", "include_audio": True, "sections": [{"start": 2, "end": 6}, {"start": 8, "end": 10}]}]}
        with patch.object(module, "_trimmed_source", side_effect=source), patch.object(module, "describe_audio", side_effect=lambda audio: audio):
            result = module.describe_refmod(settings)
        self.assertEqual([c["start"] for c in calls], [1, 2])
        self.assertTrue(all(c["soundtrack_only"] for c in calls))
        self.assertEqual(result["waveform"].shape, (1, 2, 7 * 32000))

    def test_stored_decode_and_no_mutation(self):
        latent = torch.ones(1, 32, 2, 800)
        mod = SimpleNamespace(kind="audio", latent=latent)
        vae = SimpleNamespace(audio_sample_rate_output=32000, decode=lambda z: torch.ones(1, 32000 * 20, 2))
        with patch.object(module, "members_from_file", return_value=(None, {"kind": "bundle"}, [mod])), patch.object(module, "describe_audio", side_effect=lambda x: {"description": "warm", "seconds": x["waveform"].shape[-1] / x["sample_rate"]}):
            with self.assertRaisesRegex(ValueError, "audio VAE"):
                module.describe_refmod({"existing": {"file": "a"}})
            result = module.SkebaRefModVoiceDescription().describe(json.dumps({"existing": {"file": "a"}}), vae)
            self.assertEqual(result["ui"]["voice_description"][0]["seconds"], 15)
            self.assertEqual(result["result"], ("warm",))
        self.assertEqual(latent.shape[-1], 800)
        self.assertTrue(torch.all(latent == 1))

    def test_removed_voice_does_not_decode(self):
        with patch.object(module, "members_from_file") as read:
            with self.assertRaisesRegex(ValueError, "Upload voice"):
                module.describe_refmod({"existing": {"file": "a"}, "keep_voice": False})
            read.assert_not_called()


if __name__ == "__main__":
    unittest.main()

import importlib.util
import json
from pathlib import Path
import unittest

import torch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("h3_audio_level_test", ROOT / "h3_audio_level.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AudioLevelTests(unittest.TestCase):
    def test_quiet_and_loud_speech_move_toward_each_other(self):
        rate = 16000
        t = torch.arange(rate, dtype=torch.float32) / rate
        tone = torch.sin(2 * torch.pi * 1000 * t)
        waveform = torch.cat([tone * 0.03, tone * 0.35])[None, None]
        source = {"waveform": waveform.clone(), "sample_rate": rate}
        output = MODULE.normalize_audio(source, low_cut_hz=0, presence_db=0)["waveform"]
        before_ratio = waveform[..., rate + 4000:rate + 12000].square().mean().sqrt() / waveform[..., 4000:12000].square().mean().sqrt()
        after_ratio = output[..., rate + 4000:rate + 12000].square().mean().sqrt() / output[..., 4000:12000].square().mean().sqrt()
        self.assertLess(float(after_ratio), float(before_ratio))
        self.assertTrue(torch.equal(source["waveform"], waveform))
        self.assertLessEqual(float(output.abs().max()), 10 ** (-1 / 20) + 1e-5)

    def test_silence_and_stereo_balance(self):
        rate = 8000
        tone = torch.sin(2 * torch.pi * 1000 * torch.arange(rate) / rate) * 0.05
        source = {"waveform": torch.stack([tone, tone * 0.5], dim=0)[None], "sample_rate": rate}
        result = MODULE.normalize_audio(source, low_cut_hz=0, presence_db=0)["waveform"]
        self.assertTrue(torch.allclose(result[:, 1], result[:, 0] * 0.5, atol=1e-6))
        silence = {"waveform": torch.zeros(1, 2, rate), "sample_rate": rate}
        self.assertEqual(float(MODULE.normalize_audio(silence)["waveform"].abs().max()), 0)

    def test_bypass_returns_original_audio(self):
        audio = {"waveform": torch.ones(1, 1, 16), "sample_rate": 16000}
        output, status = MODULE.SkebaH3AudioLevel().process(audio, enabled=False)
        self.assertIs(output, audio)
        self.assertIn("bypassed", status)

    def test_oct24_workflow_feeds_both_audio_consumers(self):
        workflow = json.loads((ROOT / "example/MainWorkflow-Oct24.json").read_text(encoding="utf-8"))
        nodes = {node["id"]: node for node in workflow["nodes"]}
        links = {link[0]: link for link in workflow["links"]}
        level = next(node for node in nodes.values() if node["type"] == "SkebaH3AudioLevel")
        self.assertEqual(links[level["inputs"][0]["link"]][1:5], [323, 0, level["id"], 0])
        self.assertEqual(links[2022][1:5], [level["id"], 0, 930, 1])
        self.assertEqual(links[2242][1:5], [level["id"], 0, 1221, 3])


if __name__ == "__main__":
    unittest.main()

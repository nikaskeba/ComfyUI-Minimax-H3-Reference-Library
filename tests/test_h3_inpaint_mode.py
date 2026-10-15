import importlib.util
import json
from pathlib import Path
import sys
import unittest

import torch


ROOT = Path(__file__).resolve().parents[1]
COMFY = ROOT.parents[1]
if str(COMFY) not in sys.path:
    sys.path.insert(0, str(COMFY))
SPEC = importlib.util.spec_from_file_location("h3_inpaint_mode_test", ROOT / "h3_inpaint_mode.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class InpaintModeTests(unittest.TestCase):
    def test_audio_driven_video_uses_blank_video_and_selected_audio(self):
        source = {"samples": torch.ones((1, 32, 2, 37))}
        node = MODULE.SkebaH3InpaintLatentMode()
        self.assertEqual(node.check_lazy_status("audio drives video"), ["source_audio_latent"])
        output, _ = node.select("audio drives video", "preserve source audio",
                                64, 48, 22, source_audio_latent=source)
        video, audio = output["samples"].unbind()
        video_mask, audio_mask = output["noise_mask"].unbind()
        self.assertEqual(tuple(video.shape), (1, 24, 7, 3, 4))
        self.assertEqual(float(video.abs().max()), 0)
        self.assertTrue(torch.equal(audio, source["samples"]))
        self.assertEqual(float(video_mask.min()), 1)
        self.assertEqual(float(audio_mask.max()), 0)
        generated, _ = node.select("audio drives video", "generate audio", 64, 48, 22,
                                   source_audio_latent=source)
        self.assertEqual(float(generated["noise_mask"].unbind()[1].min()), 1)

    def test_source_mode_passes_through_and_video_switch_is_lazy(self):
        source = {"samples": "existing"}
        node = MODULE.SkebaH3InpaintLatentMode()
        self.assertEqual(node.check_lazy_status("source video inpaint"), ["inpaint_latent"])
        self.assertIs(node.select("source video inpaint", "preserve source audio",
                                  64, 48, 22, inpaint_latent=source)[0], source)
        switch = MODULE.SkebaH3InpaintVideoMode()
        self.assertEqual(switch.check_lazy_status("audio drives video"), ["generated_video"])
        generated = torch.ones((22, 3, 4, 3))
        self.assertIs(switch.select("audio drives video", generated_video=generated)[0], generated)

    def test_oct15_workflow_skips_mask_branch_in_audio_mode(self):
        graph = json.loads((ROOT / "example/Minimax_Upscale_Loop_Workflow-Oct_15Inpainting .json")
                           .read_text(encoding="utf-8"))
        nodes = {node["id"]: node for node in graph["nodes"]}
        links = {link[0]: link for link in graph["links"]}
        self.assertEqual(nodes[1324]["widgets_values_named"]["video_generation_mode"],
                         "source video inpaint")
        self.assertEqual(links[nodes[300]["inputs"][4]["link"]][1], 1358)
        self.assertEqual(links[nodes[265]["inputs"][0]["link"]][1], 1359)
        self.assertEqual(links[nodes[1166]["inputs"][0]["link"]][1], 1359)
        self.assertNotIn(1168, nodes)
        self.assertNotIn(1349, nodes)
        self.assertNotIn(1350, nodes)
        self.assertNotIn(1313, nodes)
        self.assertNotIn(1314, nodes)
        self.assertEqual(links[nodes[1164]["inputs"][1]["link"]][1], 1312)
        for lid, origin, slot, target, target_slot, _ in graph["links"]:
            self.assertIn(lid, nodes[origin]["outputs"][slot]["links"])
            self.assertEqual(nodes[target]["inputs"][target_slot]["link"], lid)


if __name__ == "__main__":
    unittest.main()

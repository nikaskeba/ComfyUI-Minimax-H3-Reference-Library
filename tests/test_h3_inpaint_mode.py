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
    def test_four_video_modes_route_latents_videos_and_models(self):
        latent_node = MODULE.SkebaH3InpaintLatentMode()
        video_node = MODULE.SkebaH3InpaintVideoMode()
        model_node = MODULE.SkebaH3InpaintModelMode()
        source_latent = {"samples": "source"}
        audio_latent = {"samples": torch.ones((1, 32, 2, 37))}
        source_video, generated_video = object(), object()
        base_model, control_model = object(), object()
        for mode in ("audio drives video", "controlnet only", "inpaint only",
                     "controlnet and inpainting", "source video inpaint"):
            inpaint = mode in MODULE.INPAINT_MODES
            control = mode in MODULE.CONTROLNET_MODES
            self.assertEqual(latent_node.check_lazy_status(mode),
                             ["inpaint_latent"] if inpaint else ["source_audio_latent"])
            self.assertEqual(video_node.check_lazy_status(mode),
                             ["inpaint_video"] if inpaint else ["generated_video"])
            self.assertEqual(model_node.check_lazy_status(mode),
                             ["controlnet_model"] if control else ["base_model"])
            latent = latent_node.select(mode, "preserve source audio", 64, 48, 22,
                                        inpaint_latent=source_latent,
                                        source_audio_latent=audio_latent)[0]
            self.assertIs(latent, source_latent) if inpaint else self.assertIsNot(latent, source_latent)
            video = video_node.select(mode, inpaint_video=source_video,
                                      generated_video=generated_video)[0]
            self.assertIs(video, source_video if inpaint else generated_video)
            model = model_node.select(mode, base_model=base_model,
                                      controlnet_model=control_model)[0]
            self.assertIs(model, control_model if control else base_model)

    def test_oct26_workflow_switches_controlnet_before_both_passes(self):
        graph = json.loads((ROOT / "example/inpaint_oct26.json").read_text(encoding="utf-8"))
        nodes = {node["id"]: node for node in graph["nodes"]}
        links = {link[0]: link for link in graph["links"]}
        self.assertEqual(nodes[4584]["type"], "SkebaH3InpaintModelMode")
        self.assertEqual(links[13711][1:5], [1324, 5, 4584, 0])
        self.assertEqual(links[13712][1:5], [272, 0, 4584, 1])
        self.assertEqual(links[13706][1:5], [4578, 0, 4584, 2])
        self.assertEqual(links[13713][1:5], [4584, 0, 356, 0])
        self.assertEqual(nodes[358]["outputs"][0]["links"], [link[0] for link in graph["links"]
                         if link[1] == 358 and link[2] == 0])

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

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AudioInpaintWorkflowTests(unittest.TestCase):
    def test_oct15_upscale_receives_finished_base_latent(self):
        graph = json.loads((ROOT / "example/video_audio_reference_mix_loop_oct15.json")
                           .read_text(encoding="utf-8"))
        nodes = {node["id"]: node for node in graph["nodes"]}
        links = {link[0]: link for link in graph["links"]}
        finish = next(node for node in nodes.values()
                      if node["type"] == "SkebaH3FinishInpaintLatent")
        self.assertEqual(links[finish["inputs"][0]["link"]][1:3], [300, 1])
        self.assertEqual(links[nodes[505]["inputs"][3]["link"]][1:3],
                         [finish["id"], 0])
        self.assertEqual(links[nodes[527]["inputs"][2]["link"]][1], 526)
        for lid, source, source_slot, target, target_slot, _ in graph["links"]:
            self.assertIn(lid, nodes[source]["outputs"][source_slot]["links"])
            self.assertEqual(nodes[target]["inputs"][target_slot]["link"], lid)

    def test_dasiwa_workflow_finishes_inpaint_and_avoids_second_sampler(self):
        original = json.loads((ROOT / "example/video_audio_inpaint_alt_upscaler.json").read_text(encoding="utf-8"))
        graph = json.loads((ROOT / "example/video_audio_inpaint_alt_upscaler_fixed.json").read_text(encoding="utf-8"))
        nodes = {node["id"]: node for node in graph["nodes"]}
        links = {link[0]: link for link in graph["links"]}
        self.assertEqual(nodes[497]["type"], "SkebaH3FinishInpaintLatent")
        self.assertEqual(links[950][1:5], [300, 1, 497, 0])
        self.assertEqual(links[956][1:5], [497, 0, 492, 2])
        self.assertEqual(links[830][1:5], [492, 0, 423, 0])
        self.assertEqual(links[957][1:5], [492, 1, 498, 0])
        self.assertEqual(nodes[501]["type"], "SkebaH3UpscaleContextGuides")
        self.assertEqual(nodes[501]["widgets_values_named"]["mode"], "Off")
        self.assertEqual(links[961][1:5], [493, 0, 501, 0])
        self.assertEqual(links[962][1:5], [497, 0, 501, 1])
        self.assertEqual(links[963][1:5], [500, 0, 501, 2])
        self.assertEqual(links[964][1:5], [495, 0, 501, 3])
        self.assertEqual(links[965][1:5], [501, 0, 492, 1])
        self.assertEqual(links[958][1:5], [497, 0, 499, 0])
        self.assertEqual(links[959][1:5], [499, 0, 500, 0])
        self.assertIsNone(nodes[358]["outputs"][0]["links"])
        self.assertEqual(nodes[492]["widgets_values_named"]["denoise"], 0.2)
        self.assertEqual(nodes[492]["widgets_values_named"]["steps"], 4)
        original_links = {link[0]: link for link in original["links"]}
        for link_id in original_links.keys() - {830, 950, 951}:
            self.assertEqual(links[link_id], original_links[link_id])
        for link in links.values():
            link_id, src, src_slot, dst, dst_slot, _ = link
            self.assertIn(link_id, nodes[src]["outputs"][src_slot]["links"])
            self.assertEqual(nodes[dst]["inputs"][dst_slot]["link"], link_id)

    def test_anchor_blend_uses_completed_video_and_keeps_audio_separate(self):
        graph = json.loads((ROOT / "example/alternative_video_audio_inpaint_v5_anchor_blend.json").read_text(encoding="utf-8"))
        nodes = {node["id"]: node for node in graph["nodes"]}
        links = {link[0]: link for link in graph["links"]}
        self.assertEqual(nodes[485]["type"], "SkebaH3VideoLatentAnchorBlend")
        self.assertEqual(nodes[485]["widgets_values_named"]["anchor_strength"], 0.3)
        self.assertEqual(links[733][1:5], [353, 0, 485, 0])
        self.assertEqual(links[938][1:5], [352, 0, 485, 1])
        self.assertEqual(links[939][1:5], [485, 0, 354, 0])
        self.assertEqual(links[732][1:5], [352, 1, 354, 1])
        self.assertEqual(nodes[483]["widgets_values_named"]["video_mask_strength"], 0.12)
        self.assertEqual(nodes[474]["widgets_values_named"]["audio_mask_strength"], 0)
        for link in links.values():
            link_id, src, src_slot, dst, dst_slot, _ = link
            self.assertIn(link_id, nodes[src]["outputs"][src_slot]["links"])
            self.assertEqual(nodes[dst]["inputs"][dst_slot]["link"], link_id)

    def test_conservative_v5_gentle_refinement_variants_preserve_audio(self):
        for filename, expected_slot in (
            ("alternative_video_audio_inpaint_v5_gentle_refine.json", 0),
            ("alternative_video_audio_inpaint_v5_x0_gentle_refine.json", 1),
        ):
            graph = json.loads((ROOT / "example" / filename).read_text(encoding="utf-8"))
            nodes = {node["id"]: node for node in graph["nodes"]}
            links = {link[0]: link for link in graph["links"]}
            self.assertEqual(links[730][1:5], [300, expected_slot, 352, 0])
            self.assertEqual(links[734][1:5], [354, 0, 483, 0])
            self.assertEqual(links[936][1:5], [483, 0, 474, 0])
            self.assertEqual(nodes[353]["widgets_values_named"]["model_name"],
                             "minimax_h3_bf16_CONSERVATIVE_v5.safetensors")
            self.assertEqual(nodes[483]["widgets_values_named"]["video_mask_strength"], 0.12)
            self.assertTrue(nodes[483]["widgets_values_named"]["extend_to_last_frame"])
            self.assertEqual(nodes[474]["widgets_values_named"]["audio_mask_strength"], 0)
            for link in links.values():
                link_id, src, src_slot, dst, dst_slot, _ = link
                self.assertIn(link_id, nodes[src]["outputs"][src_slot]["links"])
                self.assertEqual(nodes[dst]["inputs"][dst_slot]["link"], link_id)

    def test_video_upscale_comparisons_keep_audio_and_mask_routing(self):
        base = json.loads((ROOT / "example/alternative_video_audio_inpaint_wired.json").read_text(encoding="utf-8"))
        sampled = json.loads((ROOT / "example/alternative_video_audio_inpaint_sampled_handoff.json").read_text(encoding="utf-8"))
        conservative = json.loads((ROOT / "example/alternative_video_audio_inpaint_conservative_upscale.json").read_text(encoding="utf-8"))
        conservative_v5 = json.loads((ROOT / "example/alternative_video_audio_inpaint_conservative_v5.json").read_text(encoding="utf-8"))
        for graph in (sampled, conservative, conservative_v5):
            nodes = {node["id"]: node for node in graph["nodes"]}
            links = {link[0]: link for link in graph["links"]}
            self.assertEqual(links[730][1:5], [300, 0, 352, 0])
            self.assertEqual(links[734][1:5], [354, 0, 483, 0])
            self.assertEqual(links[936][1:5], [483, 0, 474, 0])
            self.assertEqual(links[937][1:5], [482, 1, 484, 0])
            self.assertEqual(nodes[483]["widgets_values_named"]["video_mask_strength"], 0)
            self.assertTrue(nodes[482]["widgets_values_named"]["extend_to_last_frame"])
            self.assertEqual(nodes[474]["widgets_values_named"]["audio_mask_strength"], 0)
            for link in links.values():
                link_id, src, src_slot, dst, dst_slot, _ = link
                self.assertIn(link_id, nodes[src]["outputs"][src_slot]["links"])
                self.assertEqual(nodes[dst]["inputs"][dst_slot]["link"], link_id)
        base_nodes = {node["id"]: node for node in base["nodes"]}
        sampled_nodes = {node["id"]: node for node in sampled["nodes"]}
        conservative_nodes = {node["id"]: node for node in conservative["nodes"]}
        conservative_v5_nodes = {node["id"]: node for node in conservative_v5["nodes"]}
        self.assertEqual(base_nodes[353], sampled_nodes[353])
        self.assertEqual(sampled_nodes[353]["type"], "MinimaxH3LatentUpscaler3D")
        self.assertEqual(conservative_nodes[353]["type"], "LatentUpscaleBy")
        self.assertEqual(conservative_nodes[353]["widgets_values_named"],
                         {"upscale_method": "bilinear", "scale_by": 1.5})
        self.assertEqual(conservative_v5_nodes[353]["type"], "MinimaxH3LatentUpscaler3D")
        self.assertEqual(conservative_v5_nodes[353]["widgets_values_named"]["model_name"],
                         "minimax_h3_bf16_CONSERVATIVE_v5.safetensors")
        self.assertEqual(conservative_v5_nodes[353]["widgets_values_named"]["align"], 32)
        self.assertTrue(conservative_v5_nodes[353]["widgets_values_named"]["keep_proportion"])
        self.assertEqual(conservative_v5_nodes[353]["widgets_values"][3:5], [32, True])

    def test_uploaded_audio_first_workflow_encodes_source_video_without_changing_audio_route(self):
        source = json.loads((ROOT / "example/alternative_vida0_inpaint_experiment.json").read_text(encoding="utf-8"))
        graph = json.loads((ROOT / "example/alternative_video_audio_inpaint_wired.json").read_text(encoding="utf-8"))
        nodes = {node["id"]: node for node in graph["nodes"]}
        links = {link[0]: link for link in graph["links"]}
        source_links = {link[0]: link for link in source["links"]}
        self.assertEqual([nodes[i]["type"] for i in (479, 480, 481, 482)],
                         ["ImageFromBatch", "ImageScale", "VAEEncode", "SkebaH3VideoEditMask"])
        expected = {928: (478, 479), 929: (417, 479), 930: (479, 480),
                    931: (442, 480), 932: (443, 480), 933: (480, 481),
                    934: (411, 481), 682: (481, 320), 684: (320, 482),
                    935: (482, 472), 734: (354, 483), 936: (483, 474),
                    937: (482, 484)}
        for link_id, (start, end) in expected.items():
            self.assertEqual((links[link_id][1], links[link_id][3]), (start, end))
        for link_id in (927, 907, 695, 680, 683, 920, 922):
            self.assertEqual(links[link_id], source_links[link_id])
        self.assertEqual(nodes[472]["widgets_values"], source["nodes"][[n["id"] for n in source["nodes"]].index(472)]["widgets_values"])
        self.assertEqual(nodes[482]["widgets_values_named"]["video_mask_strength"], 0.25)
        self.assertTrue(nodes[482]["widgets_values_named"]["extend_to_last_frame"])
        self.assertEqual(nodes[483]["widgets_values_named"]["video_mask_strength"], 0)
        self.assertEqual(nodes[474]["widgets_values_named"]["audio_mask_strength"], 0)
        for link in links.values():
            link_id, src, src_slot, dst, dst_slot, _ = link
            self.assertIn(link_id, nodes[src]["outputs"][src_slot]["links"])
            self.assertEqual(nodes[dst]["inputs"][dst_slot]["link"], link_id)

    def test_user_video_edit_ab_trials_keep_source_and_add_explicit_voice_reference(self):
        original = json.loads((ROOT / "example/video_experiment_edits.json").read_text(encoding="utf-8"))
        original_nodes = {node["id"]: node for node in original["nodes"]}
        self.assertEqual(original_nodes[179]["widgets_values_named"]["audio_mask_strength"], 0.7)
        for name in ("video_experiment_audio_focus.json", "video_experiment_voice_reference.json"):
            graph = json.loads((ROOT / f"example/{name}").read_text(encoding="utf-8"))
            nodes = {node["id"]: node for node in graph["nodes"]}
            links = {link[0]: link for link in graph["links"]}
            self.assertEqual(nodes[179]["widgets_values_named"]["sampling_denoise"], 1.0)
            self.assertEqual(nodes[179]["widgets_values_named"]["audio_mask_strength"], 1.0)
            self.assertEqual(nodes[179]["widgets_values_named"]["video_mask_strength"], 0.25)
            self.assertEqual(nodes[181]["type"], "Video Slice")
            for link_id, src, src_slot, dst, dst_slot, _ in graph["links"]:
                self.assertIn(link_id, nodes[src]["outputs"][src_slot]["links"])
                self.assertEqual(nodes[dst]["inputs"][dst_slot]["link"], link_id)
            if name.endswith("voice_reference.json"):
                self.assertEqual(nodes[19]["type"], "MiniMaxH3ReferenceToVideo")
                self.assertEqual(nodes[182]["type"], "TrimAudioDuration")
                self.assertIn("<Audio 1>", nodes[19]["widgets_values_named"]["prompt"])
                self.assertIn("<Picture 1>", nodes[19]["widgets_values_named"]["prompt"])
                self.assertEqual(links[nodes[19]["inputs"][3]["link"]][1], 5)

    def test_latent_context_trial_matches_fractional_audio_mask_path(self):
        graph = json.loads((ROOT / "example/video_experiment_latent_context.json").read_text(encoding="utf-8"))
        nodes = {node["id"]: node for node in graph["nodes"]}
        links = {link[0]: link for link in graph["links"]}
        controls = nodes[179]["widgets_values_named"]
        self.assertEqual(controls["sampling_denoise"], 1.0)
        self.assertEqual(controls["audio_mask_strength"], 0.5)
        self.assertEqual(controls["video_mask_strength"], 0.25)
        self.assertEqual(controls["sampler_name"], "res_multistep")
        self.assertEqual(controls["control_after_generate"], "fixed")
        self.assertEqual(nodes[19]["type"], "MiniMaxH3ImageToVideo")
        self.assertFalse(any("ref_audios.ref_audio_0" in [i["name"] for i in n.get("inputs", [])]
                             for n in nodes.values()))
        self.assertEqual(links[nodes[179]["inputs"][0]["link"]][1], 13)

    def test_video_audio_experiment_uploads_source_av_and_exports_result(self):
        graph = json.loads((ROOT / "example/video_experiment.json").read_text(encoding="utf-8"))
        nodes = {node["id"]: node for node in graph["nodes"]}
        links = {link[0]: link for link in graph["links"]}
        self.assertEqual(len(nodes), len(graph["nodes"]))
        self.assertEqual(len(links), len(graph["links"]))
        self.assertEqual(nodes[1]["type"], "LoadVideo")
        self.assertEqual(nodes[175]["type"], "SkebaH3AVInpaintRange")
        self.assertEqual(nodes[175]["widgets_values_named"]["video_mask_strength"], 0.25)
        self.assertEqual(nodes[175]["widgets_values_named"]["audio_mask_strength"], 1.0)
        self.assertEqual(nodes[175]["widgets_values_named"]["video_start_seconds"], 1.0)
        self.assertEqual(nodes[175]["widgets_values_named"]["audio_start_seconds"], 1.0)
        self.assertEqual(nodes[175]["widgets_values_named"]["sampling_denoise"], 0.65)
        self.assertEqual(nodes[29]["type"], "SaveVideo")
        self.assertEqual(nodes[178]["type"], "SaveAudioMP3")
        upstream = {(link[1], link[3]) for link in links.values()}
        for edge in ((1, 2), (2, 3), (3, 5), (3, 12), (5, 11),
                     (11, 13), (12, 13), (13, 175), (175, 25),
                     (25, 26), (25, 27), (26, 28), (27, 28),
                     (28, 29), (27, 178)):
            self.assertIn(edge, upstream)
        self.assertFalse(any(node["type"] == "VHS_LoadAudioUpload" for node in nodes.values()))
        for link in links.values():
            link_id, src, src_slot, dst, dst_slot, _ = link
            self.assertIn(link_id, nodes[src]["outputs"][src_slot]["links"])
            self.assertEqual(nodes[dst]["inputs"][dst_slot]["link"], link_id)

    def test_pre_sampler_edit_masks_audio_once_and_saves_monitor(self):
        graph = json.loads((ROOT / "example/audio_pre_inpaint_experiment.json").read_text(encoding="utf-8"))
        nodes = {node["id"]: node for node in graph["nodes"]}
        links = {link[0]: link for link in graph["links"]}
        self.assertEqual(len(nodes), len(graph["nodes"]))
        self.assertEqual(len(links), len(graph["links"]))
        self.assertEqual(nodes[472]["type"], "SkebaH3AudioEditMask")
        self.assertEqual(nodes[472]["widgets_values_named"]["audio_mask_strength"], 0.5)
        self.assertEqual(nodes[474]["widgets_values_named"]["audio_mask_strength"], 0.0)
        self.assertEqual(links[684][1:4], [320, 0, 472])
        self.assertEqual(links[920][1:4], [472, 0, 322])
        self.assertEqual(links[734][1:4], [354, 0, 474])
        self.assertEqual(links[922][1:4], [474, 0, 358])
        self.assertEqual(links[921][1:4], [299, 0, 473])
        self.assertEqual(links[923][1:4], [472, 1, 475])
        for link_id in (684, 734, 920, 921, 922, 923):
            _, src, src_slot, dst, dst_slot, kind = links[link_id]
            self.assertIn(link_id, nodes[src]["outputs"][src_slot]["links"])
            self.assertEqual(nodes[dst]["inputs"][dst_slot]["link"], link_id)
        self.assertEqual(links[919][1:4], [460, 0, 262])
        self.assertEqual(nodes[262]["title"], "Save Combined Video - generated clip audio")

    def test_experiment_inserts_inpaint_and_saves_audio_separately(self):
        source = json.loads((ROOT / "example/audio_workflow.json").read_text(encoding="utf-8"))
        graph = json.loads((ROOT / "example/audio_inpaint_experiment.json").read_text(encoding="utf-8"))
        nodes = {node["id"]: node for node in graph["nodes"]}
        links = {link[0]: link for link in graph["links"]}
        self.assertEqual(len(nodes), len(graph["nodes"]))
        self.assertEqual(len(links), len(graph["links"]))
        self.assertEqual(len(graph["nodes"]), len(source["nodes"]) + 2)
        self.assertEqual(nodes[472]["type"], "SkebaH3AudioInpaintRange")
        self.assertEqual(links[830][1:4], [358, 0, 472])
        self.assertEqual(links[920][1:4], [472, 0, 423])
        self.assertEqual(links[921][1], 377)
        self.assertEqual(links[922][1], 360)
        self.assertEqual(links[923][1], 356)
        self.assertEqual(links[924][1:4], [299, 0, 473])
        self.assertEqual(links[919][1:4], [460, 0, 262])
        self.assertEqual(next(node for node in source["nodes"] if node["id"] == 470)["inputs"][1]["link"], 918)
        for link in links.values():
            link_id, src, src_slot, dst, dst_slot, kind = link
            self.assertIn(link_id, nodes[src]["outputs"][src_slot]["links"])
            self.assertEqual(nodes[dst]["inputs"][dst_slot]["link"], link_id)
            if link_id >= 920:
                self.assertIn(nodes[src]["outputs"][src_slot]["type"], (kind, "*"))
                self.assertEqual(nodes[dst]["inputs"][dst_slot]["type"], kind)


if __name__ == "__main__":
    unittest.main()

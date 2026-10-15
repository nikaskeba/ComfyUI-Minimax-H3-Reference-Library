import importlib.util
import json
from pathlib import Path
import unittest

import torch
import torch.nn.functional as F


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("h3_mask_composite_test", ROOT / "h3_mask_composite.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
COMPOSITE = MODULE.SkebaH3FinalInpaintComposite()


class FinalInpaintCompositeTests(unittest.TestCase):
    def test_expanded_subject_mask_preserves_source_outside(self):
        source = torch.zeros((2, 9, 9, 3))
        source[..., 0] = 0.25
        generated = torch.ones((2, 18, 18, 3))
        mask = torch.zeros((2, 9, 9))
        mask[0, 4, 4] = 1
        mask[1, 2, 6] = 1
        result, = COMPOSITE.composite(source, generated, mask, expand_mask=1, feather_edge=1)
        for frame, (row, col) in enumerate(((4, 4), (2, 6))):
            self.assertTrue((result[frame, row * 2, col * 2] > 0.7).all())
            self.assertTrue(torch.equal(result[frame, 0, 0], source[frame, 0, 0]))
            allowed = F.interpolate(
                F.max_pool2d(mask[frame][None, None], 3, stride=1, padding=1),
                size=(18, 18), mode="nearest",
            )[0, 0].bool()
            resized_source = F.interpolate(source[frame].permute(2, 0, 1)[None],
                                           size=(18, 18), mode="bilinear",
                                           align_corners=False)[0].permute(1, 2, 0)
            self.assertTrue(torch.equal(result[frame][~allowed], resized_source[~allowed]))
        self.assertTrue(((result[0] > 0.25) & (result[0] < 1)).any())
        self.assertTrue(torch.equal(mask[0, 0], torch.zeros(9)))

    def test_white_background_changes_background_not_black_subject(self):
        source = torch.zeros((1, 7, 7, 3))
        generated = torch.ones_like(source)
        mask = torch.ones((1, 7, 7))
        mask[:, 2:5, 2:5] = 0
        result, = COMPOSITE.composite(source, generated, mask, expand_mask=0, feather_edge=0)
        self.assertTrue(torch.equal(result[0, 3, 3], torch.zeros(3)))
        self.assertTrue(torch.equal(result[0, 0, 0], torch.ones(3)))

    def test_disabled_is_exact_bypass(self):
        generated = torch.rand((2, 4, 4, 3))
        result, = COMPOSITE.composite(torch.empty((0, 1, 1, 3)), generated,
                                      torch.empty((0, 1, 1)), enabled=False)
        self.assertIs(result, generated)

    def test_invalid_alignment_fails_clearly(self):
        source = torch.zeros((2, 4, 4, 3))
        generated = torch.ones((3, 8, 8, 3))
        with self.assertRaisesRegex(ValueError, "matching source, mask, and generated frame counts"):
            COMPOSITE.composite(source, generated, torch.ones((2, 4, 4)))
        with self.assertRaisesRegex(ValueError, "match the resized source canvas"):
            COMPOSITE.composite(source, generated[:2], torch.ones((2, 5, 5)))

    def test_generation_grid_clamps_extra_expansion(self):
        source = torch.zeros((1, 12, 12, 3))
        generated = torch.ones_like(source)
        selection = torch.zeros((1, 12, 12))
        selection[:, 4:8, 4:8] = 1
        grid = torch.zeros_like(selection)
        grid[:, 3:9, 3:9] = 1
        result = COMPOSITE.composite(source, generated, selection,
                                     expand_mask=4, feather_edge=0,
                                     generation_mask=grid)[0]
        self.assertTrue(torch.all(result[:, :3] == 0))
        self.assertTrue(torch.all(result[:, 9:] == 0))
        self.assertEqual(float(result[0, 5, 5, 0]), 1.0)

    def test_workflow_composites_before_trim_and_playlist(self):
        graph = json.loads((ROOT / "example/Minimax_Upscale_Loop_Workflow-Oct_13Inpainting.json")
                           .read_text(encoding="utf-8"))
        nodes = {n["id"]: n for n in graph["nodes"]}
        links = {l[0]: l for l in graph["links"]}
        composite = nodes[1292]
        self.assertEqual(composite["type"], "SkebaH3FinalInpaintComposite")
        self.assertEqual(composite["widgets_values_named"],
                         dict(zip(("enabled", "expand_mask", "feather_edge"),
                                  composite["widgets_values"])))
        self.assertEqual([links[i["link"]][1] for i in composite["inputs"][:3]],
                         [1167, 298, 1164])
        self.assertEqual(links[next(i["link"] for i in composite["inputs"]
                                    if i["name"] == "generation_mask")][1], 1165)
        self.assertEqual(links[nodes[265]["inputs"][0]["link"]][1], 1292)
        self.assertEqual(links[nodes[930]["inputs"][0]["link"]][1], 1292)
        self.assertEqual(links[nodes[265]["inputs"][1]["link"]][1], 323)
        for link in graph["links"]:
            lid, src, src_slot, dst, dst_slot, _ = link
            self.assertIn(lid, nodes[src]["outputs"][src_slot]["links"])
            self.assertEqual(nodes[dst]["inputs"][dst_slot]["link"], lid)


if __name__ == "__main__":
    unittest.main()

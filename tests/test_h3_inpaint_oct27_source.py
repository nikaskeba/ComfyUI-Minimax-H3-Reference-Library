import importlib.util
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
COMFY = ROOT.parents[1]
if str(COMFY) not in sys.path:
    sys.path.insert(0, str(COMFY))
SPEC = importlib.util.spec_from_file_location("h3_inpaint_oct27_source_test", ROOT / "h3_inpaint_source_loop.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Oct27SourceTests(unittest.TestCase):
    def test_choice_lists_local_files_and_returns_selection(self):
        node = MODULE.SkebaH3InpaintVideoChoice()
        self.assertEqual(node.choose("(no source video)"), ("(no source video)",))
        self.assertIn("video", node.INPUT_TYPES()["required"])
        self.assertEqual(MODULE.SkebaH3InpaintStartFrame().select(120), (120,))

    def test_batch_fit_and_source_window_share_selected_video(self):
        workflow = json.loads((ROOT / "example/inpaint_oct27.json").read_text(encoding="utf-8"))
        nodes = {node["id"]: node for node in workflow["nodes"]}
        links = {link[0]: link for link in workflow["links"]}
        choice = next(node for node in nodes.values() if node["type"] == "SkebaH3InpaintVideoChoice")
        outer_link = links[choice["outputs"][0]["links"][0]]
        instance = nodes[outer_link[3]]
        self.assertEqual(instance["inputs"][outer_link[4]]["name"], "source_video")
        subgraph = next(s for s in workflow["definitions"]["subgraphs"] if s["id"] == instance["type"])
        inner_link = next(link for link in subgraph["links"]
                          if link["origin_id"] == -10 and link["origin_slot"] == outer_link[4])
        batch_fit = next(node for node in subgraph["nodes"] if node["id"] == inner_link["target_id"])
        self.assertEqual(batch_fit["type"], "SkebaH3InpaintBatchFit")
        self.assertEqual(batch_fit["inputs"][inner_link["target_slot"]]["name"], "video")
        # A saved copy opened before the shared selector runs must not retain
        # a different video in the legacy Batch Fit widget.
        selected_video = choice["widgets_values"][0]
        self.assertEqual(batch_fit["widgets_values_named"]["video"], selected_video)
        self.assertEqual(batch_fit["widgets_values"][0], selected_video)
        self.assertEqual(nodes[1324]["widgets_values"][0], selected_video)
        start = next(node for node in nodes.values() if node["type"] == "SkebaH3InpaintStartFrame")
        start_link = links[start["outputs"][0]["links"][0]]
        self.assertEqual(start_link[3], instance["id"])
        self.assertEqual(instance["inputs"][start_link[4]]["name"], "source_start_frame")
        inner_start_link = next(link for link in subgraph["links"]
                                if link["origin_id"] == -10 and link["origin_slot"] == start_link[4])
        self.assertEqual(inner_start_link["target_id"], batch_fit["id"])
        self.assertEqual(batch_fit["inputs"][inner_start_link["target_slot"]]["name"], "start_frame")
        batch_video_link = next(link for link in workflow["links"]
                                if link[1] == instance["id"] and link[2] == 13)
        self.assertEqual(nodes[batch_video_link[3]]["type"], "Setter")
        self.assertEqual(nodes[1324]["type"], "SkebaH3InpaintSourceWindow")
        self.assertEqual(nodes[1324]["widgets_values"][-2], "controlnet and inpainting")


if __name__ == "__main__":
    unittest.main()

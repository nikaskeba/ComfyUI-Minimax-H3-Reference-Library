import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("h3_upscale_bypass", ROOT / "h3_upscale_bypass.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class UpscaleBypassTests(unittest.TestCase):
    def test_only_selected_latent_is_requested(self):
        node = module.SkebaH3UpscaleBypass()
        self.assertEqual(node.check_lazy_status("Base only"), ["base_latent"])
        self.assertEqual(node.check_lazy_status("Upscaled"), ["upscaled_latent"])
        base, upscale = object(), object()
        self.assertEqual(node.select("Base only", True, base_latent=base), (base, False))
        self.assertEqual(node.select("Upscaled", True, upscaled_latent=upscale), (upscale, True))
        self.assertEqual(node.select("Upscaled", False, upscaled_latent=upscale), (upscale, False))

    def test_workflow_routes_decode_and_upscale_cache_through_selector(self):
        workflow = json.loads((ROOT / "example/MainWokflow-Oct199 -alt-upscaler.json").read_text(encoding="utf-8"))
        nodes = {node["id"]: node for node in workflow["nodes"]}
        links = {link[0]: link for link in workflow["links"]}
        selector = nodes[1232]
        self.assertEqual(selector["type"], "SkebaH3UpscaleBypass")
        self.assertEqual(selector["widgets_values"][0], "Upscaled")
        by_name = {item["name"]: item for item in selector["inputs"]}
        self.assertEqual(links[by_name["base_latent"]["link"]][1], 1233)
        self.assertEqual(links[by_name["upscaled_latent"]["link"]][1], 1184)
        self.assertEqual(links[nodes[1200]["inputs"][0]["link"]][1], 1232)
        self.assertEqual(links[nodes[1220]["inputs"][10]["link"]][1:5], [1232, 1, 1220, 10])
        self.assertEqual({link[0] for link in workflow["links"]},
                         {link for node in workflow["nodes"] for slot in node.get("inputs", [])
                          if (link := slot.get("link")) is not None} |
                         {link for node in workflow["nodes"] for slot in node.get("outputs", [])
                          for link in slot.get("links") or []})

    def test_trim_selector_only_requests_selected_pass(self):
        node = module.SkebaH3UpscaleTrimBypass()
        self.assertEqual(node.check_lazy_status("Base only"), ["base_trim_frames"])
        self.assertEqual(node.check_lazy_status("Upscaled"), ["upscaled_trim_frames"])
        self.assertEqual(node.select("Base only", base_trim_frames=22), (22,))
        self.assertEqual(node.select("Upscaled", upscaled_trim_frames=39), (39,))

    def test_oct21_workflow_trim_does_not_force_upscale_pass(self):
        workflow = json.loads((ROOT / "example/MainWokflow-Oct211 -alt-upscaler.json").read_text(encoding="utf-8"))
        nodes = {node["id"]: node for node in workflow["nodes"]}
        links = {link[0]: link for link in workflow["links"]}
        base = next(item for item in workflow["definitions"]["subgraphs"] if item["name"] == "First Pass")
        self.assertEqual(base["outputs"][3]["name"], "trim_frames")
        source = next(link for link in base["links"] if link["id"] == base["outputs"][3]["linkIds"][0])
        self.assertEqual((source["origin_id"], source["origin_slot"]), (1205, 1))
        selector = nodes[1248]
        self.assertEqual(selector["type"], "SkebaH3UpscaleTrimBypass")
        self.assertEqual(links[selector["inputs"][1]["link"]][1:3], [1207, 3])
        self.assertEqual(links[selector["inputs"][2]["link"]][1:3], [1218, 2])
        self.assertEqual(links[nodes[612]["inputs"][0]["link"]][1:3], [1248, 0])


if __name__ == "__main__":
    unittest.main()

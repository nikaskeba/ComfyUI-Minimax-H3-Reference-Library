"""Final loop clips should not evaluate or save continuation latents."""

import ast
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TREE = ast.parse((ROOT / "motion_context" / "nodes.py").read_text(encoding="utf-8"))
SAVE_CLASS = next(
    node for node in TREE.body
    if isinstance(node, ast.ClassDef) and node.name == "MiniMaxH3MotionContextSaveLatent"
)
namespace = {"_st_save": None}
exec(compile(ast.Module(body=[SAVE_CLASS], type_ignores=[]), "<save-latent>", "exec"), namespace)
SaveLatent = namespace["MiniMaxH3MotionContextSaveLatent"]


class SaveLatentLastPromptTests(unittest.TestCase):
    def test_disabled_save_does_not_request_or_process_latent(self):
        node = SaveLatent()
        self.assertEqual(
            node.check_lazy_status("h3_context/clip", 1, False, latent=None), []
        )
        self.assertEqual(node.save(None, "h3_context/clip", 1, False), ("",))

    def test_enabled_and_legacy_save_still_request_latent(self):
        node = SaveLatent()
        self.assertEqual(node.check_lazy_status("h3_context/clip", 1), ["latent"])
        self.assertEqual(node.check_lazy_status("h3_context/clip", 1, True), ["latent"])
        with self.assertRaisesRegex(RuntimeError, "safetensors"):
            node.save(None, "h3_context/clip", 1, True)

    def test_oct16_workflow_gates_both_continuation_saves(self):
        workflow = json.loads(
            (ROOT / "example" / "MainWokflow-Oct16 .json").read_text(encoding="utf-8")
        )
        nodes = {node["id"]: node for node in workflow["nodes"]}
        links = {link[0]: link for link in workflow["links"]}
        gate = next(node for node in nodes.values()
                    if node.get("title") == "More prompts remain — save continuation?")
        self.assertEqual(gate["widgets_values"][0], "a < b")
        self.assertEqual(links[gate["inputs"][0]["link"]][1:3], [266, 1])
        self.assertEqual(links[gate["inputs"][1]["link"]][1:3], [258, 1])
        for node_id in (269, 334):
            save = nodes[node_id]
            condition = next(item for item in save["inputs"]
                             if item["name"] == "save_if_next_prompt")
            self.assertEqual(links[condition["link"]][1:3], [gate["id"], 2])


if __name__ == "__main__":
    unittest.main()

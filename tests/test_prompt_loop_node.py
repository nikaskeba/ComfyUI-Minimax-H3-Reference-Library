import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "prompt_loop_node.py"
SPEC = importlib.util.spec_from_file_location("prompt_loop_node", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PromptLoopNodeTests(unittest.TestCase):
    def test_emits_prompts_count_and_one_based_numbers(self):
        result = MODULE.PromptLoopNode().split_prompts(
            "first\n\nsecond\n third ", skip_empty=True
        )

        self.assertEqual(
            result,
            (["first", "second", "third"], 3, [1, 2, 3], ["first", "second", "third"]),
        )

    def test_preserves_empty_entries_when_requested(self):
        result = MODULE.PromptLoopNode().split_prompts("first|| third ", "|", False)

        self.assertEqual(result, (["first", "", "third"], 3, [1, 2, 3], ["first", "", "third"]))

    def test_selector_wraps_and_reports_one_based_number(self):
        result = MODULE.PromptFromListNode().get_prompt(["first", "second"], 3)

        self.assertEqual(result, ("second", 2))

    def test_selector_handles_empty_batch(self):
        self.assertEqual(MODULE.PromptFromListNode().get_prompt([], 0), ("", 0))

    def test_nodes_are_grouped_with_skeba_utilities(self):
        self.assertEqual(MODULE.PromptLoopNode.CATEGORY, "Skeba AI Nodes - Utilities")
        self.assertEqual(MODULE.PromptFromListNode.CATEGORY, "Skeba AI Nodes - Utilities")


if __name__ == "__main__":
    unittest.main()

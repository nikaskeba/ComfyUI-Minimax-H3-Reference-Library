import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "universal_bypass.py"
SPEC = importlib.util.spec_from_file_location("skeba_universal_bypass", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def prompt_for(node_id, *output_indices):
    return {
        f"consumer_{index}": {"inputs": {"value": [str(node_id), output_index]}}
        for index, output_index in enumerate(output_indices)
    }


class UniversalBypassTests(unittest.TestCase):
    def setUp(self):
        self.node = MODULE.SkebaUniversalBypass()

    def test_declares_sixteen_lazy_pairs_and_outputs(self):
        input_types = self.node.INPUT_TYPES()

        self.assertEqual(len(self.node.RETURN_TYPES), 16)
        self.assertEqual(self.node.RETURN_NAMES[-1], "output_16")
        self.assertFalse(input_types["required"]["bypass"][1]["default"])
        self.assertEqual(input_types["required"]["bypass"][1]["label_off"], "PROCESS")
        self.assertEqual(input_types["required"]["bypass"][1]["label_on"], "BYPASS")
        self.assertTrue(input_types["optional"]["original_16"][1]["lazy"])
        self.assertTrue(input_types["optional"]["processed_16"][1]["lazy"])

    def test_process_requests_and_returns_only_processed_values(self):
        self.assertEqual(
            self.node.check_lazy_status(
                False,
                original_1=None,
                processed_1=None,
                original_2=None,
                processed_2="audio",
            ),
            ["processed_1"],
        )

        outputs = self.node.route(
            False,
            original_1="original image",
            processed_1="processed image",
            original_2={"model": "original"},
            processed_2={"model": "processed"},
        )
        self.assertEqual(outputs[:2], ("processed image", {"model": "processed"}))
        self.assertEqual(outputs[2:], (None,) * 14)

    def test_bypass_requests_and_returns_only_original_values(self):
        self.assertEqual(
            self.node.check_lazy_status(
                True,
                original_1=None,
                processed_1=None,
                original_2="latent",
                processed_2=None,
            ),
            ["original_1"],
        )

        outputs = self.node.route(
            True,
            original_1="original conditioning",
            processed_1="processed conditioning",
        )
        self.assertEqual(outputs[0], "original conditioning")

    def test_unselected_branch_may_be_disconnected(self):
        self.assertEqual(self.node.check_lazy_status(False, processed_1=None), ["processed_1"])
        self.assertEqual(self.node.route(False, processed_1="value")[0], "value")
        self.assertEqual(self.node.route(True, original_1="value")[0], "value")

    def test_connected_output_requires_selected_input(self):
        prompt = prompt_for(77, 0)

        with self.assertRaisesRegex(ValueError, "lane 1: connect processed_1.*PROCESS"):
            self.node.check_lazy_status(
                False,
                prompt=prompt,
                unique_id="77",
                original_1=None,
            )
        with self.assertRaisesRegex(ValueError, "lane 1: connect original_1.*BYPASS"):
            self.node.check_lazy_status(
                True,
                prompt=prompt,
                unique_id="77",
                processed_1=None,
            )

    def test_middle_lane_gaps_keep_output_indices_stable(self):
        prompt = prompt_for(42, 0, 2, 15)
        outputs = self.node.route(
            False,
            prompt=prompt,
            unique_id=42,
            processed_1="image",
            processed_3="audio",
            processed_16="conditioning",
        )

        self.assertEqual(outputs[0], "image")
        self.assertIsNone(outputs[1])
        self.assertEqual(outputs[2], "audio")
        self.assertEqual(outputs[15], "conditioning")


if __name__ == "__main__":
    unittest.main()

import importlib
from pathlib import Path
import sys
import types
import unittest

package = types.ModuleType("choice_test_package")
package.__path__ = [str(Path(__file__).parents[1])]
sys.modules[package.__name__] = package
Node = importlib.import_module(package.__name__ + ".custom_choice").SkebaCustomChoice


class CustomChoiceTests(unittest.TestCase):
    def test_native_combo_and_dynamic_validation(self):
        self.assertEqual(Node.INPUT_TYPES()["required"]["selected"][0], ["5", "22", "39", "56"])
        self.assertIs(Node.VALIDATE_INPUTS("standard\nscene reference", "scene reference"), True)
        self.assertIs(Node.VALIDATE_INPUTS("5\n22", None), True)
        self.assertIs(Node.VALIDATE_INPUTS(None, "22"), True)
        self.assertIsNot(Node.VALIDATE_INPUTS("5\n22", "39"), True)
        self.assertIsNot(Node.VALIDATE_INPUTS("", "22"), True)

    def test_combo_values_remain_strings(self):
        self.assertEqual(Node().choose("5, 22, 39, 56", "22"), ("22",))
        self.assertEqual(Node().choose("standard\npre-cut reinforcement\nscene reference", "scene reference"), ("scene reference",))

    def test_typed_values_and_zero(self):
        for choice, kind, expected in [("0", "integer", 0), ("22", "integer", 22), ("0.5", "decimal", .5), ("false", "boolean", False), ("true", "boolean", True)]:
            value = Node().choose(choice, choice, kind)[0]
            self.assertEqual(value, expected)
            self.assertIs(type(value), type(expected))

    def test_invalid_selection_or_conversion_is_not_silently_changed(self):
        for args in [("", ""), ("5,22", "39"), ("2.5", "2.5", "integer"), ("nan", "nan", "decimal"), ("maybe", "maybe", "boolean")]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                Node().choose(*args)

    def test_whitespace_duplicates_and_literal_text(self):
        self.assertEqual(Node().choose(" 22\r\n22\n5 ", "22"), ("22",))
        self.assertEqual(Node().choose("<b>literal</b>", "<b>literal</b>"), ("<b>literal</b>",))


if __name__ == "__main__":
    unittest.main()

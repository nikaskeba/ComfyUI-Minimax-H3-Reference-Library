"""Attachment ownership and upload handling without starting ComfyUI."""
import ast
import json
from pathlib import Path
import unittest
from unittest.mock import Mock


class ImageUploadTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse((Path(__file__).parents[1] / "server.py").read_text(encoding="utf-8"))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_read_additional_images")
        self.save = Mock(return_value="new.png")
        namespace = {"json": json, "_save_image": self.save}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "server.py", "exec"), namespace)
        self.read = namespace[function.name]

    def test_existing_and_uploaded_images_keep_order_and_descriptions(self):
        created = []
        result = self.read({"additional_images": json.dumps([
            {"image_file": "side.png", "description": "Profile"},
            {"upload": "extra_image_1", "description": "Back"}])},
            {"extra_image_1": ("upload.png", b"data")},
            {"additional_images": [{"image_file": "side.png"}]}, created)
        self.assertEqual(result, [{"image_file": "side.png", "description": "Profile"},
                                  {"image_file": "new.png", "description": "Back"}])
        self.assertEqual(created, ["new.png"])
        self.save.assert_called_once_with("upload.png", b"data")

    def test_foreign_files_and_missing_uploads_are_rejected(self):
        for spec in ({"image_file": "foreign.png"}, {"image_file": "../foreign.png"},
                     {"upload": "extra_image_missing"}, {"upload": "image"}):
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                self.read({"additional_images": json.dumps([spec])}, {}, {}, [])
        self.save.assert_not_called()

    def test_omitted_preserves_existing_and_empty_list_clears(self):
        self.assertIsNone(self.read({}, {}, {}, []))
        self.assertEqual(self.read({"additional_images": "[]"}, {}, {}, []), [])


if __name__ == "__main__":
    unittest.main()

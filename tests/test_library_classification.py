import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path


sys.modules.setdefault(
    "folder_paths",
    types.SimpleNamespace(get_user_directory=lambda: "unused"),
)
MODULE_PATH = Path(__file__).parents[1] / "library.py"
SPEC = importlib.util.spec_from_file_location("h3_reference_library", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class LibraryClassificationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.original_library_root = MODULE.library_root
        MODULE.library_root = lambda: self.root

    def tearDown(self):
        MODULE.library_root = self.original_library_root
        self.temporary.cleanup()

    def test_missing_classification_defaults_to_uncategorized(self):
        MODULE.ensure_library()
        manifest = {
            "version": 1,
            "revision": 4,
            "records": [{"id": "legacy", "tag": "old_reference", "category": "archive"}],
        }
        MODULE.manifest_path().write_text(json.dumps(manifest), encoding="utf-8")

        record = MODULE.list_records()[0]

        self.assertEqual(record["reference_type"], "uncategorized")
        self.assertEqual(MODULE.library_revision(), 4)

    def test_create_and_update_store_valid_reference_types(self):
        record = MODULE.create_record(
            "jerry",
            "seinfeld",
            image_file="jerry.png",
            reference_type="character",
        )
        self.assertEqual(record["reference_type"], "character")

        updated, _, _ = MODULE.update_record(
            record["id"],
            "jerry_apartment",
            "seinfeld",
            image_file="jerry.png",
            reference_type="location",
        )
        self.assertEqual(updated["reference_type"], "location")

    def test_unknown_reference_type_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Reference type must be one of"):
            MODULE.create_record(
                "invalid",
                image_file="invalid.png",
                reference_type="vehicle",
            )


if __name__ == "__main__":
    unittest.main()

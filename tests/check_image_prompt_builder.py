"""Local checks for image prompt builder photo and reference resolution."""
import importlib
from pathlib import Path
import sys
import tempfile
import types
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parents[1]))
sys.argv = ["check", "--cpu"]
import comfy.options
comfy.options.enable_args_parsing()
package = types.ModuleType("image_builder_test")
package.__path__ = [str(ROOT)]
sys.modules[package.__name__] = package
module = importlib.import_module("image_builder_test.image_tagged_reference_prompt")

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    photo = root / "one time.png"
    Image.new("RGB", (12, 8), "red").save(photo)
    records = {"Alice": {"image_file": photo.name, "reference_type": "character"},
               "missing": {"reference_type": "object"}}
    with patch.object(module.folder_paths, "get_input_directory", return_value=directory), \
         patch.object(module, "records_by_tag", return_value=records), \
         patch.object(module, "library_built_in_records", return_value={}), \
         patch.object(module, "media_path", return_value=photo):
        module.H3ImagePromptBuilder.define_schema()
        prompt = "Take {photo:one time.png} and match {Alice}. Keep {photo:one time.png}."
        built = module.H3ImagePromptBuilder.execute(prompt)[0]
        result = module.H3ImageTaggedReferencePrompt.execute(built)
        assert result[0] == "Take <image 1> <subject 1> and match <image 2> <subject 2>. Keep <image 1> <subject 1>."
        assert result[1].shape == (1, 8, 12, 3) and result[2].shape == (1, 8, 12, 3)
        assert result[3] is None
        choices = module.builder_choices()
        assert [r["tag"] for r in choices["references"]] == ["Alice"]
        assert choices["photos"] == ["one time.png"]
        assert module.H3ImageTaggedReferencePrompt.fingerprint_inputs(prompt)
        for tag in ["photo:../outside.png", "photo:" + str(root.parent / "outside.png")]:
            try:
                module.image_path(tag, records)
            except ValueError:
                pass
            else:
                raise AssertionError("Accepted a photo outside input")
        try:
            module.image_path("photo:missing.png", records)
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("Accepted a missing photo")
print("PASS: builder-to-resolver prompt, real photo tensors, deduplication, searchable image-only references, cache fingerprint and path containment")

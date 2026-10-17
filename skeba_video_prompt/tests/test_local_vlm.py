import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import torch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT.parents[1]))
parent = types.ModuleType("h3_tag_references")
parent.__path__ = [str(ROOT)]
sys.modules.setdefault(parent.__name__, parent)

from h3_tag_references.skeba_video_prompt import nodes, vlm  # noqa: E402


def model_folder(base, model_type="qwen3_vl"):
    folder = Path(base) / "Qwen-VL"
    folder.mkdir()
    (folder / "config.json").write_text(json.dumps({"model_type": model_type}))
    for name in ("model.safetensors", "preprocessor_config.json", "tokenizer.json"):
        (folder / name).write_bytes(b"test")
    return folder


class LocalVLMTests(unittest.TestCase):
    def test_discovers_only_complete_qwen_vlm_folders(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = model_folder(directory)
            (Path(directory) / "text_clip.safetensors").write_bytes(b"test")
            with patch.object(nodes, "_model_roots", return_value=(Path(directory),)):
                self.assertEqual(nodes.local_vlm_folders(), ["Qwen-VL"])
                self.assertEqual(nodes._resolve_model("Qwen-VL", ""), folder.resolve())
                # Old workflows can still pass their previously saved path.
                self.assertEqual(nodes._resolve_model(str(folder), ""), folder.resolve())
            self.assertEqual(nodes._resolve_model(str(folder), ""), folder.resolve())
            with self.assertRaisesRegex(ValueError, "single CLIP"):
                nodes._resolve_model(str(Path(directory) / "text_clip.safetensors"), "")

    def test_rejects_non_vlm_and_incomplete_folders(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = model_folder(directory, "florence2")
            self.assertFalse(nodes._supported_model(folder))
            (folder / "config.json").write_text('{"model_type":"qwen3_vl"}')
            (folder / "preprocessor_config.json").unlink()
            self.assertFalse(nodes._supported_model(folder))

    def test_duplicate_model_names_are_disambiguated_without_drive_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            first_root = Path(directory) / "LLM"
            second_root = Path(directory) / "clip"
            first_root.mkdir()
            second_root.mkdir()
            first = model_folder(first_root)
            second = model_folder(second_root)
            with patch.object(nodes, "_model_roots", return_value=(first_root, second_root)):
                self.assertEqual(nodes.local_vlm_folders(), ["clip/Qwen-VL", "LLM/Qwen-VL"])
                self.assertEqual(nodes._resolve_model("LLM/Qwen-VL", ""), first.resolve())
                self.assertEqual(nodes._resolve_model("clip/Qwen-VL", ""), second.resolve())

    def test_loader_uses_local_files_only_and_no_snapshot_download(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = model_folder(directory)
            processor = object()
            model = MagicMock()
            model.eval.return_value = model
            transformers = types.ModuleType("transformers")
            transformers.__path__ = []
            transformers.AutoProcessor = types.SimpleNamespace(from_pretrained=MagicMock(return_value=processor))
            transformers.AutoModelForImageTextToText = types.SimpleNamespace(
                from_pretrained=MagicMock(return_value=model))
            transformers_utils = types.ModuleType("transformers.utils")
            import_utils = types.ModuleType("transformers.utils.import_utils")
            import_utils._tf_available = True
            with patch.object(vlm, "execution_device", return_value=torch.device("cpu")), \
                 patch.object(vlm, "pick_dtype", return_value=torch.float32), \
                 patch.object(vlm, "ManagedTorchModel"), \
                 patch.dict(sys.modules, {"transformers": transformers,
                                          "transformers.utils": transformers_utils,
                                          "transformers.utils.import_utils": import_utils}):
                vlm.VLMPredictor(str(folder))
            self.assertFalse(import_utils._tf_available)
            load_processor = transformers.AutoProcessor.from_pretrained
            load_model = transformers.AutoModelForImageTextToText.from_pretrained
            for call in (load_processor.call_args, load_model.call_args):
                self.assertEqual(call.args[0], str(folder.resolve()))
                self.assertIs(call.kwargs["local_files_only"], True)
                self.assertIs(call.kwargs["trust_remote_code"], False)
            self.assertFalse(hasattr(vlm, "snapshot_download"))


if __name__ == "__main__":
    unittest.main()

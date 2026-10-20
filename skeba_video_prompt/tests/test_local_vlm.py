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

from h3_tag_references.skeba_video_prompt import nodes, pipeline, vlm  # noqa: E402


def model_folder(base, model_type="qwen3_vl"):
    folder = Path(base) / "Qwen-VL"
    folder.mkdir()
    (folder / "config.json").write_text(json.dumps({"model_type": model_type}))
    for name in ("model.safetensors", "preprocessor_config.json", "tokenizer.json"):
        (folder / name).write_bytes(b"test")
    return folder


class LocalVLMTests(unittest.TestCase):
    def test_analysis_prompt_field_starts_with_original_instructions(self):
        schema = nodes.SkebaH3VideoToPrompt.define_schema()
        field = next(item for item in schema.inputs if item.id == "analysis_prompt")
        self.assertEqual(field.default, pipeline.ANALYSIS_PROMPT)
        self.assertTrue(field.multiline)

    def test_custom_analysis_prompt_reaches_video_pass(self):
        predictor = MagicMock()
        predictor.generate.return_value = '{"shots": []}'
        with patch.object(pipeline, "frames_to_tensor", return_value=object()):
            pipeline.run_analysis(predictor, [(Path("frame.jpg"), 0)], None,
                                  None, 1.0, 256, "My custom instructions")
        self.assertEqual(predictor.generate.call_args.kwargs["prompt"],
                         "My custom instructions")

    def test_nemotron_srt_preserves_speakers_and_video_relative_times(self):
        srt = ("1\r\n00:00:06,480 --> 00:00:07,460\r\n"
               "[SPEAKER_01] There you are.\r\n\r\n"
               "2\r\n00:00:09,200 --> 00:00:10,720\r\n"
               "[SPEAKER_02] Okay, Sally, good to see ya.\r\n")
        self.assertEqual(pipeline.format_srt_transcript(srt, start=5.0, length=6.0),
                         "[1.480s-2.460s] SPEAKER_01: There you are.\n"
                         "[4.200s-5.720s] SPEAKER_02: Okay, Sally, good to see ya.")

    def test_srt_rejects_malformed_cues_and_skips_outside_window(self):
        with self.assertRaisesRegex(ValueError, "SRT cue 1"):
            pipeline.format_srt_transcript("[SPEAKER_01] Missing timestamps")
        self.assertEqual(pipeline.format_srt_transcript(
            "1\n00:00:01,000 --> 00:00:02,000\nEarly line", 5.0, 2.0), "")

    def test_tagged_output_uses_observed_shots_and_srt_speaker_placeholders(self):
        analysis = {
            "style": "Warm 1990s multicamera sitcom style",
            "subjects": [{"id": "C1", "description": "person in a blue jacket"}],
            "shots": [
                {"start": 0.0, "composition": "Wide bar interior", "subjects": ["C1"],
                 "environment": "Bar with warm lamps"},
                {"start": 6.4, "transition": "hard cut", "composition": "Close-up at the bar",
                 "actions": "The person turns toward the camera"},
                {"start": 9.1, "transition": "hard cut", "composition": "Reverse angle"},
            ],
            "sounds": "Low bar ambience",
        }
        transcript = ("[6.480s-7.460s] SPEAKER_01: There you are.\n"
                      "[9.200s-10.720s] SPEAKER_02: Okay, Sally, good to see ya.")
        result = pipeline.build_skeba_tagged_prompt(
            analysis, transcript, 15, "{10_forward_bar}")
        for field in ("subject_definitions:", "summary:", "detailed_description:",
                      "overall_soundscape:", "non_diegetic_music:"):
            self.assertIn(field, result)
        self.assertIn("{10_forward_bar}", result)
        self.assertIn("<character:speaker_01 =", result)
        self.assertIn("<character:speaker_02 =", result)
        self.assertIn("<Subject 1> - person in a blue jacket", result)
        self.assertIn("[Shot 1: 0s]", result)
        self.assertIn("[Shot 2: 6.4s]", result)
        self.assertIn("[Shot 3: 6.48s]", result)
        self.assertIn("[Shot 4: 9.1s]", result)
        self.assertIn("[Shot 5: 9.2s]", result)
        self.assertIn("<character:speaker_01> says, <d>[English]There you are.</d>", result)
        self.assertIn("<character:speaker_02> says, <d>[English]Okay, Sally, good to see ya.</d>", result)
        self.assertNotIn("C1", result)

    def test_tagged_subject_ids_and_separate_timed_speech_shots(self):
        analysis = {
            "style": "Bright multicamera television style",
            "subjects": [
                {"id": "C2", "description": "woman wearing a red jacket"},
                {"id": "C1", "description": "woman exercising with dumbbells"},
            ],
            "speakers": [{"id": "S2", "subject_id": "C2"}],
            "dialogue": [{"time": 9.11, "speaker": "S2", "text": "Hey Sally, good to see ya."}],
            "shots": [
                {"start": 0, "composition": "C1 exercises alone"},
                {"start": 7, "transition": "hard cut", "composition": "C2 faces C1",
                 "actions": "C2 speaks directly to C1 who continues exercising"},
                {"start": 10.8, "transition": "hard cut", "composition": "C1 turns toward C2"},
            ],
        }
        transcript = "[9.110s-10.500s] SPEAKER_02: Hey Sally, good to see ya."
        result = pipeline.build_skeba_tagged_prompt(analysis, transcript, 15)
        self.assertIn("<Subject 1> - woman exercising with dumbbells", result)
        self.assertIn("<Subject 2> - woman wearing a red jacket", result)
        self.assertIn("[Shot 2: 7s]", result)
        self.assertIn("[Shot 3: 9.11s] Continue the established framing. "
                      "<Subject 2> says, <d>[English]Hey Sally, good to see ya.</d>", result)
        self.assertIn("[Shot 4: 10.8s]", result)
        self.assertNotRegex(result, r"\bC[12]\b")
        self.assertNotIn("<character:speaker_02", result)

    def test_tagged_output_keeps_first_shot_silent_when_srt_starts_at_zero(self):
        result = pipeline.build_skeba_tagged_prompt(
            {"shots": [{"start": 0, "composition": "Wide room"}]},
            "[0.000s-0.800s] SPEAKER_01: Hello.", 5)
        first, second = result.split("[Shot 2: 0.1s]")
        self.assertNotIn("says,", first)
        self.assertIn("<character:speaker_01> says, <d>[English]Hello.</d>", second)

    def test_tagged_speaker_is_not_assigned_from_number_alone(self):
        analysis = {"subjects": [{"id": "C1", "description": "woman in blue"}],
                    "speakers": [{"id": "S1", "subject_id": "C1"}],
                    "dialogue": [{"time": 2.0, "speaker": "S1", "text": "Earlier line"}],
                    "shots": [{"start": 0, "composition": "C1 stands"}]}
        result = pipeline.build_skeba_tagged_prompt(
            analysis, "[8.000s-9.000s] SPEAKER_01: Later line.", 10)
        self.assertIn("<character:speaker_01> says", result)
        self.assertNotIn("<Subject 1> says", result)

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

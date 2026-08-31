import importlib.util
import sys
import types
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "h3_tag_references.py"
PACKAGE_NAME = "h3_prompt_test_package"


def _stub_module(name, **attributes):
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


package = _stub_module(PACKAGE_NAME, __path__=[])
_stub_module("numpy")
_stub_module("torch")
_stub_module("PIL", Image=object(), ImageOps=object())
model_management = _stub_module("comfy.model_management")
_stub_module("comfy", model_management=model_management)
_stub_module("comfy_extras", __path__=[])
_stub_module("comfy_extras.nodes_audio", load=lambda path: None)
_stub_module(
    f"{PACKAGE_NAME}.library",
    library_revision=lambda: 0,
    media_path=lambda record, kind: "",
    records_by_tag=lambda: {},
)

SPEC = importlib.util.spec_from_file_location(
    f"{PACKAGE_NAME}.h3_tag_references", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PromptResolutionTests(unittest.TestCase):
    def test_tags_are_replaced_in_place_without_subject_legends(self):
        records = {
            "living_room": {
                "image_file": "room.png",
                "audio_file": None,
                "image_description": "1990s apartment living room with a sofa and table",
                "audio_description": "",
            },
        }

        prompt, mapping, image_tags, audio_tags = MODULE.resolve_prompt(
            "[Shot 1] The camera pans across {living_room}.", records)

        self.assertEqual(
            prompt,
            "[Shot 1] The camera pans across <Picture 1> "
            "(1990s apartment living room with a sofa and table).",
        )
        self.assertNotIn("<Subject", prompt)
        self.assertEqual(
            mapping,
            "{living_room} -> <Picture 1> "
            "(1990s apartment living room with a sofa and table)",
        )
        self.assertEqual(image_tags, ["living_room"])
        self.assertEqual(audio_tags, [])

    def test_audio_only_tag_uses_audio_description(self):
        records = {
            "narrator": {
                "image_file": None,
                "audio_file": "voice.wav",
                "image_description": "",
                "audio_description": "a calm narrator voice",
            },
        }

        prompt, mapping, image_tags, audio_tags = MODULE.resolve_prompt(
            "{narrator} introduces the scene.", records)

        self.assertEqual(
            prompt,
            "<Audio 1> (a calm narrator voice) introduces the scene.",
        )
        self.assertEqual(
            mapping,
            "{narrator} -> <Audio 1> (a calm narrator voice)",
        )
        self.assertEqual(image_tags, [])
        self.assertEqual(audio_tags, ["narrator"])

    def test_repeated_tag_is_replaced_each_time_and_mapped_once(self):
        records = {
            "prop": {
                "image_file": "prop.png",
                "audio_file": None,
                "image_description": "a red rotary telephone",
                "audio_description": "",
            },
        }

        prompt, mapping, _, _ = MODULE.resolve_prompt(
            "{prop} sits beside {prop}.", records)

        self.assertEqual(
            prompt,
            "<Picture 1> (a red rotary telephone) sits beside "
            "<Picture 1> (a red rotary telephone).",
        )
        self.assertEqual(len(mapping.splitlines()), 1)

    def test_voice_tag_reports_audio_slot_and_description(self):
        records = {
            "anchor": {
                "image_file": "anchor.png",
                "audio_file": "anchor.wav",
                "image_description": "a news anchor in a dark suit",
                "audio_description": "a calm broadcast voice",
            },
        }

        prompt, mapping, image_tags, audio_tags = MODULE.resolve_prompt(
            "<d>[English §anchor§] Good evening.</d>", records)

        self.assertEqual(
            prompt,
            "<d>[English <Audio 1> (a calm broadcast voice)] Good evening.</d>",
        )
        self.assertEqual(
            mapping,
            "§anchor§ -> <Audio 1> (a calm broadcast voice)",
        )
        self.assertEqual(image_tags, [])
        self.assertEqual(audio_tags, ["anchor"])

    def test_voice_tag_supports_partial_or_empty_audio_data(self):
        cases = (
            ("file_only", "voice.wav", "", "<Audio 1>", ["file_only"]),
            ("description_only", None, "a soft whisper", "a soft whisper", []),
            ("empty", None, "", "empty", []),
        )
        for tag, audio_file, description, expected, expected_audio_tags in cases:
            with self.subTest(tag=tag):
                records = {
                    tag: {
                        "image_file": None,
                        "audio_file": audio_file,
                        "image_description": "",
                        "audio_description": description,
                    },
                }
                prompt, mapping, image_tags, audio_tags = MODULE.resolve_prompt(
                    f"[English §{tag}§]", records)

                self.assertEqual(prompt, f"[English {expected}]")
                self.assertEqual(mapping, f"§{tag}§ -> {expected}")
                self.assertEqual(image_tags, [])
                self.assertEqual(audio_tags, expected_audio_tags)

    def test_voice_tag_beyond_audio_limit_falls_back_to_description(self):
        records = {
            f"voice_{index}": {
                "image_file": None,
                "audio_file": f"voice_{index}.wav",
                "image_description": "",
                "audio_description": f"voice description {index}",
            }
            for index in range(1, 5)
        }

        prompt, mapping, _, audio_tags = MODULE.resolve_prompt(
            " ".join(f"§voice_{index}§" for index in range(1, 5)), records)

        self.assertEqual(
            prompt,
            "<Audio 1> (voice description 1) <Audio 2> (voice description 2) "
            "<Audio 3> (voice description 3) voice description 4",
        )
        self.assertIn("§voice_4§ -> voice description 4", mapping)
        self.assertEqual(audio_tags, ["voice_1", "voice_2", "voice_3"])

    def test_explicit_voice_tags_take_audio_slots_before_regular_references(self):
        records = {
            "paired": {
                "image_file": "paired.png",
                "audio_file": "paired.wav",
                "image_description": "a paired visual reference",
                "audio_description": "paired voice",
            },
            **{
                f"voice_{index}": {
                    "image_file": None,
                    "audio_file": f"voice_{index}.wav",
                    "image_description": "",
                    "audio_description": f"explicit voice {index}",
                }
                for index in range(1, 4)
            },
        }

        prompt, _, image_tags, audio_tags = MODULE.resolve_prompt(
            "{paired} §voice_1§ §voice_2§ §voice_3§", records)

        self.assertEqual(image_tags, ["paired"])
        self.assertEqual(audio_tags, ["voice_1", "voice_2", "voice_3"])
        self.assertEqual(
            prompt,
            "<Picture 1> (a paired visual reference) <Audio 1> (explicit voice 1) "
            "<Audio 2> (explicit voice 2) <Audio 3> (explicit voice 3)",
        )

    def test_paired_reference_mapping_reports_only_picture_slot(self):
        records = {
            "performer": {
                "image_file": "performer.png",
                "audio_file": "performer.wav",
                "image_description": "the performer on stage",
                "audio_description": "an energetic speaking voice",
            },
        }

        prompt, mapping, image_tags, audio_tags = MODULE.resolve_prompt(
            "{performer} addresses the audience.", records)

        self.assertEqual(
            prompt,
            "<Picture 1> (the performer on stage) addresses the audience.",
        )
        self.assertEqual(
            mapping,
            "{performer} -> <Picture 1> (the performer on stage)",
        )
        self.assertEqual(image_tags, ["performer"])
        self.assertEqual(audio_tags, ["performer"])

    def test_picture_markers_follow_actual_output_slot_order(self):
        records = {
            "first_frame": {
                "image_file": "frame.png",
                "audio_file": None,
                "image_description": "[Shot 1] first frame",
                "audio_description": "",
            },
            "performer": {
                "image_file": "performer.png",
                "audio_file": "performer.wav",
                "image_description": "the performer",
                "audio_description": "the performer's voice",
            },
        }

        prompt, mapping, image_tags, audio_tags = MODULE.resolve_prompt(
            "{first_frame}: fully_preserved. {performer} enters with §performer§.",
            records,
        )

        self.assertEqual(
            prompt,
            "<Picture 2> ([Shot 1] first frame): fully_preserved. "
            "<Picture 1> (the performer) enters with "
            "<Audio 1> (the performer's voice).",
        )
        self.assertIn(
            "{first_frame} -> <Picture 2> ([Shot 1] first frame)", mapping)
        self.assertIn(
            "{performer} -> <Picture 1> (the performer)",
            mapping,
        )
        self.assertIn(
            "§performer§ -> <Audio 1> (the performer's voice)", mapping)
        self.assertEqual(image_tags, ["performer", "first_frame"])
        self.assertEqual(audio_tags, ["performer"])

    def test_unknown_voice_tag_is_clear(self):
        with self.assertRaisesRegex(ValueError, "§missing_voice§"):
            MODULE.resolve_prompt("§missing_voice§ speaks.", {})


if __name__ == "__main__":
    unittest.main()

import importlib.util
import sys
import types
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "h3_tag_references.py"
PACKAGE_NAME = "h3_prompt_test_package"
RESTORE_MODULES = (
    "numpy", "torch", "PIL", "comfy", "comfy.model_management",
    "comfy_api", "comfy_api.latest", "comfy_extras",
    "comfy_extras.nodes_audio",
)
PREVIOUS_MODULES = {name: sys.modules.get(name) for name in RESTORE_MODULES}


def _stub_module(name, **attributes):
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


package = _stub_module(PACKAGE_NAME, __path__=[str(MODULE_PATH.parent)])
_stub_module("numpy")
_stub_module("torch")
_stub_module("PIL", Image=object(), ImageOps=object())
model_management = _stub_module("comfy.model_management")
_stub_module("comfy", model_management=model_management)
input_impl = types.SimpleNamespace(VideoFromFile=lambda path: None)
_stub_module("comfy_api", __path__=[])
_stub_module("comfy_api.latest", InputImpl=input_impl)
_stub_module("comfy_extras", __path__=[])
_stub_module("comfy_extras.nodes_audio", load=lambda path: None)
_stub_module(
    f"{PACKAGE_NAME}.library",
    library_revision=lambda: 0,
    media_path=lambda record, kind: "",
    records_by_tag=lambda: {},
)
_stub_module(
    f"{PACKAGE_NAME}.built_in_references",
    built_in_images_revision=lambda: 0,
    catalog_revision=lambda: "0",
    library_built_in_records=lambda: {},
)

_stub_module(f"{PACKAGE_NAME}.refmod_support", build_mods=lambda bundle: [])
_stub_module(f"{PACKAGE_NAME}.refmod_library", project_records=lambda records, prompt: records, revision=lambda: "0")

SPEC = importlib.util.spec_from_file_location(
    f"{PACKAGE_NAME}.h3_tag_references", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
for module_name, previous in PREVIOUS_MODULES.items():
    if previous is None:
        sys.modules.pop(module_name, None)
    else:
        sys.modules[module_name] = previous


class PromptResolutionTests(unittest.TestCase):
    def test_built_in_attached_voice_resolves_with_or_without_image(self):
        for image in (None, "face.png"):
            records = {"Actor_BC": {
                "built_in": True, "image_file": image, "audio_file": "voice.wav",
                "image_description": "the character", "audio_description": "the character voice",
            }}
            prompt, _, image_tags, audio_tags, _ = MODULE.resolve_prompt(
                "{Actor_BC} speaks with \u00a7Actor_BC\u00a7", records)
            self.assertEqual(audio_tags, ["Actor_BC"])
            self.assertEqual(image_tags, ["Actor_BC"] if image else [])
            self.assertIn("<Audio 1>", prompt)

    def test_built_in_attachment_claims_a_picture_slot(self):
        records = {
            "Abby Sciuto_BC": {
                "built_in": True,
                "image_file": "abby.png",
                "audio_file": None,
                "video_file": None,
                "image_description": "Abby Sciuto played by Pauley Perrette featured on NCIS",
                "audio_description": "in Abby Sciuto's voice as played by Pauley Perrette",
            },
        }

        prompt, _mapping, image_tags, audio_tags, video_tags = MODULE.resolve_prompt(
            "{Abby Sciuto_BC} enters.", records)

        self.assertEqual(
            prompt,
            "<Picture 1> (Abby Sciuto played by Pauley Perrette featured on NCIS) enters.",
        )
        self.assertEqual((image_tags, audio_tags, video_tags), (["Abby Sciuto_BC"], [], []))

    def test_namespaced_built_in_character_and_voice_tags(self):
        records = {
            "Abby Sciuto_BC": {
                "built_in": True,
                "image_file": None,
                "audio_file": None,
                "video_file": None,
                "image_description": (
                    "Abby Sciuto played by Pauley Perrette featured on NCIS"
                ),
                "audio_description": (
                    "in Abby Sciuto's voice as played by Pauley Perrette"
                ),
            },
        }

        prompt, mapping, image_tags, audio_tags, video_tags = MODULE.resolve_prompt(
            "{Abby Sciuto_BC} says <d>[English §Abby Sciuto_BC§] Hi.</d>",
            records,
        )

        self.assertEqual(
            prompt,
            "Abby Sciuto played by Pauley Perrette featured on NCIS says "
            "<d>[English in Abby Sciuto's voice as played by Pauley Perrette] Hi.</d>",
        )
        self.assertIn("{Abby Sciuto_BC} -> Abby Sciuto played by", mapping)
        self.assertIn("§Abby Sciuto_BC§ -> in Abby Sciuto's voice", mapping)
        self.assertEqual((image_tags, audio_tags, video_tags), ([], [], []))

    def test_tags_are_replaced_in_place_without_subject_legends(self):
        records = {
            "living_room": {
                "image_file": "room.png",
                "audio_file": None,
                "image_description": "1990s apartment living room with a sofa and table",
                "audio_description": "",
            },
        }

        prompt, mapping, image_tags, audio_tags, video_tags = MODULE.resolve_prompt(
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
        self.assertEqual(video_tags, [])

    def test_audio_only_tag_uses_audio_description(self):
        records = {
            "narrator": {
                "image_file": None,
                "audio_file": "voice.wav",
                "image_description": "",
                "audio_description": "a calm narrator voice",
            },
        }

        prompt, mapping, image_tags, audio_tags, video_tags = MODULE.resolve_prompt(
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
        self.assertEqual(video_tags, [])

    def test_repeated_tag_is_replaced_each_time_and_mapped_once(self):
        records = {
            "prop": {
                "image_file": "prop.png",
                "audio_file": None,
                "image_description": "a red rotary telephone",
                "audio_description": "",
            },
        }

        prompt, mapping, _, _, _ = MODULE.resolve_prompt(
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

        prompt, mapping, image_tags, audio_tags, video_tags = MODULE.resolve_prompt(
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
        self.assertEqual(video_tags, [])

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
                prompt, mapping, image_tags, audio_tags, video_tags = MODULE.resolve_prompt(
                    f"[English §{tag}§]", records)

                self.assertEqual(prompt, f"[English {expected}]")
                self.assertEqual(mapping, f"§{tag}§ -> {expected}")
                self.assertEqual(image_tags, [])
                self.assertEqual(audio_tags, expected_audio_tags)
                self.assertEqual(video_tags, [])

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

        prompt, mapping, _, audio_tags, _ = MODULE.resolve_prompt(
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

        prompt, _, image_tags, audio_tags, video_tags = MODULE.resolve_prompt(
            "{paired} §voice_1§ §voice_2§ §voice_3§", records)

        self.assertEqual(image_tags, ["paired"])
        self.assertEqual(audio_tags, ["voice_1", "voice_2", "voice_3"])
        self.assertEqual(video_tags, [])
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

        prompt, mapping, image_tags, audio_tags, video_tags = MODULE.resolve_prompt(
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
        self.assertEqual(video_tags, [])

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

        prompt, mapping, image_tags, audio_tags, video_tags = MODULE.resolve_prompt(
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
        self.assertEqual(video_tags, [])

    def test_video_reference_uses_video_slot_and_offsets_standalone_audio(self):
        records = {
            "performance": {
                "video_file": "performance.mp4",
                "video_has_audio": True,
                "video_description": "a singer performing on stage",
                "image_file": None,
                "audio_file": None,
                "audio_description": "the singer's live voice",
            },
            "narrator": {
                "video_file": None,
                "image_file": None,
                "audio_file": "narrator.wav",
                "audio_description": "a calm narrator",
            },
        }

        prompt, mapping, image_tags, audio_tags, video_tags = MODULE.resolve_prompt(
            "{performance} then §performance§ and §narrator§.", records)

        self.assertEqual(
            prompt,
            "<Video 1> (a singer performing on stage) then "
            "<Audio 1> (the singer's live voice) and "
            "<Audio 2> (a calm narrator).",
        )
        self.assertIn("{performance} -> <Video 1>", mapping)
        self.assertEqual(image_tags, [])
        self.assertEqual(audio_tags, ["narrator"])
        self.assertEqual(video_tags, ["performance"])

    def test_silent_video_is_valid_and_voice_only_video_audio_can_be_standalone(self):
        silent = {
            "silent": {
                "video_file": "silent.mp4",
                "video_has_audio": False,
                "video_description": "a silent camera move",
                "image_file": None,
                "audio_file": None,
                "audio_description": "",
            },
        }
        prompt, _, _, audio_tags, video_tags = MODULE.resolve_prompt(
            "Use {silent}.", silent)
        self.assertEqual(prompt, "Use <Video 1> (a silent camera move).")
        self.assertEqual(audio_tags, [])
        self.assertEqual(video_tags, ["silent"])

        voiced = {
            "clip": {
                "video_file": "clip.mp4",
                "video_has_audio": True,
                "video_description": "",
                "image_file": None,
                "audio_file": None,
                "audio_description": "dialogue from the clip",
            },
        }
        prompt, _, _, audio_tags, video_tags = MODULE.resolve_prompt(
            "[English §clip§]", voiced)
        self.assertEqual(prompt, "[English <Audio 1> (dialogue from the clip)]")
        self.assertEqual(audio_tags, ["clip"])
        self.assertEqual(video_tags, [])

    def test_video_limit_and_socket_order(self):
        records = {
            f"clip_{index}": {
                "video_file": f"clip_{index}.mp4",
                "video_has_audio": False,
            }
            for index in range(1, 5)
        }
        with self.assertRaisesRegex(ValueError, "at most 3 reference videos"):
            MODULE.resolve_prompt(" ".join(f"{{clip_{i}}}" for i in range(1, 5)), records)

        names = MODULE.H3TaggedReferencePrompt.RETURN_NAMES
        video_fps = MODULE.H3TaggedReferencePrompt.INPUT_TYPES()["required"]["video_fps"]
        self.assertEqual(video_fps[0], "FLOAT")
        self.assertEqual(video_fps[1]["default"], 24.0)
        video_max_side = MODULE.H3TaggedReferencePrompt.INPUT_TYPES()["required"]["video_max_side"]
        self.assertEqual(video_max_side[0], "INT")
        self.assertEqual(video_max_side[1]["default"], 1536)
        self.assertEqual(names[0:2], ("prompt", "mapping"))
        self.assertEqual(names[2:11], tuple(f"image_{i}" for i in range(1, 10)))
        self.assertEqual(names[11:14], ("audio_1", "audio_2", "audio_3"))
        self.assertEqual(names[14:17], ("video_1", "video_2", "video_3"))
        self.assertEqual(names[17:20], ("video_audio_1", "video_audio_2", "video_audio_3"))
        self.assertEqual(names[20], "reference_bundle")

    def test_build_emits_video_frames_and_slot_aligned_embedded_audio(self):
        records = {
            "voiced": {
                "video_file": "voiced.mp4",
                "video_has_audio": True,
                "video_description": "a voiced clip",
                "image_file": None,
                "audio_file": None,
            },
            "silent": {
                "video_file": "silent.mp4",
                "video_has_audio": False,
                "video_description": "a silent clip",
                "image_file": None,
                "audio_file": None,
            },
        }
        original_records = MODULE.records_by_tag
        original_media_path = MODULE.media_path
        original_load_video = MODULE.load_video
        try:
            MODULE.records_by_tag = lambda: records
            MODULE.media_path = lambda record, kind: record[f"{kind}_file"]
            MODULE.load_video = lambda path, fps=24, max_side=1536: (
                f"frames:{path}@{fps}",
                f"audio:{path}" if path == "voiced.mp4" else None,
            )
            output = MODULE.H3TaggedReferencePrompt().build(
                "{voiced} {silent}", video_fps=29.97)
        finally:
            MODULE.records_by_tag = original_records
            MODULE.media_path = original_media_path
            MODULE.load_video = original_load_video

        self.assertEqual(output[14:17], (
            "frames:voiced.mp4@29.97", "frames:silent.mp4@29.97", None))
        self.assertEqual(output[17:20], ("audio:voiced.mp4", None, None))
        self.assertEqual(
            [entry["tag"] for entry in output[20]["videos"]],
            ["voiced", "silent"],
        )
        self.assertEqual(output[20]["video_max_side"], 1536)

    def test_video_max_side_only_shrinks_larger_media(self):
        self.assertEqual(MODULE.normalized_video_dimensions(1280, 720, 1536), (1280, 720))
        self.assertEqual(MODULE.normalized_video_dimensions(3840, 2160, 1536), (1536, 864))
        self.assertEqual(MODULE.normalized_video_dimensions(2160, 3840, 1536), (864, 1536))
        self.assertEqual(MODULE.normalized_video_dimensions(3840, 2160, 0), (3840, 2160))

    def test_bundle_only_mode_does_not_decode_reference_media(self):
        records = {
            "clip": {
                "id": "clip-id",
                "video_file": "clip.mp4",
                "video_has_audio": True,
                "video_description": "a reference clip",
                "image_file": None,
                "audio_file": None,
            },
        }
        original_records = MODULE.records_by_tag
        original_media_path = MODULE.media_path
        original_load_video = MODULE.load_video
        try:
            MODULE.records_by_tag = lambda: records
            MODULE.media_path = lambda record, kind: record[f"{kind}_file"]
            MODULE.load_video = lambda *args, **kwargs: self.fail(
                "bundle-only mode decoded the video")
            output = MODULE.H3TaggedReferencePrompt().build(
                "{clip}", defer_media_loading=True)
        finally:
            MODULE.records_by_tag = original_records
            MODULE.media_path = original_media_path
            MODULE.load_video = original_load_video

        self.assertEqual(output[14:20], (None, None, None, None, None, None))
        self.assertTrue(output[20]["media_deferred"])
        self.assertTrue(output[20]["videos"][0]["has_audio"])

    def test_compiler_media_outputs_match_mapping_and_deferred_bundle(self):
        from unittest.mock import patch
        import json
        records = {
            "plain": dict(reference_type="character", name="Plain", image_file="plain.png"),
            "hero": dict(reference_type="character", name="Hero", image_file="hero.png", audio_file="hero.wav"),
            "clip": dict(reference_type="video", video_file="clip.mp4", video_has_audio=True),
        }
        source = "subject_definitions:\n{plain}\n{hero}\n\nsummary:\n{hero} moves.\n\nretention_analysis:\nKeep clothing.\n\ndetailed_description:\n{hero} says \u00a7hero\u00a7, <d>[English]Go!</d> Follow {clip}.\n\noverall_soundscape:\nReference the wind from \u00a7clip\u00a7.\n\nnon_diegetic_music:\nN/A"
        with patch.object(MODULE, "records_by_tag", return_value=records), \
             patch.object(MODULE, "library_built_in_records", return_value={}), \
             patch.object(MODULE, "media_path", side_effect=lambda r,k:r[k+"_file"]), \
             patch.object(MODULE, "load_image", side_effect=lambda p:p), \
             patch.object(MODULE, "load_audio", side_effect=lambda p:p), \
             patch.object(MODULE, "load_video", return_value=("frames", "soundtrack")):
            node = MODULE.H3TaggedReferencePrompt()
            output = node.build(source, auto_crop_voice_references=False, compiler_mode="deterministic")
            deferred = node.build(source, auto_crop_voice_references=False, compiler_mode="deterministic", defer_media_loading=True)
            isolation_off = node.build(source, auto_crop_voice_references=False, compiler_mode="deterministic", defer_media_loading=True,
                                       compiler_voice_isolation=False)
        mapping = json.loads(output[1])
        self.assertEqual(output[2:4], ("hero.png", "plain.png"))
        self.assertEqual(output[11], "hero.wav")
        self.assertEqual(output[14], "frames")
        self.assertEqual(output[17], "soundtrack")
        self.assertEqual(mapping["resources"]["saved:hero"]["picture"], 1)
        self.assertEqual(mapping["resources"]["saved:hero"]["audio"], 2)
        self.assertEqual(mapping["resources"]["saved:clip"]["audio"], 1)
        self.assertTrue(mapping["resources"]["saved:clip"]["audio_used"])
        self.assertIn("Reference the wind from <Audio 1>.", output[0])
        self.assertEqual(output[:2], deferred[:2])
        for kind in ("images", "audios", "videos"):
            self.assertEqual(output[20][kind], deferred[20][kind])
        self.assertTrue(all(v is None for v in deferred[2:20]))
        self.assertIn("is the only speaker using <Audio 2>", deferred[0])
        self.assertNotIn("is the only speaker using", isolation_off[0])
        self.assertEqual(deferred[20], isolation_off[20])
        self.assertNotEqual(node.IS_CHANGED(source, compiler_voice_isolation=True),
                            node.IS_CHANGED(source, compiler_voice_isolation=False))

    def test_large_cast_loads_only_requested_voice_in_outputs_and_bundle(self):
        from unittest.mock import patch
        import json
        records = {name: dict(reference_type="character", name=name, image_file=name+".png", audio_file=name+".wav")
                   for name in ("a", "b", "c", "d")}
        source = "subject_definitions:\n{a}\n{b}\n{c}\n{d}\nsummary:\n{d} speaks.\nretention_analysis:\nN/A\ndetailed_description:\n{d} says \u00a7d\u00a7, <d>[English]Hello.</d>\noverall_soundscape:\nRoom tone.\nnon_diegetic_music:\nN/A"
        with patch.object(MODULE, "records_by_tag", side_effect=lambda:dict(records)), \
             patch.object(MODULE, "library_built_in_records", return_value={}), \
             patch.object(MODULE, "media_path", side_effect=lambda r,k:r[k+"_file"]), \
             patch.object(MODULE, "load_image", side_effect=lambda p:p), \
             patch.object(MODULE, "load_audio", return_value="speaker audio") as load:
            node = MODULE.H3TaggedReferencePrompt()
            result = node.build(source, auto_crop_voice_references=False, compiler_mode="deterministic")
            deferred = node.build(source, auto_crop_voice_references=False, compiler_mode="deterministic", defer_media_loading=True)
        load.assert_called_once_with("d.wav")
        self.assertEqual(result[2:6], ("d.png", "a.png", "b.png", "c.png"))
        self.assertEqual(result[11:14], ("speaker audio", None, None))
        self.assertEqual(result[20]["audios"], deferred[20]["audios"])
        self.assertEqual([a["tag"] for a in deferred[20]["audios"]], ["d"])
        self.assertEqual(json.loads(result[1])["audio"], {"1":"saved:d"})
        self.assertEqual(result[:2], deferred[:2])

    def test_speaking_order_reorders_real_media_and_deferred_bundle_together(self):
        from unittest.mock import patch
        import json
        records = {name: dict(reference_type="character", name=name,
                             image_file=name+".png", audio_file=name+".wav")
                   for name in ("george", "jerry", "silent")}
        headings = ("subject_definitions", "summary", "retention_analysis", "detailed_description",
                    "overall_soundscape", "non_diegetic_music")
        for first, second in (("jerry", "george"), ("george", "jerry")):
            with self.subTest(first=first):
                detail = (f"{{{first}}} says \u00a7{first}\u00a7, <d>[English]First.</d>\n"
                          f"{{{second}}} replies \u00a7{second}\u00a7, <d>[English]Second.</d>\n"
                          f"{{{first}}} says \u00a7{first}\u00a7, <d>[English]Third.</d>")
                sections = ("{george}\n{silent}\n{jerry}", "", "N/A", detail, "Room tone.", "N/A")
                source = "\n\n".join(f"{h}:\n{s}" for h,s in zip(headings,sections))
                with patch.object(MODULE, "records_by_tag", side_effect=lambda:dict(records)), \
                     patch.object(MODULE, "library_built_in_records", return_value={}), \
                     patch.object(MODULE, "media_path", side_effect=lambda r,k:r[k+"_file"]), \
                     patch.object(MODULE, "load_image", side_effect=lambda p:p), \
                     patch.object(MODULE, "load_audio", side_effect=lambda p:p):
                    node = MODULE.H3TaggedReferencePrompt()
                    output = node.build(source, auto_crop_voice_references=False, compiler_mode="deterministic")
                    deferred = node.build(source, auto_crop_voice_references=False, compiler_mode="deterministic", defer_media_loading=True)
                mapping = json.loads(output[1])
                self.assertEqual(output[2:5], (first+".png", second+".png", "silent.png"))
                self.assertEqual(output[11:14], (first+".wav", second+".wav", None))
                self.assertEqual(output[:2], deferred[:2])
                for kind in ("images", "audios", "videos"):
                    self.assertEqual(output[20][kind], deferred[20][kind])
                self.assertEqual([r["tag"] for r in deferred[20]["images"]], [first, second, "silent"])
                self.assertEqual([r["tag"] for r in deferred[20]["audios"]], [first, second])
                for slot, name in enumerate((first, second), 1):
                    resource = mapping["resources"]["saved:"+name]
                    self.assertEqual([resource[k] for k in ("subject", "speaker", "picture", "audio")], [slot]*4)
                    self.assertIn(f"<Subject {slot}> is {name} in <Picture {slot}>", output[0])
                    self.assertIn(f"<Audio {slot}> is the voice-timbre reference for <Subject {slot}> (S{slot})", output[0])
                self.assertEqual(mapping["resources"]["saved:silent"]["subject"], 3)
                self.assertIsNone(mapping["resources"]["saved:silent"]["speaker"])
                self.assertIsNone(mapping["resources"]["saved:silent"]["audio"])
                self.assertIn("<Subject 1> (S1) says using the recognizable voice timbre referenced from <Audio 1>, <d>[English]Third.</d>", output[0])

    def test_unknown_voice_tag_is_clear(self):
        with self.assertRaisesRegex(ValueError, "§missing_voice§"):
            MODULE.resolve_prompt("§missing_voice§ speaks.", {})


class PromptListValidatorTests(unittest.TestCase):
    def test_inline_subject_and_duration_in_list(self):
        source = "[new_location] [s=15]\nsubject_definitions:\n<object:coffee_cup = A white porcelain cup.>\ndetailed_description:\ntimeline:\n[Shot 1] A view of <object:coffee_cup>.\noverall_soundscape:\nRoom tone.\nnon_diegetic_music:\nN/A"
        result = MODULE.H3PromptListValidator().validate_list(source + "|" + source.replace("[new_location] [s=15]", ""))
        self.assertIn("Validated all 2 prompts", result[3])
        self.assertIn("[s=15]", result[0])

    def test_digit_leading_location_in_prompt_three(self):
        source = "<location:1920s_street = A street in the 1920s.>\nsubject_definitions:\n<location:1920s_street>\ndetailed_description:\ntimeline:\n[Shot 1] At 00:00.000, a view of <location:1920s_street>.\noverall_soundscape:\nTraffic.\nnon_diegetic_music:\nN/A"
        result = MODULE.H3PromptListValidator().validate_list("|".join([self.prompt(), self.prompt(), source]))
        self.assertIn("Validated all 3 prompts", result[3])

    def test_eight_prompts_without_retention_accept_header_voices(self):
        from unittest.mock import patch
        import json
        records = {"George Costanza_BC":dict(reference_type="character", built_in=True,
                                             name="George Costanza", audio_file="george.wav")}
        source = "subject_definitions:\n{George Costanza_BC}\ndetailed_description:\n[Shot 2] At 00:03.000, {George Costanza_BC} says, <d>[English \u00a7George Costanza_BC\u00a7]They did? Because I can be more intimidating.</d>\noverall_soundscape:\nRoom tone.\nnon_diegetic_music:\nN/A"
        with patch.object(MODULE,"records_by_tag",return_value=records), \
             patch.object(MODULE,"library_built_in_records",return_value={}), \
             patch.object(MODULE,"media_path",return_value="george.wav"), \
             patch.object(MODULE,"load_audio",side_effect=AssertionError("must not load media")):
            validation = MODULE.H3PromptListValidator().validate_list("|".join([source]*8))
            output = MODULE.H3TaggedReferencePrompt().build(source,compiler_mode=validation[1],defer_media_loading=True)
        self.assertIn("Validated all 8 prompts",validation[3])
        self.assertNotIn("retention_analysis:",output[0])
        self.assertIn("<d>[English <Audio 1>]They did? Because I can be more intimidating.</d>",output[0])
        self.assertEqual(output[20]["audios"][0]["tag"],"George Costanza_BC")
        self.assertEqual(output[20]["audios"][0]["max_duration_seconds"],15)
        self.assertEqual(json.loads(output[1])["speakers"],{"1":"saved:George Costanza_BC"})

    @staticmethod
    def prompt():
        return "<character:guest = A guest.>\nsubject_definitions:\n<character:guest>\nsummary:\nA guest arrives.\nretention_analysis:\n<character:guest>: fully_preserved - retain appearance.\ndetailed_description:\n<character:guest> says in a cheerful voice, <d>[English]Hello.</d>\noverall_soundscape:\nRoom tone.\nnon_diegetic_music:\nN/A"

    def test_passes_original_list_and_compatible_mode_after_all_prompts_compile(self):
        from unittest.mock import patch
        source = "  " + self.prompt() + "\n|\n\n|\n" + self.prompt() + "\n|  "
        with patch.object(MODULE, "compile_prompt", wraps=MODULE.compile_prompt) as compile_spy:
            result = MODULE.H3PromptListValidator().validate_list(source)
        self.assertEqual(compile_spy.call_count, 2)
        self.assertEqual(result[:3], (source, "deterministic", True))
        self.assertIn("Validated all 2 prompts", result[3])
        self.assertEqual(MODULE.H3PromptListValidator.RETURN_TYPES[1],
                         MODULE.H3TaggedReferencePrompt.INPUT_TYPES()["optional"]["compiler_mode"][0])

    def test_collects_late_errors_before_releasing_any_list(self):
        from unittest.mock import patch
        source = "|".join((self.prompt(), "bad second", self.prompt(), "bad fourth"))
        with patch.object(MODULE, "compile_prompt", wraps=MODULE.compile_prompt) as compile_spy:
            with self.assertRaises(ValueError) as error:
                MODULE.H3PromptListValidator().validate_list(source)
        self.assertEqual(compile_spy.call_count, 4)
        self.assertIn("2 of 4 prompts", str(error.exception))
        self.assertIn("Prompt 2: INVALID_SECTION", str(error.exception))
        self.assertIn("Prompt 4: INVALID_SECTION", str(error.exception))

    def test_temporary_registry_resets_for_each_prompt(self):
        undeclared = self.prompt().split("\n", 1)[1]
        with self.assertRaisesRegex(ValueError, "Prompt 2: UNKNOWN_TEMPORARY_RESOURCE"):
            MODULE.H3PromptListValidator().validate_list(self.prompt()+"|"+undeclared)

    def test_disabled_skips_compiler_and_library_and_outputs_legacy(self):
        from unittest.mock import patch
        with patch.object(MODULE, "compile_prompt", side_effect=AssertionError("must not compile")), \
             patch.object(MODULE, "records_by_tag", side_effect=AssertionError("must not load library")), \
             patch.object(MODULE, "library_revision", side_effect=AssertionError("must not inspect library")):
            result = MODULE.H3PromptListValidator().validate_list("broken | prompt", validation_enabled=False, delimiter="")
            MODULE.H3PromptListValidator.IS_CHANGED(validation_enabled=False)
        self.assertEqual(result[:3], ("broken | prompt", "legacy", False))

    def test_delimiters_empty_parts_and_warnings_match_loop_behavior(self):
        source = self.prompt()+"\n---\n"+self.prompt()
        result = MODULE.H3PromptListValidator().validate_list(source, delimiter="\n---\n")
        self.assertIn("Validated all 2 prompts", result[3])
        with self.assertRaisesRegex(ValueError, "Prompt 2: INVALID_SECTION"):
            MODULE.H3PromptListValidator().validate_list(self.prompt()+"|", skip_empty=False)
        with self.assertRaisesRegex(ValueError, "no prompts"):
            MODULE.H3PromptListValidator().validate_list(" | ")
        with self.assertRaisesRegex(ValueError, "delimiter must not be empty"):
            MODULE.H3PromptListValidator().validate_list(source, delimiter="")
        result = MODULE.H3PromptListValidator().validate_list(self.prompt().replace("<character:guest>: fully_preserved - retain appearance.", "N/A"))
        self.assertNotIn("MISSING_RETENTION_ENTRY", result[3])
        self.assertEqual(result[1], "deterministic")

    def test_compiler_options_and_library_revision_are_used_without_decoding(self):
        from unittest.mock import patch
        records = {"clip": dict(reference_type="video", video_file="clip.mp4", video_has_audio=True)}
        source = "subject_definitions:\nsummary:\nFollow {clip}.\nretention_analysis:\n{clip}: partially_preserved - edit color.\ndetailed_description:\nFollow {clip}.\noverall_soundscape:\nReference the ambience from \u00a7clip\u00a7.\nnon_diegetic_music:\nN/A"
        with patch.object(MODULE, "records_by_tag", return_value=records), \
             patch.object(MODULE, "compile_prompt", wraps=MODULE.compile_prompt) as compile_spy, \
             patch.object(MODULE, "load_video", side_effect=AssertionError("must not decode")):
            result = MODULE.H3PromptListValidator().validate_list(source, compiler_video_usage="editing", compiler_audio_usage="reuse", compiler_voice_isolation=False)
        self.assertEqual(result[1], "deterministic")
        self.assertEqual(compile_spy.call_args.kwargs["video_usage"], "editing")
        self.assertEqual(compile_spy.call_args.kwargs["audio_usage"], "reuse")
        self.assertFalse(compile_spy.call_args.kwargs["voice_isolation"])
        with patch.object(MODULE, "library_revision", side_effect=[1,2]):
            first = MODULE.H3PromptListValidator.IS_CHANGED()
            second = MODULE.H3PromptListValidator.IS_CHANGED()
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()

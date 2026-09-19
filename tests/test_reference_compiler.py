import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("reference_compiler_test", ROOT / "reference_compiler.py")
compiler = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = compiler
spec.loader.exec_module(compiler)


def prompt(definitions, detail="", summary="", retention="", sound="", music="N/A", declarations=""):
    values = (definitions, summary, retention, detail, sound, music)
    return declarations + "\n" + "\n\n".join(f"{s}:\n{v}" for s, v in zip(compiler.SECTIONS, values))


def character(image=None, audio=None, **values):
    return dict(reference_type="character", name="Binary Thott", image_file=image, audio_file=audio,
                image_description="A young man with black dreadlocks.", audio_description="Young male voice, relaxed cadence.", **values)


class CompilerTests(unittest.TestCase):
    def test_inline_definitions_and_duration_marker(self):
        defs = "<character:guest = A guest.>\n<voice:guest = A warm voice.>\n<object:coffee_cup = A white porcelain cup.>"
        detail = "<character:guest> holds <object:coffee_cup> and says, <d>[English <voice:guest>]Hello.</d>"
        for marker in ("", "[s=15]", "[new_location] [s=12.5]", "[s=15] [new_location]"):
            result = compiler.compile_prompt(marker + "\n" + prompt(defs, detail), {})
            self.assertIn("is A white porcelain cup.", result.prompt)
            self.assertIn("<d>[English A warm voice.]Hello.</d>", result.prompt)
            if marker:
                self.assertTrue(result.prompt.startswith(marker))
        with self.assertRaisesRegex(ValueError, "DUPLICATE_TEMPORARY_DECLARATION"):
            compiler.compile_prompt(prompt(defs, declarations="<object:coffee_cup = Another cup.>"), {})
        with self.assertRaisesRegex(ValueError, "MISSING_TEMPORARY_DESCRIPTION"):
            compiler.compile_prompt(prompt("<object:cup = >"), {})

    def test_timeline_subheading_stays_inside_detail(self):
        source = prompt("{hero}", "Sitcom presentation.\n\ntimeline:\n\n[Shot 1] At 00:00.000, {hero} says, <d>[English \u00a7hero\u00a7]Hello.</d>")
        result = compiler.compile_prompt(source, {"hero":character(audio="hero.wav")})
        self.assertIn("Sitcom presentation.\n\ntimeline:\n\n[Shot 1]", result.prompt)
        self.assertIn("<d>[English <Audio 1>]Hello.</d>", result.prompt)
        self.assertEqual(result.audios, ["hero"])
        for invalid in (source.replace("timeline:", "timline:"), source.replace("subject_definitions:", "timeline:\nsubject_definitions:")):
            with self.assertRaisesRegex(ValueError, "INVALID_SECTION"):
                compiler.compile_prompt(invalid, {"hero":character()})

    def test_flexible_temporary_names(self):
        for name in ("1920s_street", "123", "café entrance", "東京-通り", "guest #2", "O'Brien", "voice.v2", "_guest"):
            source = prompt(f"<character:{name}>",
                            f"<character:{name}> says, <d>[English <voice:{name}>]Hello.</d>",
                            declarations=f"<character:{name} = A guest.>\n<voice:{name} = A warm voice.>")
            result = compiler.compile_prompt(source, {})
            self.assertIn("<d>[English A warm voice.]Hello.</d>", result.prompt)
            self.assertEqual(result.debug["speakers"], {"1":f"temporary:character:{name}"})
        for name in ("", "bad|name", "bad[name]", "bad{name}", "bad\nname"):
            with self.assertRaisesRegex(ValueError, "INVALID_TEMPORARY_NAME"):
                compiler.compile_prompt(prompt("", declarations=f"<object:{name} = Thing.>"), {})

    def test_optional_summary_and_retention_combinations(self):
        for keep_summary in (False, True):
            for keep_retention in (False, True):
                source = prompt("", "Follow {clip}.", summary="Keep framing.", retention="Keep color.")
                if not keep_summary:
                    source = source.replace("summary:\nKeep framing.\n\n", "")
                if not keep_retention:
                    source = source.replace("retention_analysis:\nKeep color.\n\n", "")
                result = compiler.compile_prompt(source, {"clip": dict(reference_type="video", video_file="clip.mp4")}, video_usage="editing")
                self.assertEqual("summary:" in result.prompt, keep_summary)
                self.assertEqual("retention_analysis:" in result.prompt, keep_retention)
                self.assertIn("The target video is an edited version of <Video 1>.", result.prompt)
                if not keep_summary:
                    self.assertIn("detailed_description:\n\nThe target video", result.prompt)
        for source in ("subject_definitions:\ndetailed_description:\nnon_diegetic_music:\nN/A",
                       "subject_definitions:\nsummary:\nsummary:\ndetailed_description:\noverall_soundscape:\nnon_diegetic_music:\nN/A"):
            with self.assertRaisesRegex(ValueError, "INVALID_SECTION"):
                compiler.compile_prompt(source, {})

    def test_five_sections_and_language_header_voice_preserve_entire_line(self):
        records = {"Jerry Seinfeld_BC": character("jerry.png", "jerry.wav"),
                   "George Costanza_BC": character("george.png", "george.wav")}
        detail = ("[Shot 2] At 00:03.000, a medium shot shows only {George Costanza_BC} clutching his mysterious folder. "
                  "{George Costanza_BC} says, <d>[English \u00a7George Costanza_BC\u00a7]They did? Because I can be more intimidating.</d>\n"
                  "[Shot 3] At 00:07.000, {Jerry Seinfeld_BC} reacts: <d>[English \u00a7Jerry Seinfeld_BC\u00a7]My refrigerator doesn't move. It barely refrigerates.</d>\n"
                  "{George Costanza_BC} continues, <d>[English \u00a7George Costanza_BC\u00a7]Fine.</d>")
        source = prompt("{Jerry Seinfeld_BC}\n{George Costanza_BC}", detail).replace("retention_analysis:\n\n\n", "")
        result = compiler.compile_prompt(source, records)
        self.assertNotIn("retention_analysis:", result.prompt)
        self.assertEqual(result.debug["warnings"], [])
        self.assertEqual(result.debug["generated_voice_retention"], [])
        self.assertEqual(result.images, ["George Costanza_BC", "Jerry Seinfeld_BC"])
        self.assertEqual(result.audios, result.images)
        self.assertIn("<Subject 1> (S1) says, <d>[English <Audio 1>]They did? Because I can be more intimidating.</d>", result.prompt)
        self.assertIn("<Subject 2> (S2) reacts: <d>[English <Audio 2>]My refrigerator doesn't move. It barely refrigerates.</d>", result.prompt)
        self.assertIn("<d>[English <Audio 1>]Fine.</d>", result.prompt)

    def test_temporary_and_standalone_header_voices_need_no_speech_verb(self):
        source = prompt("<character:guest>", "<character:guest> grins: <d>[French <voice:guest>]Bonjour!</d>",
                        declarations="<character:guest = A guest.>\n<voice:guest = A warm voice.>")
        result = compiler.compile_prompt(source, {})
        self.assertIn("<Subject 1> (S1) grins: <d>[French A warm voice.]Bonjour!</d>", result.prompt)
        self.assertEqual(result.audios, [])
        source = prompt("{hero}", "A voice is heard. <d>[English \u00a7hero\u00a7]Hello.</d>")
        result = compiler.compile_prompt(source, {"hero": character(audio="hero.wav")})
        self.assertEqual(result.debug["speakers"], {"1":"saved:hero"})
        self.assertIn("<d>[English <Audio 1>]Hello.</d>", result.prompt)

    def test_missing_resources_and_broken_structure_still_fail(self):
        for source, code in (
            (prompt("", "<d>[English \u00a7missing\u00a7]Hi.</d>"), "UNKNOWN_SAVED_RESOURCE"),
            (prompt("", "<d>[English <voice:missing>]Hi.</d>"), "UNKNOWN_TEMPORARY_RESOURCE"),
            (prompt("", "<d>[English]Hi."), "INVALID_DIALOGUE"),
            (prompt("", "<d><d>Hi.</d></d>"), "INVALID_DIALOGUE"),
            (prompt("", "<d>[English <Audio 1>]Hi.</d>"), "AUTHORED_RUNTIME_SLOT"),
        ):
            with self.subTest(code=code), self.assertRaisesRegex(ValueError, code):
                compiler.compile_prompt(source, {})

    def test_coffee_shop_silent_character(self):
        source = prompt("{binary_thott}\n<location:coffee_shop>",
                        "[Shot 1] {binary_thott} sits in <location:coffee_shop>.\n[Shot 2] At 00:06.000, he drinks coffee.",
                        "{binary_thott} drinks coffee.", "{binary_thott}: fully_preserved - keep clothing.",
                        declarations="<location:coffee_shop = A cozy coffee shop with wooden tables.>")
        result = compiler.compile_prompt(source, {"binary_thott": character("image.png", "voice.wav")})
        self.assertIn("<Subject 1> is Binary Thott in <Picture 1>, A young man with black dreadlocks.", result.prompt)
        self.assertIn("<Subject 2> is A cozy coffee shop with wooden tables.", result.prompt)
        self.assertNotIn("[reference generation]", result.prompt)
        self.assertNotIn("<Audio", result.prompt)
        self.assertEqual(result.audios, [])
        self.assertIsNone(result.debug["resources"]["saved:binary_thott"]["audio"])
        self.assertFalse(result.debug["resources"]["saved:binary_thott"]["audio_used"])
        self.assertEqual(result.debug["speakers"], {})
        self.assertIn("[Shot 2] At 00:06.000, he drinks coffee.", result.prompt)
        self.assertIn("<Subject 1>: fully_preserved - keep clothing.", result.prompt)

    def test_text_only_first_speaker_gets_matching_subject_without_dummy_media(self):
        declarations = "<character:cashier = A cashier in a red uniform.>\n<voice:cashier = Young male voice, upbeat tone.>"
        dialogue = "<d>[English]Your order is ready.</d>"
        source = prompt("{binary_thott}\n<character:cashier>\n<voice:cashier>\n§binary_thott§",
                        f"<character:cashier> says <voice:cashier>, {dialogue}\n"
                        "{binary_thott} says §binary_thott§, <d>[English]Thanks!</d>\n"
                        f"<character:cashier> says <voice:cashier>, {dialogue}", declarations=declarations)
        result = compiler.compile_prompt(source, {"binary_thott": character("i.png", "a.wav")})
        self.assertEqual(result.prompt.count("<Subject 1> (S1) says in Young male voice, upbeat tone"), 2)
        self.assertIn("<Subject 2> (S2) says using the recognizable voice timbre referenced from <Audio 1>", result.prompt)
        self.assertIn("<Audio 1> is the voice-timbre reference for <Subject 2> (S2).", result.prompt)
        self.assertEqual(result.images, ["binary_thott"])
        self.assertEqual(result.audios, ["binary_thott"])
        self.assertEqual(result.prompt.count(dialogue), 2)
        self.assertEqual(result.debug["speakers"], {"1":"temporary:character:cashier", "2":"saved:binary_thott"})
        self.assertEqual(len(result.debug["audio"]), 1)

    def test_namespace_collision_and_resource_order(self):
        records = {"coffee_shop": dict(reference_type="location", image_description="Saved cafe."),
                   "rich": character("i.png", "a.wav")}
        result = compiler.compile_prompt(prompt("<location:coffee_shop>\n{coffee_shop}\n{rich}",
            "{coffee_shop} beside <location:coffee_shop>.", declarations="<location:coffee_shop = Temporary cafe.>"), records)
        self.assertEqual(result.debug["resources"]["saved:rich"]["subject"], 1)
        self.assertEqual(result.debug["resources"]["saved:coffee_shop"]["subject"], 2)
        self.assertEqual(result.debug["resources"]["temporary:location:coffee_shop"]["subject"], 3)
        self.assertIn("<Subject 2> beside <Subject 3>.", result.prompt)
        changed = compiler.compile_prompt(prompt("{rich}\n{coffee_shop}\n<location:coffee_shop>",
            declarations="<location:coffee_shop = Temporary cafe.>"), records)
        self.assertEqual(result.debug["pictures"], changed.debug["pictures"])
        self.assertEqual([v["subject"] for v in result.debug["resources"].values()],
                         [v["subject"] for v in changed.debug["resources"].values()])

    def test_video_embedded_audio_and_music_slot_order(self):
        records = {"hero": character("i.png", "voice.wav"),
                   "motion": dict(reference_type="video", video_file="clip.mp4", video_has_audio=True),
                   "score": dict(reference_type="music", audio_file="score.wav")}
        source = prompt("{hero}", "{hero} says §hero§, <d>[English]Go!</d> Use {motion} for movement.", music="Use {score} as score.")
        result = compiler.compile_prompt(source, records)
        self.assertEqual(result.debug["resources"]["saved:hero"]["audio"], 2)
        self.assertEqual(result.debug["resources"]["saved:score"]["audio"], 3)
        self.assertIsNone(result.debug["resources"]["saved:motion"]["subject"])
        self.assertIsNone(result.debug["resources"]["saved:score"]["subject"])
        self.assertNotIn("video continuation", result.prompt)
        self.assertIn("Use <Video 1> for movement.", result.prompt)
        self.assertIn("Use <Audio 3> as score.", result.prompt)
        for usage, task in [("continuation", "video continuation"), ("editing", "video editing"), ("motion_reference", "reference generation")]:
            self.assertIn(task, compiler.compile_prompt(source, records, video_usage=usage).debug["task_types"])

    def test_text_voice_no_audio_and_no_prose_rewrite(self):
        source = prompt("{hero}\n§hero§", "{hero} says §hero§, <d>[French]Bonjour, mon ami!</d>", retention="{hero}: partially_preserved - exactly this wording.")
        result = compiler.compile_prompt(source, {"hero": character()})
        self.assertNotIn("<Audio", result.prompt)
        self.assertNotIn("audio reference", result.prompt)
        self.assertIn("in Young male voice, relaxed cadence", result.prompt)
        self.assertIn("<d>[French]Bonjour, mon ami!</d>", result.prompt)
        self.assertIn("partially_preserved - exactly this wording.", result.prompt)

    def test_definitions_sorted_with_voice_and_authored_text_preserved(self):
        records = {"randy": character("randy.png", "randy.wav"),
                   "apartment": dict(reference_type="location", name="Apartment", image_file="room.png"),
                   "kramer": character("kramer.png"), "jerry": character("jerry.png")}
        detail = "{kramer} says \u00a7kramer\u00a7, <d>[English]One.</d>\n{jerry} says \u00a7jerry\u00a7, <d>[English]Two.</d>\n{randy} says \u00a7randy\u00a7, <d>[English]Three.</d>"
        for voice_definition in ("", "\u00a7randy\u00a7\n"):
            source = prompt("Cast notes.\n" + voice_definition + "{jerry}\nJerry stays by the door.\n\n{kramer}\n{randy}\n{apartment}",
                            detail, summary="{jerry} watches {randy}.")
            result = compiler.compile_prompt(source, records)
            definitions = result.prompt.split("summary:")[0]
            labels = ["<Subject 1> is", "<Subject 2> is", "<Subject 3> is", "<Audio 1> is", "<Subject 4> is"]
            positions = [definitions.index(label) for label in labels]
            self.assertEqual(positions, sorted(positions))
            self.assertIn("<Subject 3> (S3)", definitions)
            self.assertEqual(definitions.count("<Audio 1> is"), 1)
            self.assertIn("Cast notes.", definitions)
            self.assertGreater(definitions.index("Jerry stays by the door."), definitions.index("<Subject 2> is"))
            self.assertLess(definitions.index("Jerry stays by the door."), definitions.index("<Subject 3> is"))
            self.assertIn("<Subject 2> watches <Subject 3>.", result.prompt)
            self.assertEqual(result.images, ["kramer", "jerry", "randy", "apartment"])

    def test_summary_subject_entries_sort_without_changing_speaker_order(self):
        records = {"randy": character("randy.png", "randy.wav"),
                   "apartment": dict(reference_type="location", image_file="room.png"),
                   "kramer": character("kramer.png"), "jerry": character("jerry.png")}
        detail = "{jerry} says \u00a7jerry\u00a7, <d>[English]Hi.</d>\n{randy} says \u00a7randy\u00a7, <d>[English]Hello.</d>"
        summary = "{jerry}: waits.\n\n{kramer}: stands.\n{randy}: sits.\n{apartment}: unchanged."
        result = compiler.compile_prompt(prompt("{jerry}\n{kramer}\n{randy}\n{apartment}", detail, summary), records)
        section = result.prompt.split("summary:\n\n", 1)[1].split("\n\nretention_analysis:", 1)[0]
        self.assertEqual(section, "<Subject 1>: waits. <Subject 2>: sits. <Subject 3>: unchanged. <Subject 4>: stands.")
        self.assertEqual(result.debug["speakers"], {"1": "saved:jerry", "2": "saved:randy"})
        self.assertEqual(result.images, ["jerry", "randy", "apartment", "kramer"])
        self.assertIn("<Subject 1> (S1) says", result.prompt)

    def test_summary_narrative_and_multisubject_sentences_are_preserved(self):
        examples = [
            "<Subject 4> watches <Subject 1>.\n<Subject 2> waits.",
            "<Subject 4> watches. <Subject 1> leaves.",
            "<Subject 4> watches.\n<Subject 1> walks\ninto the room.",
            "At the counter, <Subject 4> watches.\n<Subject 1> waits.",
        ]
        for summary in examples:
            self.assertEqual(compiler._sort_summary_entries(summary), summary)
        self.assertEqual(compiler._sort_summary_entries("- <Subject 10>: waits.\n- <Subject 2>: sits.\n- <Subject 2>: smiles."),
                         "- <Subject 2>: sits.\n- <Subject 2>: smiles.\n- <Subject 10>: waits.")

    def test_optional_retention_sorted_without_generated_entries(self):
        records = {"george": character("george.png", "george.wav"),
                   "jerry": character("jerry.png", "jerry.wav"),
                   "apartment": dict(reference_type="location", image_file="room.png")}
        detail = "{jerry} says \u00a7jerry\u00a7, <d>[English]Hi.</d>\n{george} says \u00a7george\u00a7, <d>[English]Hello.</d>"
        retention = ("{jerry} (appears throughout): fully_preserved - keep Jerry.\n"
                     "Keep his hairstyle, too.\n\n"
                     "\u00a7jerry\u00a7: weak_reference - keep only the timbre.\n"
                     "{george} (appears throughout): fully_preserved - keep George.\n"
                     "{apartment}: fully_preserved - keep the sofa.")
        result = compiler.compile_prompt(prompt("{jerry}\n{george}\n{apartment}", detail,
                                                retention=retention), records)
        section = result.prompt.split("retention_analysis:\n\n")[1].split("\n\ndetailed_description:")[0]
        labels = ["<Subject 1> (appears", "<Subject 2> (appears", "<Subject 3>:",
                  "<Audio 1>:"]
        positions = [section.index(label) for label in labels]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("keep Jerry.\nKeep his hairstyle, too.", section)
        self.assertIn("<Audio 1>: weak_reference - keep only the timbre.", section)
        self.assertEqual(result.debug["generated_voice_retention"], [])
        self.assertEqual(result.debug["speakers"], {"1": "saved:jerry", "2": "saved:george"})
        self.assertEqual(result.images, ["jerry", "george", "apartment"])
        self.assertEqual(result.audios, ["jerry", "george"])

    def test_retention_numeric_sort_preserves_blocks_and_duplicate_order(self):
        blocks = ["<Audio 2>: reference - guide <Subject 1>.",
                  "- <Subject 10>: fully_preserved - ten.\nWrapped detail.",
                  "<Video 1>: partially_preserved - motion.",
                  "<Subject 2>: fully_preserved - first entry.",
                  "<Picture 1>: weak_reference - palette.",
                  "<Subject 2>: partially_preserved - second entry.",
                  "<Audio 1>: reference - guide <Subject 10>."]
        text = "Authored note.\n\n" + "\n".join(blocks)
        expected = "Authored note.\n\n" + "\n\n".join(blocks[i] for i in (3, 5, 1, 4, 2, 6, 0))
        self.assertEqual(compiler._sort_retention_entries(text), expected)
        self.assertEqual(compiler._sort_retention_entries("N/A"), "N/A")

    def test_used_media_have_definitions_and_editing_summary_opening(self):
        records = {"clip": dict(reference_type="video", video_file="clip.mp4", video_description="A walk along the river."),
                   "score": dict(reference_type="music", audio_file="score.wav", audio_description="Slow piano.")}
        source = prompt("", "Follow {clip}.", summary="Keep the framing.\nUse {score} as score.", music="Reuse {score}.")
        result = compiler.compile_prompt(source, records, video_usage="editing", audio_usage="reuse")
        definitions = result.prompt.split("summary:")[0]
        self.assertIn("<Video 1> is the source video for the target video edit. A walk along the river.", definitions)
        self.assertIn("<Audio 1> is the music reference reused in the target video. Slow piano.", definitions)
        self.assertNotIn("<Subject", definitions)
        summary = result.prompt.split("summary:\n\n")[1].split("\n\nretention_analysis:")[0]
        self.assertEqual(summary, "The target video is an edited version of <Video 1>. Keep the framing. Use <Audio 1> as score.")
        explicit = compiler.compile_prompt(prompt("{clip}\n{score}", "Follow {clip}.", music="Use {score}."), records)
        self.assertEqual(explicit.prompt.count("<Video 1> is"), 1)
        self.assertEqual(explicit.prompt.count("<Audio 1> is"), 1)

    def test_summary_voice_reference_is_retained_without_inventing_speaker(self):
        source = prompt("{hero}", summary="Use \u00a7hero\u00a7 as the voice reference for {hero}.")
        result = compiler.compile_prompt(source, {"hero": character("hero.png", "voice.wav")})
        self.assertIn("Use <Audio 1> as the voice reference for <Subject 1>.", result.prompt)
        self.assertIn("<Audio 1> is the voice-timbre reference for <Subject 1>.", result.prompt)
        self.assertEqual(result.debug["speakers"], {})
        text_only = compiler.compile_prompt(source, {"hero": character()})
        self.assertNotIn("<Audio", text_only.prompt)
        self.assertIn("Use Young male voice, relaxed cadence.", text_only.prompt)

    def test_offscreen_speaker_and_audio_cues_preserve_dialogue(self):
        records = {"hero": character("hero.png", "voice.wav"),
                   "score": dict(reference_type="music", audio_file="score.wav", audio_usage="reuse")}
        detail = "{hero} (off-screen) exclaims \u00a7hero\u00a7, <d>[French]Salut!</d>\n{hero} says \u00a7hero\u00a7, <d>[French]Au revoir!<cutoff></d>\nWhen {score} reaches <d>[English]Hello.</d>, the light changes."
        result = compiler.compile_prompt(prompt("{hero}", detail, music="Use {score}."), records)
        self.assertIn("<Subject 1> (S1) (off-screen) exclaims", result.prompt)
        self.assertEqual(result.debug["speakers"], {"1": "saved:hero"})
        self.assertIn("When <Audio 2> reaches <d>[English]Hello.</d>", result.prompt)
        self.assertIn("<d>[French]Au revoir!<cutoff></d>", result.prompt)

    def test_retention_diagnostics_respect_roles_and_ignore_source_only_pictures(self):
        records = {"hero": character("hero.png", "voice.wav")}
        detail = "{hero} says \u00a7hero\u00a7, <d>[English]Hi.</d>"
        source = prompt("{hero}", detail, retention="{hero} (appears in [Shot 1]): fully_preserved - keep identity.\n\u00a7hero\u00a7: reference - timbre only.")
        result = compiler.compile_prompt(source, records)
        self.assertEqual(result.debug["warnings"], [])
        bad = compiler.compile_prompt(prompt("{hero}", detail, retention="{hero}: reference - identity."), records)
        self.assertEqual(bad.debug["warnings"], [])
        self.assertFalse(any("MISSING_RETENTION_ENTRY: <Audio 1>" in w for w in bad.debug["warnings"]))
        self.assertEqual(bad.debug["generated_voice_retention"], [])
        self.assertFalse(any("Picture" in w for w in bad.debug["warnings"]))
        self.assertNotIn("(S1)", result.prompt.split("retention_analysis:")[1].split("detailed_description:")[0])

    def test_dialogue_placement_is_not_enforced(self):
        for section in ("summary", "sound", "music", "retention"):
            with self.subTest(section=section):
                result = compiler.compile_prompt(prompt("", **{section: "<d>[English]Hello.</d>"}), {})
                self.assertIn("<d>[English]Hello.</d>", result.prompt)

    def test_video_soundtrack_is_explicit_and_has_no_speaker(self):
        records = {"clip": dict(reference_type="video", video_file="clip.mp4", video_has_audio=True)}
        silent = compiler.compile_prompt(prompt("", detail="Follow {clip}."), records, video_usage="editing", audio_usage="reuse")
        self.assertNotIn("<Audio", silent.prompt)
        self.assertNotIn("audio reuse", silent.debug["task_types"])
        source = prompt("", detail="Edit {clip}. When \u00a7clip\u00a7 reaches <d>[English]Go!</d>, the light changes.",
                        retention="{clip}: partially_preserved - change the light.\n\u00a7clip\u00a7: partially_copy - keep the original ambience.",
                        sound="Reuse the ambience from \u00a7clip\u00a7.", music="Reuse the score layer from \u00a7clip\u00a7.")
        result = compiler.compile_prompt(source, records, video_usage="editing", audio_usage="reuse")
        self.assertIn("<Audio 1> is the synchronized audio track of <Video 1> and is reused in the target video.", result.prompt)
        self.assertEqual(result.debug["speakers"], {})
        self.assertEqual(result.debug["warnings"], [])
        self.assertEqual(result.debug["task_types"], ["video editing", "audio reuse"])
        self.assertIn("Reuse the score layer from <Audio 1>.", result.prompt)
        self.assertEqual(result.audios, [])
        self.assertEqual(result.videos, ["clip"])
        records["clip"]["video_has_audio"] = False
        with self.assertRaisesRegex(ValueError, "MISSING_VIDEO_AUDIO"):
            compiler.compile_prompt(source, records)

    def test_reused_voice_does_not_claim_timbre_only_reference(self):
        source = prompt("{hero}", "{hero} says \u00a7hero\u00a7, <d>[English]Go!</d>")
        result = compiler.compile_prompt(source, {"hero": character(audio="voice.wav")}, audio_usage="reuse")
        self.assertIn("using vocal audio directly reused from <Audio 1>", result.prompt)
        self.assertIn("<Audio 1> is the source of the vocal audio reused for <Subject 1> (S1).", result.prompt)
        self.assertNotIn("voice-timbre reference", result.prompt)
        self.assertEqual(result.debug["task_types"], ["audio reuse"])
        reference = compiler.compile_prompt(source, {"hero": character(audio="voice.wav")})
        self.assertEqual(reference.debug["task_types"], ["reference generation", "audio reference"])

    def test_mixed_voice_isolation_aligns_subjects_but_keeps_sparse_audio_ownership(self):
        records = {"randy": character("randy.png", "randy.wav"),
                   "cafe": dict(reference_type="location", image_file="cafe.png"),
                   "kramer": character("kramer.png"), "jerry": character("jerry.png")}
        records["kramer"]["audio_description"] = "Kramer's distinctive voice."
        records["jerry"]["audio_description"] = "Jerry's distinctive voice."
        detail = "{kramer} says \u00a7kramer\u00a7, <d>[English]Look at the package.</d>\n{randy} says \u00a7randy\u00a7, <d>[English]Fine.</d>\n{jerry} (off-screen) says \u00a7jerry\u00a7, <d>[English]Finally.</d>\n{randy} says \u00a7randy\u00a7, <d>[English]Yes.</d>"
        source = prompt("{jerry}\n{kramer}\n{randy}\n{cafe}", detail)
        result = compiler.compile_prompt(source, records)
        self.assertEqual(result.debug["speakers"], {"1":"saved:kramer", "2":"saved:randy", "3":"saved:jerry"})
        self.assertIn("<Subject 2> (S2) is the only speaker using <Audio 1> as its voice-timbre reference.", result.prompt)
        self.assertEqual(result.prompt.count("<Subject 2> (S2) is the only speaker"), 2)
        for subject, speaker in ((1,1),(3,3)):
            self.assertIn(f"<Subject {subject}> (S{speaker}) uses its own assigned voice identity and must not use or imitate <Audio 1>.", result.prompt)
        self.assertIn("<Subject 3> (S3) (off-screen) says in Jerry's distinctive voice", result.prompt)
        retention = result.prompt.split("retention_analysis:")[1].split("detailed_description:")[0]
        self.assertEqual(retention.strip(), "")
        self.assertNotIn("(S", retention)
        self.assertEqual(retention.count("<Audio 1>:"), 0)
        self.assertEqual(compiler.DIALOGUE.findall(result.prompt), compiler.DIALOGUE.findall(source))
        disabled = compiler.compile_prompt(source, records, voice_isolation=False)
        self.assertNotIn("must not use or imitate", disabled.prompt)
        self.assertNotIn("is the only speaker", disabled.prompt)
        self.assertEqual(result.images, disabled.images)
        self.assertEqual(result.audios, disabled.audios)
        self.assertEqual(result.debug["speakers"], disabled.debug["speakers"])

    def test_voice_exclusions_do_not_capture_music_or_video_soundtracks(self):
        records = {"one": character("one.png", "one.wav"), "two": character("two.png", "two.wav"),
                   "score": dict(reference_type="music", audio_file="score.wav"),
                   "clip": dict(reference_type="video", video_file="clip.mp4", video_has_audio=True)}
        source = prompt("{one}\n{two}", "{one} says \u00a7one\u00a7, <d>[English]One.</d> {two} says \u00a7two\u00a7, <d>[English]Two.</d>",
                        sound="Reference \u00a7clip\u00a7.", music="Use {score}.")
        result = compiler.compile_prompt(source, records)
        detail = result.prompt.split("detailed_description:")[1].split("overall_soundscape:")[0]
        self.assertIn("must not use or imitate <Audio 3>", detail)
        self.assertIn("must not use or imitate <Audio 2>", detail)
        self.assertNotIn("<Audio 1>", detail)
        self.assertNotIn("<Audio 4>", detail)
        self.assertEqual(result.debug["generated_voice_retention"], [])

    def test_voice_retention_preserves_authored_analysis_and_does_not_guess_reuse(self):
        records = {"hero": character(audio="voice.wav")}
        detail = "{hero} says \u00a7hero\u00a7, <d>[English]Hi.</d>"
        authored = "\u00a7hero\u00a7: weak_reference - keep only the broad vocal atmosphere."
        result = compiler.compile_prompt(prompt("{hero}", detail, retention=authored), records)
        retention = result.prompt.split("retention_analysis:")[1].split("detailed_description:")[0]
        self.assertIn("<Audio 1>: weak_reference - keep only the broad vocal atmosphere.", retention)
        self.assertEqual(retention.count("<Audio 1>:"), 1)
        self.assertEqual(result.debug["generated_voice_retention"], [])
        reused = compiler.compile_prompt(prompt("{hero}", detail), records, audio_usage="reuse")
        self.assertEqual(reused.debug["generated_voice_retention"], [])
        self.assertEqual(reused.debug["warnings"], [])
        silent = compiler.compile_prompt(prompt("{hero}"), records)
        self.assertNotIn("<Audio", silent.prompt)
        self.assertEqual(silent.debug["generated_voice_retention"], [])

    def test_errors(self):
        records = {"hero": character("i.png", "a.wav")}
        cases = [
            (prompt("{missing}"), "UNKNOWN_SAVED_RESOURCE"),
            (prompt("<location:missing>"), "UNKNOWN_TEMPORARY_RESOURCE"),
            (prompt("", declarations="<planet:world = Round.>"), "INVALID_TEMPORARY_TYPE"),
            (prompt("", declarations="<object: = Thing.>"), "INVALID_TEMPORARY_NAME"),
            (prompt("", declarations="<object:box = >"), "MISSING_TEMPORARY_DESCRIPTION"),
            (prompt("", declarations="<object:box = Box.><object:box = Box.>"), "DUPLICATE_TEMPORARY_DECLARATION"),
            (prompt("", detail="<object:box = Box.>"), "INVALID_DECLARATION"),
            (prompt("<Subject 1> is {hero}"), "AUTHORED_RUNTIME_SLOT"),
            ("summary:\n{hero}", "INVALID_SECTION"),
            (prompt("", "{hero} walks."), "MISSING_SUBJECT_DEFINITION"),
        ]
        for source, code in cases:
            with self.subTest(code=code), self.assertRaisesRegex(ValueError, code):
                compiler.compile_prompt(source, records)

    def test_only_active_voices_consume_audio_slots_in_large_cast(self):
        records = {name: character(name + ".png", name + ".wav") for name in ("a", "b", "c", "d", "e")}
        definitions = "\n".join("{" + name + "}" for name in records)
        # Definition-only voice tags do not activate silent characters' audio.
        definitions += "\n\u00a7a\u00a7\n\u00a7b\u00a7\n\u00a7c\u00a7"
        detail = "{e} says \u00a7e\u00a7, <d>[English]First.</d>\n{d} says \u00a7d\u00a7, <d>[English]Second.</d>"
        result = compiler.compile_prompt(prompt(definitions, detail), records)
        self.assertEqual(result.images, ["e", "d", "a", "b", "c"])
        self.assertEqual(result.audios, ["e", "d"])
        self.assertEqual(result.debug["audio"], {"1":"saved:e", "2":"saved:d"})
        self.assertEqual(result.debug["speakers"], {"1":"saved:e", "2":"saved:d"})
        for name in ("a", "b", "c"):
            self.assertTrue(result.debug["resources"]["saved:"+name]["has_audio"])
            self.assertIsNone(result.debug["resources"]["saved:"+name]["audio"])
        self.assertIn("<Subject 1> (S1) is the only speaker using <Audio 1>", result.prompt)
        self.assertEqual(result.debug["generated_voice_retention"], [])
        silent = compiler.compile_prompt(prompt(definitions), records)
        self.assertEqual(silent.audios, [])
        self.assertNotIn("<Audio", silent.prompt)
        # Allocations are per-prompt, and genuinely requested fourth audio still fails.
        other = compiler.compile_prompt(prompt(definitions, "{a} says \u00a7a\u00a7, <d>[English]Next.</d>"), records)
        self.assertEqual(other.audios, ["a"])
        explicit = compiler.compile_prompt(prompt(definitions, detail, summary="Use \u00a7b\u00a7 as a voice reference."), records)
        self.assertEqual(explicit.audios, ["e", "d", "b"])
        with self.assertRaisesRegex(ValueError, "REFERENCE_LIMIT: 4 audio files"):
            compiler.compile_prompt(prompt(definitions, detail, summary="Use \u00a7a\u00a7 and \u00a7b\u00a7 as voice references."), records)

    def test_active_voice_music_and_embedded_slots_remain_aligned(self):
        records = {"silent": character("silent.png", "silent.wav"),
                   "speaker": character("speaker.png", "speaker.wav"),
                   "score": dict(reference_type="music", audio_file="score.wav"),
                   "clip": dict(reference_type="video", video_file="clip.mp4", video_has_audio=True)}
        result = compiler.compile_prompt(prompt("{silent}\n{speaker}", "{speaker} says \u00a7speaker\u00a7, <d>[English]Hi.</d> Follow {clip}.", music="Use {score}."), records)
        self.assertEqual(result.audios, ["speaker", "score"])
        self.assertEqual(result.debug["audio"], {"1":"saved:clip", "2":"saved:speaker", "3":"saved:score"})
        self.assertEqual(result.debug["resources"]["saved:silent"]["subject"], 2)
        self.assertEqual(result.debug["resources"]["saved:speaker"]["subject"], 1)
        self.assertEqual(result.images, ["speaker", "silent"])
        self.assertIn("<Subject 1> (S1) is the only speaker using <Audio 2>", result.prompt)

    def test_south_park_reply_modifier_preserves_ownership_and_dialogue(self):
        names = ("Stan Marsh_BC", "Kyle Broflovski_BC", "Eric Cartman_BC")
        records = {name: character(name+".png", name+".wav") for name in names}
        definitions = "\n".join("{"+name+"}" for name in names)
        detail = "[Shot 3] At 00:08.000, the bus exits frame. {Stan Marsh_BC}, {Kyle Broflovski_BC}, and {Eric Cartman_BC} stare toward where Kenny landed. {Stan Marsh_BC} says \u00a7Stan Marsh_BC\u00a7, <d>[English]Oh my God! They killed Kenny!</d> {Kyle Broflovski_BC} immediately replies \u00a7Kyle Broflovski_BC\u00a7, <d>[English]You bastards!</d>"
        result = compiler.compile_prompt(prompt(definitions, detail), records)
        self.assertEqual(result.debug["speakers"], {"1":"saved:Stan Marsh_BC", "2":"saved:Kyle Broflovski_BC"})
        self.assertEqual(result.audios, list(names[:2]))
        self.assertIn("<Subject 2> (S2) immediately replies using the recognizable voice timbre referenced from <Audio 2>", result.prompt)
        self.assertIn("<Subject 1>, <Subject 2>, and <Subject 3> stare toward where Kenny landed.", result.prompt)
        self.assertEqual(compiler.DIALOGUE.findall(detail), compiler.DIALOGUE.findall(result.prompt))

    def test_vocal_modifiers_before_and_after_verbs_for_temporary_speakers(self):
        for phrase in ("quietly says", "says quietly", "almost immediately replies", "then softly answers",
                       "STILL QUIETLY RESPONDS", "(off-screen) just mutters softly"):
            with self.subTest(phrase=phrase):
                detail = f"<character:guest> {phrase} <voice:guest>: <d>[English]Hello.</d>"
                source = prompt("<character:guest>", detail, declarations="<character:guest = A guest.>\n<voice:guest = A calm voice.>")
                result = compiler.compile_prompt(source, {})
                self.assertIn(f"<Subject 1> (S1) {phrase} in A calm voice", result.prompt)
                self.assertEqual(result.debug["speakers"], {"1":"temporary:character:guest"})
                self.assertEqual(result.audios, [])

    def test_voice_phrasing_and_cross_character_references_do_not_fail(self):
        records = {"one": character(audio="one.wav"), "two": character(audio="two.wav")}
        details = (
            "{one} looks away. Immediately replies \u00a7one\u00a7, <d>[English]Hi.</d>",
            "{one} says to {two} \u00a7one\u00a7, <d>[English]Hi.</d>",
            "{one} immediately replies \u00a7two\u00a7, <d>[English]Hi.</d>",
            "Voice direction: \u00a7one\u00a7. No scripted dialogue.",
        )
        for detail in details:
            with self.subTest(detail=detail):
                result = compiler.compile_prompt(prompt("{one}\n{two}", detail), records)
                self.assertEqual(len(result.audios), 1)
                self.assertNotIn("\u00a7", result.prompt)
                self.assertEqual(compiler.DIALOGUE.findall(result.prompt), compiler.DIALOGUE.findall(detail))

    def test_barbie_inline_voice_needs_no_saved_reference_or_voice_declaration(self):
        declarations = "<character:barbie_doll = A blonde articulated plastic doll.>\n<object:fire_axe = A red fire axe.>"
        detail = "The doll grips <object:fire_axe> outside the door with one articulated plastic hand. In a deliberately uncanny cheerful voice, <character:barbie_doll> says in a barbie like voice, <d>[English]Here's Barbie!</d>"
        source = prompt("<character:barbie_doll>\n<object:fire_axe>", detail, declarations=declarations)
        result = compiler.compile_prompt(source, {})
        self.assertEqual(result.debug["speakers"], {"1":"temporary:character:barbie_doll"})
        self.assertEqual(result.audios, [])
        self.assertNotIn("<Audio", result.prompt)
        self.assertIn("In a deliberately uncanny cheerful voice, <Subject 1> (S1) says in a barbie like voice, <d>[English]Here's Barbie!</d>", result.prompt)
        self.assertIn("The doll grips <Subject 2> outside the door", result.prompt)
        self.assertEqual(compiler.DIALOGUE.findall(result.prompt), compiler.DIALOGUE.findall(source))

    def test_flexible_tagged_clause_and_inline_speech_share_speaker_order(self):
        records = {"hero": character("hero.png", "hero.wav"), "inline": character("inline.png", "unused.wav")}
        detail = "{inline} turns toward the door and says in a warm voice, <d>[English]Welcome.</d>\n{hero}, using \u00a7hero\u00a7 with a startled delivery, <d>[English]Hello!</d>\n{inline} (off-screen) laughs softly and replies, <d>[English]Come in.</d>"
        source = prompt("{hero}\n{inline}", detail)
        result = compiler.compile_prompt(source, records)
        self.assertEqual(result.debug["speakers"], {"1":"saved:inline", "2":"saved:hero"})
        self.assertEqual(result.audios, ["hero"])
        self.assertIn("<Subject 1> (S1) turns toward the door and says in a warm voice", result.prompt)
        self.assertIn("<Subject 1> (S1) (off-screen) laughs softly and replies", result.prompt)
        self.assertIn("using the recognizable voice timbre referenced from <Audio 1> with a startled delivery", result.prompt)
        self.assertNotIn("using using", result.prompt)
        self.assertIn("must not use or imitate <Audio 1>", result.prompt)
        self.assertEqual(compiler.DIALOGUE.findall(result.prompt), compiler.DIALOGUE.findall(source))
        # An explicit reference event can also contain action/delivery wording.
        result = compiler.compile_prompt(prompt("{hero}", "{hero} turns around and says \u00a7hero\u00a7, <d>[English]Hi.</d>"), records)
        self.assertEqual(result.audios, ["hero"])

    def test_bare_character_speech_does_not_require_voice_metadata(self):
        source = prompt("<character:guest>", "<character:guest> says, <d>[English]Hi.</d>", declarations="<character:guest = A guest.>")
        result = compiler.compile_prompt(source, {})
        self.assertIn("<Subject 1> (S1) says, <d>[English]Hi.</d>", result.prompt)
        self.assertEqual(result.debug["speakers"], {"1":"temporary:character:guest"})
        self.assertEqual(result.audios, [])

    def test_speech_clause_can_wrap_but_not_cross_paragraphs_or_shots(self):
        records = {"hero": character(audio="hero.wav")}
        source = prompt("{hero}", "{hero} turns and\nreplies using \u00a7hero\u00a7,\n<d>[English]Hi.</d>")
        result = compiler.compile_prompt(source, records)
        self.assertEqual(result.debug["speakers"], {"1":"saved:hero"})
        for boundary in ("\n\n", "\n[Shot 2] "):
            with self.subTest(boundary=boundary):
                result = compiler.compile_prompt(prompt("{hero}", "{hero}"+boundary+"using \u00a7hero\u00a7, <d>[English]Hi.</d>"), records)
                self.assertEqual(result.audios, ["hero"])

    def test_no_truncation_of_audio_slots(self):
        records = {f"music{i}": dict(reference_type="music", audio_file=f"{i}.wav") for i in range(4)}
        with self.assertRaisesRegex(ValueError, "REFERENCE_LIMIT"):
            compiler.compile_prompt(prompt("", music=" ".join("{"+key+"}" for key in records)), records)

    def test_new_location_and_debug_deterministic(self):
        source = "[new_location]\n" + prompt("{hero}")
        first = compiler.compile_prompt(source, {"hero":character("i.png")})
        second = compiler.compile_prompt(source, {"hero":character("i.png")})
        self.assertEqual(first.prompt, second.prompt)
        self.assertEqual(first.mapping, second.mapping)
        self.assertTrue(first.prompt.startswith("[new_location]"))
        self.assertEqual(json.loads(first.mapping), first.debug)


if __name__ == "__main__": unittest.main()

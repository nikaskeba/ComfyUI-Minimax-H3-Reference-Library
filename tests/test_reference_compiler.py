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
    def test_coffee_shop_silent_character(self):
        source = prompt("{binary_thott}\n<location:coffee_shop>",
                        "[Shot 1] {binary_thott} sits in <location:coffee_shop>.\n[Shot 2] At 00:06.000, he drinks coffee.",
                        "{binary_thott} drinks coffee.", "{binary_thott}: fully_preserved - keep clothing.",
                        declarations="<location:coffee_shop = A cozy coffee shop with wooden tables.>")
        result = compiler.compile_prompt(source, {"binary_thott": character("image.png", "voice.wav")})
        self.assertIn("<Subject 1> is Binary Thott in <Picture 1>, A young man with black dreadlocks.", result.prompt)
        self.assertIn("<Subject 2> is A cozy coffee shop with wooden tables.", result.prompt)
        self.assertIn("[reference generation]", result.prompt)
        self.assertNotIn("<Audio", result.prompt)
        self.assertEqual(result.audios, ["binary_thott"])
        self.assertFalse(result.debug["resources"]["saved:binary_thott"]["audio_used"])
        self.assertEqual(result.debug["speakers"], {})
        self.assertIn("[Shot 2] At 00:06.000, he drinks coffee.", result.prompt)
        self.assertIn("<Subject 1>: fully_preserved - keep clothing.", result.prompt)

    def test_speaker_order_independent_of_subject_and_dialogue_preserved(self):
        declarations = "<character:cashier = A cashier in a red uniform.>\n<voice:cashier = Young male voice, upbeat tone.>"
        dialogue = "<d>[English]Your order is ready.</d>"
        source = prompt("{binary_thott}\n<character:cashier>\n<voice:cashier>\n§binary_thott§",
                        f"<character:cashier> says <voice:cashier>, {dialogue}\n"
                        "{binary_thott} says §binary_thott§, <d>[English]Thanks!</d>\n"
                        f"<character:cashier> says <voice:cashier>, {dialogue}", declarations=declarations)
        result = compiler.compile_prompt(source, {"binary_thott": character("i.png", "a.wav")})
        self.assertEqual(result.prompt.count("<Subject 2> (S1) says in Young male voice, upbeat tone"), 2)
        self.assertIn("<Subject 1> (S2) says using the recognizable voice timbre referenced from <Audio 1>", result.prompt)
        self.assertIn("<Audio 1> is the voice-timbre reference for <Subject 1> (S2).", result.prompt)
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
            labels = ["<Subject 1> is", "<Audio 1> is", "<Subject 2> is", "<Subject 3> is", "<Subject 4> is"]
            positions = [definitions.index(label) for label in labels]
            self.assertEqual(positions, sorted(positions))
            self.assertIn("<Subject 1> (S3)", definitions)
            self.assertEqual(definitions.count("<Audio 1> is"), 1)
            self.assertIn("Cast notes.", definitions)
            self.assertGreater(definitions.index("Jerry stays by the door."), definitions.index("<Subject 4> is"))
            self.assertIn("<Subject 4> watches <Subject 1>.", result.prompt)
            self.assertEqual(result.images, list(records))

    def test_summary_subject_entries_sort_without_changing_speaker_order(self):
        records = {"randy": character("randy.png", "randy.wav"),
                   "apartment": dict(reference_type="location", image_file="room.png"),
                   "kramer": character("kramer.png"), "jerry": character("jerry.png")}
        detail = "{jerry} says \u00a7jerry\u00a7, <d>[English]Hi.</d>\n{randy} says \u00a7randy\u00a7, <d>[English]Hello.</d>"
        summary = "{jerry}: waits.\n\n{kramer}: stands.\n{randy}: sits.\n{apartment}: unchanged."
        result = compiler.compile_prompt(prompt("{jerry}\n{kramer}\n{randy}\n{apartment}", detail, summary), records)
        section = result.prompt.split("summary:\n\n", 1)[1].split("\n\nretention_analysis:", 1)[0]
        self.assertEqual(section, "[reference generation + audio reference] <Subject 1>: sits. <Subject 2>: unchanged. <Subject 3>: stands. <Subject 4>: waits.")
        self.assertEqual(result.debug["speakers"], {"1": "saved:jerry", "2": "saved:randy"})
        self.assertEqual(result.images, list(records))
        self.assertIn("<Subject 4> (S1) says", result.prompt)

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
        self.assertEqual(summary, "[video editing + audio reuse] The target video is an edited version of <Video 1>. Keep the framing. Use <Audio 1> as score.")
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
        self.assertTrue(any(w.startswith("INVALID_RETENTION_MARKER") for w in bad.debug["warnings"]))
        self.assertFalse(any("MISSING_RETENTION_ENTRY: <Audio 1>" in w for w in bad.debug["warnings"]))
        self.assertEqual(bad.debug["generated_voice_retention"], [1])
        self.assertFalse(any("Picture" in w for w in bad.debug["warnings"]))
        self.assertNotIn("(S1)", result.prompt.split("retention_analysis:")[1].split("detailed_description:")[0])

    def test_dialogue_rejected_outside_detailed_description(self):
        for section in ("summary", "sound", "music", "retention"):
            with self.subTest(section=section), self.assertRaisesRegex(ValueError, "DIALOGUE_OUTSIDE_DETAIL"):
                compiler.compile_prompt(prompt("", **{section: "<d>[English]Hello.</d>"}), {})

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

    def test_mixed_voice_isolation_uses_actual_owner_not_matching_subject_number(self):
        records = {"randy": character("randy.png", "randy.wav"),
                   "cafe": dict(reference_type="location", image_file="cafe.png"),
                   "kramer": character("kramer.png"), "jerry": character("jerry.png")}
        records["kramer"]["audio_description"] = "Kramer's distinctive voice."
        records["jerry"]["audio_description"] = "Jerry's distinctive voice."
        detail = "{kramer} says \u00a7kramer\u00a7, <d>[English]Look at the package.</d>\n{randy} says \u00a7randy\u00a7, <d>[English]Fine.</d>\n{jerry} (off-screen) says \u00a7jerry\u00a7, <d>[English]Finally.</d>\n{randy} says \u00a7randy\u00a7, <d>[English]Yes.</d>"
        source = prompt("{jerry}\n{kramer}\n{randy}\n{cafe}", detail)
        result = compiler.compile_prompt(source, records)
        self.assertEqual(result.debug["speakers"], {"1":"saved:kramer", "2":"saved:randy", "3":"saved:jerry"})
        self.assertIn("<Subject 1> (S2) is the only speaker using <Audio 1> as its voice-timbre reference.", result.prompt)
        self.assertEqual(result.prompt.count("<Subject 1> (S2) is the only speaker"), 2)
        for subject, speaker in ((3,1),(4,3)):
            self.assertIn(f"<Subject {subject}> (S{speaker}) uses its own assigned voice identity and must not use or imitate <Audio 1>.", result.prompt)
        self.assertIn("<Subject 4> (S3) (off-screen) says in Jerry's distinctive voice", result.prompt)
        retention = result.prompt.split("retention_analysis:")[1].split("detailed_description:")[0]
        self.assertIn("<Audio 1>: reference - voice timbre and delivery guide <Subject 1> exclusively", retention)
        self.assertNotIn("(S", retention)
        self.assertEqual(retention.count("<Audio 1>:"), 1)
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
        self.assertEqual(result.debug["generated_voice_retention"], [2,3])

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
        self.assertTrue(any("MISSING_RETENTION_ENTRY: <Audio 1>" in w for w in reused.debug["warnings"]))
        silent = compiler.compile_prompt(prompt("{hero}"), records)
        self.assertNotIn("<Audio", silent.prompt)
        self.assertEqual(silent.debug["generated_voice_retention"], [])

    def test_errors(self):
        records = {"hero": character("i.png", "a.wav")}
        cases = [
            (prompt("{missing}"), "UNKNOWN_SAVED_RESOURCE"),
            (prompt("<location:missing>"), "UNKNOWN_TEMPORARY_RESOURCE"),
            (prompt("", declarations="<planet:world = Round.>"), "INVALID_TEMPORARY_TYPE"),
            (prompt("", declarations="<object:2bad = Thing.>"), "INVALID_TEMPORARY_NAME"),
            (prompt("", declarations="<object:box = >"), "MISSING_TEMPORARY_DESCRIPTION"),
            (prompt("", declarations="<object:box = Box.><object:box = Box.>"), "DUPLICATE_TEMPORARY_DECLARATION"),
            (prompt("<object:box = Box.>"), "INVALID_DECLARATION"),
            (prompt("<voice:alone>", declarations="<voice:alone = Voice.>"), "VOICE_WITHOUT_MATCHING_CHARACTER"),
            (prompt("{hero}", "{hero} says §hero§, <d>[English]{hero}</d>"), "REFERENCE_TAG_INSIDE_DIALOGUE"),
            (prompt("<Subject 1> is {hero}"), "AUTHORED_RUNTIME_SLOT"),
            ("summary:\n{hero}", "INVALID_SECTION"),
            (prompt("", "{hero} walks."), "MISSING_SUBJECT_DEFINITION"),
            (prompt("{hero}", "{hero} says §hero§ without a dialogue block."), "UNSUPPORTED_VOCAL_EVENT"),
        ]
        for source, code in cases:
            with self.subTest(code=code), self.assertRaisesRegex(ValueError, code):
                compiler.compile_prompt(source, records)

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

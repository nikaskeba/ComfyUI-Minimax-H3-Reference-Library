import importlib
import json
import unittest

from test_reference_compiler import compiler, character, prompt

preview = importlib.import_module(compiler.__package__ + ".compiler_template_preview").preview_reference


class PreviewTests(unittest.TestCase):
    def test_real_voice_and_custom_wording(self):
        record = character("a.png", "a.wav")
        result = preview("a", {"a": record}, json.dumps({"version": 1, "templates": {
            "voice_reference": "[[audio]] guides [[subject]][[speaker]]."}}))
        self.assertEqual(result["examples"]["voice_reference"], ["<Audio 1> guides <Subject 1> (S1)."])
        self.assertIn(result["examples"]["voice_reference"][0], result["prompt"])
        self.assertEqual(result["voice_description"], record["audio_description"])

    def test_no_voice_is_invented(self):
        result = preview("a_BC", {"a_BC": character("a.png")})
        self.assertFalse(result["has_audio"])
        self.assertNotIn("<Audio", result["prompt"])
        self.assertNotIn("voice_reference", result["examples"])

    def test_refmod_and_reuse(self):
        record = {**character(None, "refmod:a"), "video_file": "refmod:visual",
                  "_refmod_video": {"file": "a", "member": 0}, "_refmod_audio": {"file": "a", "member": 1}}
        for usage in ("reference", "reuse"):
            result = preview("a_rm", {"a_rm": record}, audio_usage=usage)
            self.assertIn("voice_" + usage, result["examples"])
            self.assertTrue(result["has_audio"])

    def test_location_and_music(self):
        for kind, assets in (("location", {"image_file": "room.png"}), ("music", {"audio_file": "music.wav"})):
            result = preview("item", {"item": {"reference_type": kind, "name": "Example", **assets}})
            for section in compiler.SECTIONS:
                self.assertIn(section + ":", result["prompt"])

    def test_errors(self):
        with self.assertRaisesRegex(ValueError, "no longer available"):
            preview("missing", {})
        with self.assertRaisesRegex(ValueError, "COMPILER_TEMPLATE"):
            preview("a", {"a": character("a.png")}, "invalid json")

    def test_capture_preserves_normal_output(self):
        records = {"a": character("a.png", "a.wav")}
        source = prompt("{a}", "{a} says, <d>[English]Hello.</d>")
        normal = compiler.compile_prompt(source, records)
        captured = {}
        observed = compiler.compile_prompt(source, records, template_preview=captured)
        self.assertEqual(normal.prompt, observed.prompt)
        self.assertEqual(normal.debug, observed.debug)
        self.assertEqual(normal.audios, observed.audios)
        self.assertTrue(captured)


if __name__ == "__main__":
    unittest.main()

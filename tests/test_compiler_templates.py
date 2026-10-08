import importlib
import json
import unittest

from test_reference_compiler import compiler, character, prompt

templates = importlib.import_module(compiler.__package__ + ".compiler_templates")


def config(**values):
    return json.dumps({"version": 1, "templates": values})


class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.records = {"a": character("a.png", "a.wav"), "b": character("b.png", "b.wav")}
        self.source = prompt("{a} {b}", "[Shot 1: 1s] {b} says, <d>[English]Hi.</d> [Shot 2: 4s] {a} says, <d>[English]Hello.</d>", summary="The room is bright.")

    def test_default_and_node_output_match(self):
        serialized = templates.SkebaH3CompilerTemplates().build(**templates.DEFAULTS)[0]
        old = compiler.compile_prompt(self.source, self.records)
        new = compiler.compile_prompt(self.source, self.records, compiler_templates=serialized)
        self.assertEqual(old.prompt, new.prompt)
        self.assertEqual(old.debug, new.debug)
        self.assertEqual(new.debug["compiler_templates"]["version"], 1)

    def test_overrides_keep_ownership_and_authored_content(self):
        overrides = config(subject_definition="[[subject]] depicts [[description]].",
            voice_reference="[[audio]] guides [[subject]][[speaker]].",
            voice_characteristics=" Voice: [[voice_description]]",
            global_binding="Bindings: [[bindings]].", dialogue_binding_reference=", guided by [[audio]],",
            summary_voice_reference="[[identity]] uses [[audio]].", retention_voice_reference="[[audio]]: reference for [[identity]].")
        for order in ("library_order", "first_speech"):
            original = compiler.compile_prompt(self.source, self.records, reference_order=order)
            result = compiler.compile_prompt(self.source, self.records, reference_order=order, compiler_templates=overrides)
            for key in ("resources", "pictures", "audio", "video", "speakers"):
                self.assertEqual(original.debug[key], result.debug[key])
            self.assertEqual(original.audios, result.audios)
            self.assertIn(" depicts ", result.prompt)
            self.assertIn("Bindings:", result.prompt)
            self.assertIn("The room is bright.", result.prompt)
            self.assertIn("<d>[English]Hi.</d>", result.prompt)
            self.assertNotEqual(original.debug["compiler_templates"]["hash"], result.debug["compiler_templates"]["hash"])

    def test_suppression_modes_and_sections(self):
        result = compiler.compile_prompt(self.source, self.records, compiler_templates=config(
            global_binding="", summary_task_prefix="", summary_voice_reference="", voice_characteristics="", retention_subject="", retention_voice_reference=""))
        self.assertNotIn("Voice-identity binding", result.prompt)
        self.assertNotIn("Voice characteristics", result.prompt)
        self.assertNotIn("fully_preserved", result.prompt)
        for section in compiler.SECTIONS:
            self.assertIn(section + ":", result.prompt)
        self.assertIn("summary:\n\nThe room is bright.", result.prompt)
        result = compiler.compile_prompt(self.source, self.records, voice_isolation=False, compiler_templates=config(global_binding="SHOULD NOT APPEAR", dialogue_binding_reference="SHOULD NOT APPEAR"))
        self.assertNotIn("SHOULD NOT APPEAR", result.prompt)

    def test_invalid_templates_and_runtime_labels(self):
        for text in ("bad json", "[]", '{"version":2,"templates":{}}', config(unknown="x"), config(voice_reference=3), config(voice_reference="[[typo]]"), config(voice_reference="[[audio]")):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, "COMPILER_TEMPLATE"):
                compiler.compile_prompt(self.source, self.records, compiler_templates=text)
        with self.assertRaisesRegex(ValueError, "AUDIO_SLOT_WITHOUT_ASSET"):
            compiler.compile_prompt(self.source, self.records, compiler_templates=config(voice_reference="<Audio 999>"))

    def test_refmods_reuse_and_temporary_text_only_voices(self):
        records = {"a": {**character(None, "refmod:a"), "video_file": "refmod:visual", "_refmod_video": {"file": "a", "member": 0}, "_refmod_audio": {"file": "a", "member": 1}}}
        source = prompt("{a}", "{a} says, <d>[English]Hello.</d>")
        for usage in ("reference", "reuse"):
            result = compiler.compile_prompt(source, records, audio_usage=usage, compiler_templates=config(**{"voice_"+usage: "[[audio]] assigned to [[subject]][[speaker]]."}))
            self.assertIn("<Audio 1> assigned to <Subject 1> (S1).", result.prompt)
            hidden = compiler.compile_prompt(source, records, refmod_subject_only=True, compiler_templates=config(voice_reference="DO NOT EMIT"))
            self.assertNotIn("DO NOT EMIT", hidden.prompt)
            self.assertEqual(result.audios, hidden.audios)
        source = prompt("<character:person = A person.>\n<voice:person = A warm American voice.>", "<character:person> says <voice:person>, <d>[English]Hello.</d>")
        result = compiler.compile_prompt(source, {}, compiler_templates=config(subject_definition="[[subject]] depicts [[description]]."))
        self.assertIn("<Subject 1> depicts A person.", result.prompt)
        self.assertEqual(result.audios, [])

    def test_literal_single_pass(self):
        value = templates.CompilerTemplates(config(subject_definition="<b>[[subject]]</b>: [[description]]"))
        self.assertEqual(value.render("subject_definition", subject="<Subject 1>", description="[[subject]]"), "<b><Subject 1></b>: [[subject]]")
        self.assertEqual(templates.CompilerTemplates(config()).hash, templates.CompilerTemplates().hash)

    def test_shared_voice_context_and_separate_identity_fields(self):
        self.records['a']['audio_description'] = 'A warm gravelly voice'
        self.records['b']['audio_description'] = 'A light crisp voice'
        overrides = config(retention_voice_reference=(
            '[[audio]]: reference - [[identity]] / [[subject_label]] / [[speaker_id]] '
            '/ [[speaker_tag]] / [[subject_number]] / [[speaker_number]]: [[voice_description]]'),
            summary_voice_reference='[[name]]: [[voice_description]] [[subject]][[speaker]] uses [[audio]].',
            dialogue_binding_reference=', with [[name]] voice: [[voice_description]],')
        for order in ('library_order', 'first_speech'):
            original = compiler.compile_prompt(self.source, self.records, reference_order=order)
            result = compiler.compile_prompt(self.source, self.records, reference_order=order, compiler_templates=overrides)
            self.assertEqual(original.audios, result.audios)
            for key in ('resources', 'pictures', 'audio', 'video', 'speakers'):
                self.assertEqual(original.debug[key], result.debug[key])
            self.assertIn('A warm gravelly voice.', result.prompt)
            self.assertIn('A light crisp voice.', result.prompt)
            if order == 'library_order':
                self.assertIn('<Audio 1>: reference - <Subject 1> (S2) / Subject 1 / S2 / <S2> / 1 / 2: A warm gravelly voice.', result.prompt)
            self.assertNotIn('[[', result.prompt)

    def test_every_field_accepts_shared_vocabulary(self):
        value = ' '.join('[[' + key + ']]' for key in templates.PLACEHOLDERS)
        custom = templates.CompilerTemplates(config(**{key: value for key in templates.DEFAULTS}))
        for key in templates.DEFAULTS:
            self.assertIn('warm', custom.render(key, voice_description='warm'))
            self.assertNotIn('[[', custom.render(key))

    def test_missing_context_does_not_borrow_audio_or_speaker(self):
        self.records['silent'] = character('silent.png', 'silent.wav')
        self.records['plain'] = character('plain.png', None)
        source = prompt('{a} {silent} {plain}', '[Shot 1: 1s] {plain} says, <d>[English]Hi.</d> [Shot 2: 3s] {a} says, <d>[English]Hello.</d>')
        result = compiler.compile_prompt(source, self.records, compiler_templates=config(
            subject_definition='[[subject]] is [[description]]. Voice=([[audio]]) Speaker=([[speaker_id]]).',
            summary_task_prefix='Global ([[subject]]) ([[voice_description]]) '))
        self.assertIn('Voice=() Speaker=(S1).', result.prompt)
        self.assertIn('Voice=() Speaker=().', result.prompt)
        self.assertIn('Global () ()', result.prompt)
        self.assertEqual(len(result.audios), 1)


if __name__ == "__main__":
    unittest.main()

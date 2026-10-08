import re
import unittest

from test_reference_compiler import compiler, character, prompt


class Ref2VAOutputTests(unittest.TestCase):
    def test_voice_characteristics_stay_with_the_assigned_audio_definition(self):
        description = "distinctively raspy, gravelly, and nasal tone with a casual, deadpan edge"
        records = {
            "alf": dict(reference_type="character", name="ALF", image_file="alf.png", audio_file="alf.wav", audio_description=description),
            "willy": dict(reference_type="character", name="Willy", image_file="willy.png", audio_file="willy.wav", audio_description=""),
            "silent": dict(reference_type="character", image_file="silent.png", audio_file="silent.wav", audio_description="Silent character description"),
        }
        source = prompt("{alf} {willy} {silent}", "[Shot 1: 1s] {willy} says, <d>[English]Hello.</d> [Shot 2: 3s] {alf} says, <d>[English]Hi.</d>")
        for order, number in [("first_speech", 2), ("library_order", 1)]:
            for usage in ("reference", "reuse"):
                for isolation in (True, False):
                    result = compiler.compile_prompt(source, records, reference_order=order, audio_usage=usage, voice_isolation=isolation)
                    definitions = result.prompt.split("summary:")[0]
                    line = next(line for line in definitions.splitlines() if line.startswith(f"<Audio {number}> is"))
                    self.assertIn(f"Voice characteristics: {description}.", line)
                    self.assertEqual(result.prompt.count(description), 1)
                    self.assertNotIn("Silent character description", result.prompt)
                    self.assertEqual(result.debug["resources"]["saved:alf"]["speaker"], 2)
        records["alf"]["audio_description"] = "Raspy delivery."
        result = compiler.compile_prompt(source, records)
        self.assertIn("Voice characteristics: Raspy delivery.", result.prompt)
        self.assertNotIn("delivery..", result.prompt)


    def test_timed_shot_markers_preserve_speakers_and_retention(self):
        records = {"a": character("a.png", "a.wav"), "b": character("b.png", "b.wav")}
        detail = ("[Shot 1: 0s] {a} waits.\n[Shot 2: 1.0s] {b} says, <d>[English]Hello.</d>\n"
                  "[Shot 3: 4.5s] {a} says, <d>[English]Hi.</d>\n[Shot 4: 8.2s] {b} waits.")
        result = compiler.compile_prompt('[s=10]\n' + prompt('{a}\n{b}', detail), records)
        self.assertEqual(result.debug['speakers'], {'1': 'saved:b', '2': 'saved:a'})
        self.assertIn('<Subject 1> (appears in [Shot 2], [Shot 4])', result.prompt)
        self.assertIn('<Subject 2> (appears in [Shot 1], [Shot 3])', result.prompt)
        for marker in ('[Shot 1: 0s]', '[Shot 2: 1.0s]', '[Shot 3: 4.5s]', '[Shot 4: 8.2s]'):
            self.assertIn(marker, result.prompt)

    def test_first_speech_controls_speaker_ids_independently_of_audio(self):
        records = {
            "second": dict(reference_type="character", name="Second", image_file="second.png", audio_file="second.wav"),
            "silent": dict(reference_type="character", name="Silent", image_file="silent.png", audio_file="silent.wav"),
            "first": dict(reference_type="character", name="First", image_file="first.png"),
        }
        for second_cue in ("[English]", "[English §second§]"):
            source = prompt("{second}\n{silent}\n{first}",
                "[Shot 1] {second} stands beside {silent}. {first} enters.\n"
                "[Shot 2] {first} says, <d>[English]I speak first.</d>\n"
                f"[Shot 3] {{second}} says, <d>{second_cue}I speak second.</d>\n"
                "[Shot 4] {first} says, <d>[English]Back again.</d>\n"
                "[Shot 5] {second} (off-screen) says, <d>[English]Me too.</d>",
                summary="{second} and {silent} stand beside {first}.")
            result = compiler.compile_prompt(source, records)
            self.assertEqual(result.debug["speakers"], {"1": "saved:first", "2": "saved:second"})
            self.assertEqual(result.debug["audio"], {"1": "saved:second"})
            self.assertEqual(result.audios, ["second"])
            self.assertIsNone(result.debug["resources"]["saved:silent"]["speaker"])
            self.assertEqual(result.prompt.count("<Subject 1> (S1) says,"), 2)
            self.assertIn("<Audio 1> is the voice-timbre reference for <Subject 2> (S2).", result.prompt)
            self.assertEqual(result.prompt.count("<Subject 2> (S2), using the voice identity referenced exclusively from <Audio 1>,"), 2)

    def test_audio_definitions_name_the_resolved_character(self):
        records = {
            "Kryten_rm": dict(reference_type="character", audio_file="k.wav", _refmod_audio={"member": 1}),
            "Rimmer_BC": dict(reference_type="character", name="Arnold Rimmer", audio_file="r.wav"),
        }
        source = prompt("{Kryten_rm}\n{Rimmer_BC}",
                        "{Kryten_rm} says, <d>[English]Ready.</d>\n{Rimmer_BC} says, <d>[English]Good.</d>")
        result = compiler.compile_prompt(source, records)
        self.assertIn("<Audio 1> applies exclusively to <Subject 1> (S1) and provides Kryten’s vocal timbre and delivery.", result.prompt)
        self.assertIn("<Audio 2> applies exclusively to <Subject 2> (S2) and provides Arnold Rimmer’s vocal timbre and delivery.", result.prompt)
        self.assertEqual(result.audios, ["Kryten_rm", "Rimmer_BC"])
        self.assertNotIn("British", result.prompt)
        disabled = compiler.compile_prompt(source, records, voice_isolation=False)
        for name, number in (("Kryten", 1), ("Arnold Rimmer", 2)):
            self.assertIn(
                f"<Audio {number}> is the voice-timbre reference for <Subject {number}> (S{number}). "
                f"<Audio {number}> applies exclusively to <Subject {number}> (S{number}) and provides {name}’s vocal timbre and delivery.",
                disabled.prompt)
        reused = compiler.compile_prompt(source, records, audio_usage="reuse")
        self.assertNotIn("provides Kryten’s vocal timbre", reused.prompt)

    def test_refmod_layout_keeps_native_pictures_and_single_task_prefix(self):
        records = {
            "robot": {**character(audio="robot.wav"), "video_file": "robot.refmod", "_refmod_video": {"member": 0}},
            "officer": {**character(audio="officer.wav"), "video_file": "officer.refmod", "_refmod_video": {"member": 0}},
            "room": dict(reference_type="location", image_file="room.png", additional_images=[{"image_file": "panorama.png", "description": "Room panorama"}]),
        }
        binding = "<Audio 1> exclusively provides the voice-timbre reference for <Subject 1> (S1)."
        source = prompt("{robot}\n{officer}\n{room}",
            "[Shot 1] {robot} in {room}.\n[Shot 2] {robot} says, <d>[English]Ready.</d>\n[Shot 3] {officer} says, <d>[English]Good.</d>",
            summary="[reference generation + audio reference] The room is quiet.")
        result = compiler.compile_prompt(source, records)
        self.check_sections(result)
        self.assertNotIn(" in <Video", result.prompt)
        self.assertIn("in <Picture 1>, <Picture 2>", result.prompt)
        self.assertEqual(result.videos, ["robot", "officer"])
        self.assertEqual(result.audios, ["robot", "officer"])
        self.assertEqual(result.debug["video"], {"1": "saved:robot", "2": "saved:officer"})
        summary = result.prompt.split("summary:\n\n")[1].split("\n\nretention_analysis:")[0]
        self.assertEqual(summary.count(binding), 1)
        self.assertEqual(summary.count("[reference generation + audio reference]"), 1)
        self.assertIn("<Audio 2> exclusively provides the voice-timbre reference for <Subject 2> (S2).", summary)

    def check_sections(self, result):
        self.assertEqual(tuple(compiler.HEADER.findall(result.prompt)), compiler.SECTIONS)

    def test_one_two_three_voices_and_returning_speakers(self):
        for count in (1, 2, 3):
            with self.subTest(count=count):
                records = {str(i): character(f'{i}.png', f'{i}.wav') for i in range(count)}
                detail = '\n'.join(f'[Shot {i+1}] At 00:0{i}.000, {{{i}}} says, <d>[English]Line {i}.</d>' for i in range(count))
                detail += f'\n[Shot {count+1}] {{0}} says, <d>[English]Again.</d>'
                source = prompt('\n'.join('{'+i+'}' for i in records), detail)
                source = source.replace('summary:\n\n\n', '').replace('retention_analysis:\n\n\n', '')
                result = compiler.compile_prompt(source, records)
                self.check_sections(result)
                definitions = result.prompt.split("subject_definitions:", 1)[1].split("summary:", 1)[0]
                starts = re.findall(r"^<(Subject|Audio) (\d+)>", definitions, re.M)
                self.assertEqual(starts, [(kind, str(i+1)) for i in range(count) for kind in ("Subject", "Audio")])
                self.assertEqual(result.images, list(records))
                self.assertEqual(result.audios, list(records))
                self.assertEqual(compiler.DIALOGUE.findall(result.prompt), compiler.DIALOGUE.findall(source))
                self.assertEqual(result.debug['speakers'], {str(i+1): 'saved:'+str(i) for i in range(count)})
                self.assertEqual('Voice-identity binding is strict' in result.prompt, count >= 2)
                for i in range(count):
                    n = i+1
                    if count >= 2:
                        self.assertIn(f'<Subject {n}> = S{n} = <Audio {n}>', result.prompt)
                    local = f'<Subject {n}> (S{n}), using the voice identity referenced exclusively from <Audio {n}>, says,'
                    self.assertEqual(result.prompt.count(local), 2 if i == 0 else 1)
                    self.assertIn(
                        f"<Audio {n}>: reference - its vocal timbre and delivery guide only the dialogue "
                        f"produced by <Subject {n}> (S{n}), without copying the original audio signal.",
                        result.prompt)
                self.assertIn(f'<Subject 1> (appears in [Shot 1], [Shot {count+1}])', result.prompt)
                self.assertNotIn('must not use or imitate', result.prompt)

    def test_sparse_audio_silent_character_location_and_offscreen_return(self):
        records = {'text': character(), 'jay': character('jay.png', 'jay.wav'),
                   'al': character('al.png', 'al.wav'), 'silent': character('silent.png', 'silent.wav'),
                   'room': dict(reference_type='location', image_file='room.png'),
                   'clip': dict(reference_type='video', video_file='clip.mp4', video_has_audio=True)}
        detail = ('[Shot 1] {text} says, <d>[English]Hi.</d>\n'
                  '[Shot 2] Only {jay} inside {room}. {jay} says, <d>[English]Jay.</d>\n'
                  '[Shot 3] {al} says, <d>[English]Al.</d> {silent} watches.\n'
                  '[Shot 4] {jay} (off-screen) says, <d>[English]Again.</d>')
        result = compiler.compile_prompt(prompt('{text}\n{jay}\n{al}\n{silent}\n{room}', detail, sound='Reference §clip§.'), records)
        self.check_sections(result)
        self.assertEqual(result.debug['audio'], {'1': 'saved:clip', '2': 'saved:jay', '3': 'saved:al'})
        self.assertEqual(result.debug['speakers'], {'1': 'saved:text', '2': 'saved:jay', '3': 'saved:al'})
        self.assertEqual(result.audios, ['jay', 'al'])
        self.assertIn('<Subject 1> (S1) says, <d>[English]Hi.</d>', result.prompt)
        self.assertNotIn('<Subject 1> = S1 =', result.prompt)
        self.assertIn('<Subject 2> (appears in [Shot 2]):', result.prompt)
        self.assertNotIn('<Subject 2> (appears in [Shot 2], [Shot 4])', result.prompt)
        for tag in ('silent', 'room'):
            resource = result.debug['resources']['saved:'+tag]
            self.assertIsNone(resource['speaker'])
            self.assertIsNone(resource['audio'])

    def test_audio_numbers_differ_from_subjects(self):
        records = {'jay': character('jay.png', 'jay.wav'), 'al': character('al.png', 'al.wav'),
                   'clip': dict(reference_type='video', video_file='clip.mp4', video_has_audio=True)}
        source = prompt('{jay}\n{al}', '[Shot 1] {jay} says, <d>[English]Jay.</d>\n[Shot 2] {al} says, <d>[English]Al.</d>', sound='Use §clip§.')
        result = compiler.compile_prompt(source, records)
        self.check_sections(result)
        self.assertIn('<Subject 1> = S1 = <Audio 2>; <Subject 2> = S2 = <Audio 3>.', result.prompt)
        self.assertNotIn('<Subject 1> = S1 = <Audio 1>', result.prompt)
        definitions = result.prompt.split("subject_definitions:", 1)[1].split("summary:", 1)[0]
        self.assertEqual(re.findall(r"^<Audio (\d+)>", definitions, re.M), ["2", "3", "1"])
        self.assertLess(definitions.index("<Subject 2> is"), definitions.index("<Audio 1> is"))
        disabled = compiler.compile_prompt(source, records, voice_isolation=False)
        for key in ('resources', 'pictures', 'audio', 'video', 'speakers'):
            self.assertEqual(result.debug[key], disabled.debug[key])

    def test_explicit_visual_discriminators_and_control_tags_survive(self):
        records = {'jay': character('jay.png', 'jay.wav'), 'al': character('al.png', 'al.wav')}
        definitions = '{jay} wears rectangular eyeglasses.\n{al} wears no glasses.'
        detail = '[Shot 1] {jay} wears rectangular eyeglasses. {jay} says, <d>[English]Future.</d>\n[Shot 2] At 00:04.000, {al} wears no glasses. {al} says, <d>[English]Really?</d>'
        result = compiler.compile_prompt('[new_location] [s=12]\n'+prompt(definitions, detail), records)
        self.check_sections(result)
        self.assertTrue(result.prompt.startswith('[new_location] [s=12]'))
        sections = re.split(r'^\w+:\s*$', result.prompt, flags=re.M)
        self.assertIn('wears rectangular eyeglasses.', sections[1])
        self.assertNotIn('eyeglasses', sections[2])
        self.assertIn('wears no glasses.', sections[1])
        self.assertNotIn('glasses', sections[2])
        self.assertIn('At 00:04.000', result.prompt)
        self.assertEqual(compiler.DIALOGUE.findall(result.prompt), compiler.DIALOGUE.findall(detail))

    def test_summary_only_swaps_tags_without_appending_identity_or_wardrobe(self):
        records = {"george": character("george.png", "george.wav"),
                   "newman": character("newman.png", "newman.wav"),
                   "gate": dict(reference_type="location", image_file="gate.png")}
        definitions = ("{george} Image context: bald man, with glasses. "
                       "Wardrobe: wearing a muted shirt and dark trousers. This exact wardrobe remains fixed.\n"
                       "{newman} Wardrobe: wearing a white angel robe and feathered wings.\n{gate}")
        summary = ("The target video shows live-action sitcom photography inside {gate}. "
                   "{george} stands among luminous clouds. {newman} remains beside the gate. "
                   "George gestures toward himself. Newman remains composed and stern.")
        result = compiler.compile_prompt(prompt(definitions,
            "{george} says, <d>[English]Hello.</d> {newman} says, <d>[English]Welcome.</d>",
            summary=summary), records)
        actual = result.prompt.split("summary:\n\n", 1)[1].split("\n\nretention_analysis:", 1)[0]
        expected = summary.replace("{gate}", "<Subject 3>").replace("{george}", "<Subject 1>").replace("{newman}", "<Subject 2>")
        self.assertEqual(actual, "[reference generation + audio reference] " + expected +
                         " <Audio 1> exclusively provides the voice-timbre reference for <Subject 1> (S1)." +
                         " <Audio 2> exclusively provides the voice-timbre reference for <Subject 2> (S2).")
        self.assertIn("Image context: bald man, with glasses.", result.prompt.split("summary:")[0])
        self.assertIn("Wardrobe: wearing a white angel robe", result.prompt.split("summary:")[0])

    def test_subject_only_refmod_audio_keeps_ordinary_voice_binding(self):
        records = {"ordinary": character("face.png", "voice.wav"),
                   "mod": {**character("mod.png", "mod.wav"), "_refmod_audio": {"member": 1}}}
        for cue in ("[English]", "[English §mod§]"):
            source = prompt("{ordinary}\n{mod}\n§mod§",
                            "{ordinary} says, <d>[English]First.</d>\n"
                            "{mod} says, <d>" + cue + "Second.</d>")
            normal = compiler.compile_prompt(source, records)
            simple = compiler.compile_prompt(source, records, refmod_subject_only=True)
            self.assertIn("<Audio 1> is the voice-timbre reference", simple.prompt)
            self.assertNotIn("<Audio 2>", simple.prompt)
            self.assertIn("<Subject 2> (S2) says,", simple.prompt)
            self.assertEqual(normal.audios, simple.audios)
            for key in ("resources", "audio", "speakers"):
                self.assertEqual(normal.debug[key], simple.debug[key])

    def test_temporary_speaker_has_no_fabricated_audio(self):
        source = prompt('<character:guest = An older clean-shaven guest.>\n<location:room = A quiet room.>',
                        '[Shot 1] <character:guest> in <location:room> says, <d>[French]Bonjour.</d>\n[Shot 2] <character:guest> says, <d>[French]Encore.</d>')
        result = compiler.compile_prompt(source, {})
        self.check_sections(result)
        self.assertNotIn('<Audio', result.prompt)
        self.assertIn('(S1)', result.prompt)
        self.assertNotIn('(S2)', result.prompt)


if __name__ == '__main__':
    unittest.main()

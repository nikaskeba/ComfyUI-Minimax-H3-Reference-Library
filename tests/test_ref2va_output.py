import re
import unittest

from test_reference_compiler import compiler, character, prompt


class Ref2VAOutputTests(unittest.TestCase):
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
                    self.assertIn(f'<Audio {n}>: reference - its vocal timbre and delivery guide only <Subject {n}> (S{n})', result.prompt)
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
        self.assertIn('<Subject 1> wears rectangular eyeglasses.', sections[2])
        self.assertIn('<Subject 2> wears no glasses.', sections[2])
        self.assertIn('At 00:04.000', result.prompt)
        self.assertEqual(compiler.DIALOGUE.findall(result.prompt), compiler.DIALOGUE.findall(detail))

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

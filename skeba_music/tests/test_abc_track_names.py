import importlib.util
from io import BytesIO
from pathlib import Path
import unittest

import pretty_midi
from symusic import Score


ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("skeba_abc_track_names", ROOT / "abc_track_names.py")
labels = importlib.util.module_from_spec(spec)
spec.loader.exec_module(labels)


class ABCTrackNameTests(unittest.TestCase):
    def test_declared_voices_keep_names_when_both_have_notes(self):
        abc = (ROOT / "examples" / "two_voices.abc").read_text(encoding="utf-8")
        score = Score.from_abc(abc)
        labels.label_abc_tracks(abc, score)
        self.assertEqual([track.name for track in score.tracks], ["Vocal Melody", "Ins Melody"])

    def test_silent_vocal_and_chord_generated_tracks_are_named_honestly(self):
        abc = '''X:1
T:
M:4/4
L:1/16
Q:1/4=128
V: Vocal clef=treble name="Vocal Melody" snm="Vocal"
V: Ins clef=treble name="Ins Melody" snm="Inst."
K:Am
V: Vocal
"Em/G"z16|"F"z16|
V: Ins
G,2B,2E2G,2B,2E2G,2B,2|E2G,2B,2E2G,2B,2E2G,2|
'''
        score = Score.from_abc(abc)
        labels.label_abc_tracks(abc, score)
        self.assertEqual([track.name for track in score.tracks],
                         ["Chord-derived 1", "Chord-derived 2", "Ins Melody"])
        exported = pretty_midi.PrettyMIDI(BytesIO(score.dumps_midi()))
        self.assertEqual([track.name for track in exported.instruments],
                         ["Chord-derived 1", "Chord-derived 2", "Ins Melody"])

    def test_unknown_voice_keeps_its_identifier(self):
        abc = "X:1\nM:4/4\nL:1/8\nQ:1/4=120\nV: A\nK:C\nV: A\nCDEF|\n"
        score = Score.from_abc(abc)
        labels.label_abc_tracks(abc, score)
        self.assertEqual([track.name for track in score.tracks], ["A"])


if __name__ == "__main__":
    unittest.main()

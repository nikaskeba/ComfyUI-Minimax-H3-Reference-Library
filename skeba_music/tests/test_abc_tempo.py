import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
MUSIC = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("skeba_abc_tempo", MUSIC / "abc_tempo.py")
tempo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tempo)


class SharedTempoTests(unittest.TestCase):
    def test_zero_preserves_original_exactly(self):
        abc = "X:1\r\nM:4/4\r\nQ:1/4=159\r\nK:C\r\nCDEF|\r\n"
        self.assertEqual(tempo.set_abc_tempo(abc), abc)

    def test_override_changes_only_tempo_line(self):
        abc = "X:1\nT:Test\nM:4/4\nQ:1/4=159\nK:C\nCDEF|\n"
        expected = abc.replace("Q:1/4=159", "Q:1/4=160")
        self.assertEqual(tempo.set_abc_tempo(abc, 160), expected)
        self.assertEqual(tempo.SkebaABCSharedTempo.execute(abc, 160).result[0], expected)

    def test_rejects_invalid_tempo_or_ambiguous_score(self):
        with self.assertRaisesRegex(ValueError, "between 20 and 400"):
            tempo.set_abc_tempo("Q:120", 10)
        with self.assertRaisesRegex(ValueError, "exactly one"):
            tempo.set_abc_tempo("X:1\nK:C\nCDEF|", 160)
        with self.assertRaisesRegex(ValueError, "exactly one"):
            tempo.set_abc_tempo("Q:120\nQ:130", 160)


if __name__ == "__main__":
    unittest.main()

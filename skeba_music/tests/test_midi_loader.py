import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
import folder_paths


MUSIC = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("skeba_midi_loader", MUSIC / "midi_loader.py")
loader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loader)


class MIDILoaderTests(unittest.TestCase):
    def test_input_and_output_files_connect_to_converter(self):
        data = (MUSIC / "examples" / "two_voices.mid").read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            input_root = Path(directory) / "input"
            output_root = Path(directory) / "output"
            (input_root / "nested").mkdir(parents=True)
            output_root.mkdir()
            (input_root / "nested" / "song.mid").write_bytes(data)
            (output_root / "render.MIDI").write_bytes(data)
            with patch.object(folder_paths, "get_input_directory", return_value=str(input_root)), \
                 patch.object(folder_paths, "get_output_directory", return_value=str(output_root)):
                self.assertEqual(loader.midi_files(), ["input/nested/song.mid", "output/render.MIDI"])
                self.assertEqual(loader.load_midi("input/nested/song.mid"), data)
                self.assertEqual(loader.SkebaLoadMIDI.execute("output/render.MIDI").result[0], data)

    def test_rejects_outside_paths_and_invalid_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_root = root / "input"
            output_root = root / "output"
            input_root.mkdir()
            output_root.mkdir()
            (input_root / "bad.mid").write_bytes(b"bad")
            with patch.object(folder_paths, "get_input_directory", return_value=str(input_root)), \
                 patch.object(folder_paths, "get_output_directory", return_value=str(output_root)):
                with self.assertRaisesRegex(ValueError, "stay inside"):
                    loader.load_midi("input/../output/else.mid")
                with self.assertRaisesRegex(ValueError, "not a readable MIDI"):
                    loader.load_midi("input/bad.mid")
                with self.assertRaises(FileNotFoundError):
                    loader.load_midi("input/missing.mid")


if __name__ == "__main__":
    unittest.main()

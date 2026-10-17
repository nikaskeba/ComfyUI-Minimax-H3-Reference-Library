import importlib.util
import io
import json
import math
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import mido
import torch
import huggingface_hub

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "custom_nodes/ComfyUI-MuScriptor"))
import folder_paths

if "muscriptor" not in sys.modules:
    package = types.ModuleType("muscriptor")
    package.__path__ = [str(ROOT / "custom_nodes/ComfyUI-MuScriptor")]
    sys.modules["muscriptor"] = package

from muscriptor.events import NoteStartEvent, NoteEndEvent
from muscriptor.tokenizer.mt3 import MT3_FULL_PLUS_GROUP_NAMES

spec = importlib.util.spec_from_file_location("skeba_muscriptor_grid", Path(__file__).parents[1] / "muscriptor_grid.py")
grid = importlib.util.module_from_spec(spec)
spec.loader.exec_module(grid)


def abc(qpm=120, meter="4/4", bars="CDEF GABc|"):
    return f"X:1\nT:Grid\nM:{meter}\nL:1/8\nQ:1/4={qpm}\nK:C\n{bars}"


def pair(index, start, end, pitch=60, instrument="piano"):
    event = NoteStartEvent(pitch, start, index, instrument)
    return [event, NoteEndEvent(end, event)]


class GridTests(unittest.TestCase):
    def test_sheetsage_beat_map_corrects_uniform_tempo_drift(self):
        # The decoded song beats are 0.52s apart, while its rounded ABC is 120 BPM.
        beat_map = grid.parse_beat_map(json.dumps({
            "version": 1, "source_duration": 6.24,
            "times": [index * 0.52 for index in range(13)],
            "quarters": list(range(13)),
        }))
        events = pair(1, 4.16, 4.42)
        uniform, _ = grid.quantize_events(events, 120, lambda _: 0, "Skip malformed")
        aligned, _ = grid.quantize_events(events, 120, lambda _: 0, "Skip malformed", beat_map)
        self.assertEqual(uniform[0]["start_tick"], 3960)
        self.assertEqual(aligned[0]["start_tick"], 3840)
        self.assertEqual(aligned[0]["end_tick"], 4080)

    def test_beat_map_validation_and_pickup_offset(self):
        for payload in ('{"version":2}', '{"version":1,"times":[0,1],"quarters":[0,0],"source_duration":1}',
                        '{"version":1,"times":[0,1],"quarters":[0,1],"source_duration":0}'):
            with self.assertRaisesRegex(ValueError, "beat_map"):
                grid.parse_beat_map(payload)
        beat_map = grid.parse_beat_map(json.dumps({"version": 1, "source_duration": 2,
            "times": [0.5, 1.0, 1.5, 2.0], "quarters": [3, 4, 5, 6]}))
        notes, _ = grid.quantize_events(pair(1, 0.5, 1.0), 120, lambda _: 0,
                                        "Skip malformed", beat_map)
        self.assertEqual((notes[0]["start_tick"], notes[0]["end_tick"]), (1440, 1920))

    def test_picker_lists_every_model_instrument_drums_first(self):
        self.assertEqual(grid.INSTRUMENT_OPTIONS[0], "drums")
        self.assertEqual(set(grid.INSTRUMENT_OPTIONS), set(MT3_FULL_PLUS_GROUP_NAMES))
        schema = grid.SkebaMuScriptorGrid.define_schema()
        field = next(item for item in schema.inputs if item.id == "instruments")
        self.assertEqual(field.extra_dict["instrumentOptions"], list(grid.INSTRUMENT_OPTIONS))

    def test_cached_model_uses_local_path(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "model.safetensors"
            checkpoint.write_bytes(b"checkpoint")
            (checkpoint.parent / "config.json").write_text("{}")
            with patch.object(huggingface_hub, "try_to_load_from_cache", return_value=str(checkpoint)) as lookup:
                self.assertEqual(grid.local_model_source("large"), checkpoint)
                self.assertEqual(lookup.call_count, 1)
            with patch.object(huggingface_hub, "try_to_load_from_cache", return_value=None):
                self.assertEqual(grid.local_model_source("medium"), "medium")

    def test_abc_tempo_meter_and_grid(self):
        for bpm, meter in ((120, "4/4"), (128, "3/4"), (120, "6/8")):
            qpm, top, bottom, _ = grid.parse_abc_grid(abc(bpm, meter))
            self.assertAlmostEqual(qpm, bpm)
            self.assertEqual(f"{top}/{bottom}", meter)
            notes, skipped = grid.quantize_events(pair(1, 0.14, 0.92), qpm, lambda _: 0, "Skip malformed")
            self.assertEqual(skipped, 0)
            midi = mido.MidiFile(file=io.BytesIO(grid.encode_midi(notes, qpm, top, bottom)))
            self.assertEqual(midi.type, 1)
            self.assertEqual(midi.tracks[0][0].tempo, round(60_000_000 / bpm))
            self.assertEqual((midi.tracks[0][1].numerator, midi.tracks[0][1].denominator), (top, bottom))
            self.assertTrue(all(note["start_tick"] % 120 == note["end_tick"] % 120 == 0 for note in notes))

    def test_short_sustain_retrigger_and_drum_tracks(self):
        events = pair(1, 0.01, 0.02) + pair(2, 1.0, 3.0) + pair(3, 2.0, 2.4)
        events += pair(4, 1.04, 1.06, 38, "drums")
        events += pair(5, 0.5, 1.0, 67, "violin")
        notes, skipped = grid.quantize_events(events, 120, lambda name: {"piano": 0, "violin": 40}[name], "Skip malformed")
        self.assertEqual(skipped, 0)
        self.assertEqual(notes[0]["end_tick"] - notes[0]["start_tick"], 120)
        piano = [note for note in notes if note["instrument"] == "piano" and note["start_tick"] >= 960]
        self.assertEqual(piano[0]["end_tick"], piano[1]["start_tick"])
        data = grid.encode_midi(notes, 120, 4, 4)
        midi = mido.MidiFile(file=io.BytesIO(data))
        self.assertEqual(len(midi.tracks), 4)
        self.assertTrue(any(msg.type == "note_on" and msg.channel == 9 for track in midi.tracks for msg in track))
        self.assertEqual(len(json.loads(grid.notes_to_json(notes, 120))), len(notes))

    def test_invalid_notes_skip_and_strict(self):
        bad = pair(1, 0, 1, pitch=128) + pair(2, math.nan, 1) + pair(3, 2, 1)
        bad += pair(4, 0, 1, instrument="impossible")
        dangling = NoteStartEvent(60, 1, 5, "piano")
        bad.append(dangling)
        bad.append(NoteEndEvent(1, NoteStartEvent(60, 0, 6, "piano")))
        bad += pair(7, 0.1, 0.11)
        mapping = lambda name: {"piano": 0}[name]
        notes, skipped = grid.quantize_events(bad, 120, mapping, "Skip malformed")
        self.assertEqual((len(notes), skipped), (1, 6))
        with self.assertRaisesRegex(ValueError, "Malformed MuScriptor note"):
            grid.quantize_events(bad, 120, mapping, "Strict error")

    def test_abc_validation(self):
        for text in ("", "X:1\nM:4/4\nK:C\nC|", "X:1\nQ:120\nK:C\nC|"):
            with self.assertRaisesRegex(ValueError, "ABC"):
                grid.parse_abc_grid(text)

    def test_node_saves_identical_bytes_and_json_without_stretch(self):
        class Model:
            def transcribe(self, **kwargs):
                self.audio = kwargs["audio"]
                return iter(pair(1, 9.9, 10.1))

            def _program_for_instrument(self, name):
                return 0

        model = Model()
        faux = types.ModuleType("muscriptor.comfy_node")
        faux.get_model = lambda *args: model
        faux.resolve_instrument_names = lambda tokens: tokens
        with tempfile.TemporaryDirectory() as directory, patch.dict(sys.modules, {"muscriptor.comfy_node": faux}), patch.object(folder_paths, "get_output_directory", return_value=directory):
            audio = {"waveform": torch.zeros(1, 1, 16000 * 12), "sample_rate": 16000}
            result = grid.SkebaMuScriptorGrid.execute(abc=abc(), model_size="small", device="cpu", dtype="float32",
                use_sampling=False, temperature=1, cfg_coef=1, beam_size=1, prelude_forcing=True,
                strict_eos=False, filename_prefix="grid", audio=audio)
            path, notes_json, midi_bytes = result.result
            self.assertEqual(Path(path).read_bytes(), midi_bytes)
            notes = json.loads(notes_json)
            self.assertAlmostEqual(notes[0]["start_time"], 9.875)
            self.assertEqual(notes[0]["start_tick"] % 120, 0)
            self.assertIsInstance(model.audio, tuple)

    def test_tempo_override_uses_song_bpm_for_grid_and_export(self):
        class Model:
            def transcribe(self, **kwargs):
                return iter(pair(1, 10.0, 10.2))

            def _program_for_instrument(self, name):
                return 0

        faux = types.ModuleType("muscriptor.comfy_node")
        faux.get_model = lambda *args: Model()
        faux.resolve_instrument_names = lambda tokens: tokens
        with tempfile.TemporaryDirectory() as directory, patch.dict(sys.modules, {"muscriptor.comfy_node": faux}), patch.object(folder_paths, "get_output_directory", return_value=directory):
            audio = {"waveform": torch.zeros(1, 1, 16000 * 12), "sample_rate": 16000}
            kwargs = dict(abc=abc(159), model_size="small", device="cpu", dtype="float32",
                          use_sampling=False, temperature=1, cfg_coef=1, beam_size=1,
                          prelude_forcing=True, strict_eos=False, filename_prefix="grid", audio=audio)
            default = grid.SkebaMuScriptorGrid.execute(**kwargs).result
            corrected = grid.SkebaMuScriptorGrid.execute(**kwargs, tempo_override_bpm=160).result
            self.assertEqual(json.loads(default[1])[0]["start_tick"], 12720)
            self.assertEqual(json.loads(corrected[1])[0]["start_tick"], 12840)
            midi = mido.MidiFile(file=io.BytesIO(corrected[2]))
            self.assertEqual(midi.tracks[0][0].tempo, 375000)
            self.assertEqual(mido.MidiFile(file=io.BytesIO(default[2])).tracks[0][0].tempo, round(60_000_000 / 159))
            with self.assertRaisesRegex(ValueError, "tempo_override_bpm"):
                grid.SkebaMuScriptorGrid.execute(**kwargs, tempo_override_bpm=10)


if __name__ == "__main__":
    unittest.main()

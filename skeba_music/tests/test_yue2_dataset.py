import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import soundfile as sf
import torch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
import folder_paths
sys.modules.setdefault('nodes', types.ModuleType('nodes'))
sys.modules['nodes'].NODE_CLASS_MAPPINGS = {}
spec = importlib.util.spec_from_file_location('skeba_yue2_dataset', Path(__file__).parents[1] / 'yue2_dataset.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DatasetTests(unittest.TestCase):
    def test_lossless_tracks_batch_rates_and_stable_cache(self):
        tracks = {'audio_10': {'waveform': torch.rand(2, 2, 100), 'sample_rate': 48000},
                  'audio_2': {'waveform': torch.rand(1, 1, 80), 'sample_rate': 16000}}
        originals = {key: value['waveform'].clone() for key, value in tracks.items()}
        with tempfile.TemporaryDirectory() as root:
            folder = module.stage_tracks(tracks, root)
            files = sorted(folder.glob('*.wav'))
            self.assertEqual(len(files), 3)
            data, rate = sf.read(files[0], dtype='float32', always_2d=True)
            self.assertEqual(rate, 16000)
            self.assertTrue(torch.equal(torch.from_numpy(data.T), originals['audio_2'][0]))
            before = [p.stat().st_mtime_ns for p in files]
            self.assertEqual(module.stage_tracks(tracks, root), folder)
            self.assertEqual([p.stat().st_mtime_ns for p in files], before)
            tracks['audio_2']['waveform'] = tracks['audio_2']['waveform'] + .01
            self.assertNotEqual(module.stage_tracks(tracks, root), folder)
        self.assertTrue(torch.equal(tracks['audio_10']['waveform'], originals['audio_10']))

    def test_native_builder_contract_and_cache_isolation(self):
        calls = []
        dataset = object()
        class Trainer:
            def build(self, *args):
                calls.append(args)
                return dataset, 'native summary'
        tracks = {'audio_0': {'waveform': torch.zeros(1, 2, 20), 'sample_rate': 48000}}
        with tempfile.TemporaryDirectory() as root:
            checkpoint = Path(root) / 'model'; checkpoint.write_bytes(b'model')
            with patch.dict(module.nodes.NODE_CLASS_MAPPINGS, YuE2TrainingDataset=Trainer), patch.object(folder_paths, 'get_full_path_or_raise', return_value=str(checkpoint)):
                output = module.SkebaYuE2TrainingDataset.execute('model', tracks, 10, 'default', 'Jazz', root, True)
                self.assertIs(output.result[0], dataset)
                self.assertEqual(calls[0][2:5], (10, 'default', 'Jazz'))
                self.assertTrue(calls[0][-1])
                module.SkebaYuE2TrainingDataset.execute('model', tracks, 5, 'none', '', root)
                self.assertNotEqual(calls[0][5], calls[1][5])
                checkpoint.write_bytes(b'new checkpoint')
                module.SkebaYuE2TrainingDataset.execute('model', tracks, 10, 'default', 'New caption', root)
                self.assertNotEqual(calls[0][5], calls[2][5])

    def test_native_dataset_clipping_and_captions(self):
        import numpy as np
        source = ROOT / 'custom_nodes/ComfyUI-YuE2-Trainer/trainer_core/data.py'
        native_spec = importlib.util.spec_from_file_location('native_yue2_test_data', source)
        native = importlib.util.module_from_spec(native_spec)
        sys.modules[native_spec.name] = native
        native_spec.loader.exec_module(native)
        tracks = {'audio_0': {'waveform': torch.zeros(1, 2, 48000 * 3), 'sample_rate': 48000}}
        with tempfile.TemporaryDirectory() as root:
            folder = module.stage_tracks(tracks, root)
            cache = Path(root) / 'latents'
            with patch.object(native, 'encode_file_latents', return_value=np.zeros((75, 64), dtype=np.float32)) as encode:
                dataset = native.build_dataset(None, folder, cache, 2, 'default', ' Jazz ', torch.device('cpu'))
                self.assertEqual(len(dataset.items), 1)
                self.assertEqual(dataset.items[0].caption, 'Jazz')
                self.assertEqual(tuple(native.load_clip_latents(dataset.items[0]).shape), (50, 64))
                native.build_dataset(None, folder, cache, 2, 'none', '', torch.device('cpu'))
                self.assertEqual(encode.call_count, 1)

    def test_schema_and_missing_inputs(self):
        with patch.object(folder_paths, 'get_filename_list', return_value=['model']):
            schema = module.SkebaYuE2TrainingDataset.define_schema()
            self.assertEqual(schema.node_id, 'SkebaYuE2TrainingDataset')
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError, 'at least one'):
                module.stage_tracks({}, root)
        with self.assertRaisesRegex(ValueError, 'ComfyUI-YuE2-Trainer'):
            module.SkebaYuE2TrainingDataset.execute('model', {})


if __name__ == '__main__':
    unittest.main()

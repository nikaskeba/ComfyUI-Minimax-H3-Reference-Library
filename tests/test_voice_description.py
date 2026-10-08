import importlib
import importlib.util
import io
import sys
import types
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import numpy as np

root = Path(__file__).parents[1]
package = types.ModuleType("voice_description_test_package")
package.__path__ = [str(root)]
sys.modules[package.__name__] = package
module = importlib.import_module(package.__name__ + ".voice_description")


class VoiceDescriptionTests(unittest.TestCase):
    def test_duration_channels_and_unchanged_source(self):
        for rate in (16000, 44100, 48000):
            for duration in (3, 20):
                x = np.ones((1, 2, rate * duration), dtype=np.float32) * .1
                old = x.copy()
                with patch.object(module, "analyze_waveform", return_value={}) as analyze, patch.object(module, "describe_timbre", return_value="A warm voice."):
                    result = module.describe_audio({"waveform": x, "sample_rate": rate})
                self.assertEqual(result["seconds"], min(15, duration))
                self.assertEqual(analyze.call_args.args[0].shape, (rate * min(15, duration),))
                np.testing.assert_array_equal(x, old)

    def test_invalid_and_silent(self):
        for x in (np.array([]), np.ones(200), np.zeros(16000), np.full(16000, np.nan)):
            with self.assertRaises(ValueError):
                module.describe_audio({"waveform": x, "sample_rate": 16000})
        with self.assertRaisesRegex(ValueError, "Could not read"):
            module.describe_file(b"not audio")

    def test_upload_decode_stops_at_cap(self):
        data = io.BytesIO()
        with wave.open(data, "wb") as out:
            out.setnchannels(2); out.setsampwidth(2); out.setframerate(16000)
            out.writeframes(np.full((20 * 16000, 2), 2000, dtype="<i2").tobytes())
        with patch.object(module, "describe_audio", side_effect=lambda x: {"seconds": x["waveform"].shape[-1] / x["sample_rate"]}):
            self.assertEqual(module.describe_file(data.getvalue())["seconds"], 15)

    def test_matches_upstream_analyzer(self):
        path = root.parent / "comfyui-easy-ui" / "voice_analysis.py"
        if not path.exists():
            self.skipTest("Upstream checkout not installed")
        spec = importlib.util.spec_from_file_location("upstream_voice_analysis", path)
        upstream = importlib.util.module_from_spec(spec); spec.loader.exec_module(upstream)
        rate = 16000
        t = np.arange(rate) / rate
        x = (.15 * np.sin(2 * np.pi * 155 * t) + .05 * np.sin(2 * np.pi * 310 * t)).astype(np.float32)
        expected = upstream.analyze_waveform(x.copy(), rate)
        actual = module.analyze_waveform(x.copy(), rate)
        # Original measurements remain identical; Skeba adds phrasing metrics.
        for key, value in expected.items():
            if isinstance(value, (float, int)):
                np.testing.assert_allclose(actual[key], value, equal_nan=True)
            else:
                self.assertEqual(actual[key], value)
        self.assertEqual(module.describe_audio({"waveform": x, "sample_rate": rate})["description"], module.describe_timbre(actual))

    def test_internal_pauses_ignore_recording_padding_and_tiny_gaps(self):
        analysis = importlib.import_module(package.__name__ + ".voice_analysis_vendor.analysis")
        mask = np.r_[np.ones(100), np.zeros(20), np.ones(200), np.zeros(80), np.ones(100)].astype(bool)
        result = analysis._phrasing_metrics(mask, .01)
        self.assertEqual(result['phrase_count'], 3)
        self.assertEqual(result['pause_count'], 2)
        self.assertAlmostEqual(result['pause_seconds_median'], .5)
        self.assertAlmostEqual(result['phrase_seconds_median'], 1)
        padded = np.r_[np.zeros(200), mask, np.zeros(300)].astype(bool)
        self.assertEqual(result, analysis._phrasing_metrics(padded, .01))
        tiny_gap = np.r_[np.ones(100), np.zeros(5), np.ones(100)].astype(bool)
        self.assertEqual(analysis._phrasing_metrics(tiny_gap, .01)['pause_count'], 0)
        self.assertEqual(analysis._phrasing_metrics(np.zeros(100, dtype=bool), .01), {})

    def test_new_metrics_gain_invariant(self):
        rate = 16000
        t = np.arange(rate * 3) / rate
        x = (.2 * np.sin(2 * np.pi * 170 * t) * (.6 + .4 * np.sin(2 * np.pi * 2 * t))).astype(np.float32)
        first = module.analyze_waveform(x, rate)
        second = module.analyze_waveform(x * .1, rate)
        for key in ('active_level_span_db', 'pause_ratio', 'phrase_seconds_median'):
            self.assertAlmostEqual(first[key], second[key], places=4)


if __name__ == "__main__":
    unittest.main()

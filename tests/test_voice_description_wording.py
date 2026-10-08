import importlib.util
import math
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('concise_timbre', Path(__file__).parents[1] / 'voice_analysis_vendor/timbre_map.py')
formatter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(formatter)


def sample(**changes):
    metrics = dict(duration=12, active_ratio=.55, f0_median=219,
                   rolloff85_median=1800, low_energy=16, flatness=.001,
                   harmonic_par=45, tps=3, longest_voiced=2,
                   level_dbfs=-18, f0_span_st=11, phrase_count=4,
                   phrase_seconds_median=3, phrase_duration_cv=.5,
                   pause_count=3, pause_seconds_median=.8, pause_ratio=.3,
                   active_level_span_db=20)
    metrics.update(changes)
    return metrics


class ConciseDescriptionTests(unittest.TestCase):
    def test_concise_deterministic_perceptual_description(self):
        metrics = sample()
        original = metrics.copy()
        text = formatter.describe_timbre(metrics)
        self.assertEqual(text, formatter.describe_timbre(metrics))
        self.assertEqual(metrics, original)
        self.assertTrue(20 <= len(text.split()) <= 35, text)
        self.assertTrue(text.startswith('Mid-low pitch,'))
        self.assertIn('bright tone', text)
        self.assertIn('long pauses', text)
        self.assertNotRegex(text, r'\d|Hz|dB|F0|F1|flatness|PAR|Audio 1|clean clear crisp')
        self.assertIn(';', text)

    def test_different_voices_and_no_unmeasured_traits(self):
        light = formatter.describe_timbre(sample(f0_median=310, low_energy=2,
            rolloff85_median=3300, tps=7, longest_voiced=.6, active_ratio=.96, f0_span_st=20))
        dark = formatter.describe_timbre(sample(f0_median=120, low_energy=45,
            rolloff85_median=350, tps=2, longest_voiced=3, level_dbfs=-40, f0_span_st=3))
        self.assertIn('High pitch', light)
        self.assertIn('thin vocal body', light)
        self.assertIn('highly animated intonation', light)
        self.assertIn('Low pitch', dark)
        self.assertIn('dark tone', dark)
        self.assertIn('flat intonation', dark)
        self.assertNotEqual(light, dark)
        for text in (light, dark):
            self.assertNotRegex(text.lower(), r'gender|male|female|accent|nasal|storytelling|raspy|forward')
            self.assertLessEqual(len(text.split()), 35)

    def test_low_confidence_and_missing_measurements(self):
        short = formatter.describe_timbre(sample(duration=.3, flatness=.19, harmonic_par=3))
        self.assertNotIn('breathy', short)
        self.assertNotIn('pace', short)
        self.assertNotIn('delivery', short)
        self.assertIn('Insufficient', formatter.describe_timbre({}))
        invalid = {key: math.nan for key in sample()}
        self.assertIn('Insufficient', formatter.describe_timbre(invalid))
        noisy = formatter.describe_timbre(sample(flatness=.7, harmonic_par=1))
        self.assertNotIn('breathy', noisy)
        self.assertNotIn('clear crisp', noisy)

    def test_distinctive_traits_outrank_average_traits(self):
        text = formatter.describe_timbre(sample(f0_span_st=10.5))
        self.assertIn('long pauses', text)
        self.assertIn('long sustained phrases', text)
        self.assertIn('strong volume contrasts', text)
        self.assertNotIn('natural intonation', text)

    def test_same_pitch_and_tone_different_phrasing(self):
        sustained = formatter.describe_timbre(sample())
        clipped = formatter.describe_timbre(sample(phrase_seconds_median=.5,
            pause_seconds_median=.2, pause_ratio=.15, active_level_span_db=3))
        self.assertIn('short clipped phrases', clipped)
        self.assertIn('brief pauses', clipped)
        self.assertNotEqual(sustained, clipped)
        self.assertEqual(sustained.split(';')[0], clipped.split(';')[0])

    def test_spectral_emphasis_and_insufficient_phrase_evidence(self):
        rounded = formatter.describe_timbre(sample(bands={'mid': 85, 'highmid': 5}))
        edged = formatter.describe_timbre(sample(bands={'mid': 20, 'highmid': 60}))
        self.assertIn('rounded midrange emphasis', rounded)
        self.assertIn('pronounced upper-mid edge', edged)
        text = formatter.describe_timbre(sample(phrase_count=1, pause_count=0,
            phrase_duration_cv=0, phrase_seconds_median=.3))
        self.assertNotIn('phrases', text)
        self.assertNotIn('phrasing', text)
        self.assertNotIn('pauses', text)

    def test_phrase_regularity_needs_several_observations(self):
        for cv, label in ((.05, 'evenly measured phrasing'), (1.2, 'varied phrase lengths')):
            text = formatter.describe_timbre(sample(phrase_duration_cv=cv,
                phrase_seconds_median=1.8, active_level_span_db=9))
            self.assertIn(label, text)

    def test_pitch_labels_and_optional_quality(self):
        for pitch, label in ((90, 'Very low'), (120, 'Low'), (200, 'Mid-low'),
                             (230, 'Medium'), (250, 'Mid-high'), (300, 'High'), (400, 'Very high')):
            self.assertTrue(formatter.describe_timbre(sample(f0_median=pitch)).startswith(label + ' pitch'))
        text = formatter.describe_timbre(sample(harmonic_par=None))
        self.assertNotIn('clear crisp', text)
        self.assertNotIn('breathy', text)


if __name__ == '__main__':
    unittest.main()

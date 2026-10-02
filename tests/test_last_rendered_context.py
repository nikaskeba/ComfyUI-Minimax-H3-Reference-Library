import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

import torch

spec = importlib.util.spec_from_file_location("last_rendered_context", Path(__file__).parents[1] / "last_rendered_context.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class LastRenderedContextTests(unittest.TestCase):
    def video(self, fps=24, count=96, audio=True):
        frames = torch.arange(count).view(count, 1, 1, 1).expand(count, 2, 3, 3).float()
        sound = {"waveform": torch.arange(round(count / fps * 2400)).view(1, 1, -1), "sample_rate": 2400} if audio else None
        parts = SimpleNamespace(images=frames, audio=sound, frame_rate=fps)
        return SimpleNamespace(get_components=lambda: parts), parts

    def test_last_clip_tail_audio_alignment_and_no_source_mutation(self):
        video, parts = self.video()
        unusable = SimpleNamespace(get_components=lambda: self.fail("Earlier clips must not be decoded"))
        for count in (5, 22, 39, 56):
            frames, audio, bypass, actual = module.SkebaH3LastRenderedContext().load(str(count), accumulation={"accum": [unusable, video]})
            self.assertFalse(bypass)
            self.assertEqual(actual, count)
            self.assertTrue(torch.equal(frames, parts.images[-count:]))
            self.assertTrue(torch.equal(audio["waveform"], parts.audio["waveform"][..., -count*100:]))
            frames.zero_(); audio["waveform"].zero_()
            self.assertEqual(parts.images[-1,0,0,0],95)
            self.assertEqual(parts.audio["waveform"][0,0,-1],9599)

    def test_empty_short_and_explicit_bypass(self):
        node = module.SkebaH3LastRenderedContext()
        self.assertEqual(node.load(), (None,None,True,0))
        video,_ = self.video(count=4)
        self.assertEqual(node.load(video=video), (None,None,True,0))
        self.assertEqual(node.load(video=object(),bypass=True), (None,None,True,0))
        video,_ = self.video(count=20)
        self.assertEqual(node.load(video=video)[3],5)

    def test_explicit_video_priority_and_audio_off(self):
        video,_ = self.video(audio=False)
        self.assertIsNone(module.SkebaH3LastRenderedContext().load(video=video,accumulation={"accum":[object()]})[1])
        video,_ = self.video()
        self.assertIsNone(module.SkebaH3LastRenderedContext().load(video=video,include_audio=False)[1])

    def test_non_24_fps_is_sampled_without_spatial_crop(self):
        video,parts = self.video(fps=30,count=120)
        frames,audio,bypass,count=module.SkebaH3LastRenderedContext().load(video=video)
        self.assertEqual(frames.shape,(22,2,3,3))
        self.assertEqual(audio['waveform'].shape[-1],2200)
        self.assertEqual(frames[0,0,0,0],92)
        self.assertEqual(frames[-1,0,0,0],118)


if __name__ == '__main__':
    unittest.main()

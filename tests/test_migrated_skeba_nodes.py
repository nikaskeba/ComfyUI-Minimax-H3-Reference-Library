import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
ROOT = Path(__file__).resolve().parents[1]


class FakeTorch:
    @staticmethod
    def from_numpy(value):
        return value

    @staticmethod
    def zeros(shape):
        return np.zeros(shape, dtype=np.float32)

    @staticmethod
    def ones(shape):
        return np.ones(shape, dtype=np.float32)

    @staticmethod
    def cat(values, dim=0):
        return np.concatenate(values, axis=dim)


class FakeImage:
    mode = "RGB"

    def __init__(self, value):
        self.pixels = np.full((2, 3, 3), value, dtype=np.uint8)

    def convert(self, mode):
        self.mode = mode
        return self

    def __array__(self, dtype=None, copy=None):
        return np.asarray(self.pixels, dtype=dtype)


class FakeImageApi:
    @staticmethod
    def open(path):
        return FakeImage(0 if Path(path).name.startswith("a") else 255)


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MigratedSkebaNodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder_paths = types.SimpleNamespace(get_input_directory=lambda: "input")
        comfy_latest = types.ModuleType("comfy_api.latest")
        comfy_latest.InputImpl = types.SimpleNamespace(
            VideoFromComponents=lambda components, bit_depth: (components, bit_depth)
        )
        comfy_latest.Types = types.SimpleNamespace(VideoComponents=types.SimpleNamespace)
        comfy_api = types.ModuleType("comfy_api")
        comfy_api.latest = comfy_latest
        cls.folder_paths_patch = mock.patch.dict(
            sys.modules,
            {
                "folder_paths": folder_paths,
                "comfy_api": comfy_api,
                "comfy_api.latest": comfy_latest,
            },
        )
        cls.folder_paths_patch.start()
        cls.images = load_module("batch_image_nodes_test", "batch_image_nodes.py")
        cls.io_tags = load_module("skeba_io_tags_test", "skeba_io_tags.py")
        cls.video = load_module("video_loop_node_test", "video_loop_node.py")
        cls.images.np = np
        cls.images.torch = FakeTorch
        cls.images.Image = FakeImageApi
        cls.video.torch = FakeTorch

    @classmethod
    def tearDownClass(cls):
        cls.folder_paths_patch.stop()

    def test_batch_loader_sorts_and_loads_images(self):
        with tempfile.TemporaryDirectory() as folder:
            for name, value in (("b.png", 255), ("a.png", 0)):
                (Path(folder) / name).write_bytes(bytes([value]))

            images, filenames, count = self.images.BatchImageLoaderNode().load_images(folder)

        self.assertEqual(filenames, ["a.png", "b.png"])
        self.assertEqual(count, 2)
        self.assertEqual(tuple(images[0].shape), (1, 2, 3, 3))

    def test_image_selector_wraps_index(self):
        images = [FakeTorch.zeros((1, 2, 2, 3)), FakeTorch.ones((1, 2, 2, 3))]
        image, index = self.images.ImageFromBatchNode().get_image(images, [3])

        self.assertEqual(index, 1)
        self.assertTrue(np.array_equal(image, images[1]))

    def test_named_bypass_reports_enabled_state(self):
        node = self.io_tags.SkebaBypass()

        self.assertEqual(node.route("clip", False, "value"), ("value", "clip", True))
        self.assertEqual(node.route("clip", True, "value"), (None, "clip", False))

    def test_video_combiner_concatenates_frames_and_audio(self):
        component_type = types.SimpleNamespace
        clips = [
            component_type(
                images=FakeTorch.zeros((2, 2, 2, 3)),
                audio={"waveform": FakeTorch.zeros((1, 1, 20)), "sample_rate": 10},
                frame_rate=2,
            ),
            component_type(
                images=FakeTorch.ones((1, 2, 2, 3)),
                audio={"waveform": FakeTorch.ones((1, 1, 10)), "sample_rate": 10},
                frame_rate=2,
            ),
        ]

        class Video:
            def __init__(self, component):
                self.component = component

            def get_components(self):
                return self.component

            def get_bit_depth(self):
                return 8

        with mock.patch.object(
            self.video.InputImpl,
            "VideoFromComponents",
            side_effect=lambda components, bit_depth: (components, bit_depth),
        ):
            video, count = self.video.CombineVideoClipsNode().combine(
                {"accum": [Video(clip) for clip in clips]}
            )

        self.assertEqual(count, 2)
        self.assertEqual(video[0].images.shape[0], 3)
        self.assertEqual(video[0].audio["waveform"].shape[-1], 15)

    def test_video_bookends_order_silence_and_accumulation_unchanged(self):
        import torch

        def video(value, audio=None, rate=2):
            component = types.SimpleNamespace(
                images=torch.full((2, 2, 2, 3), float(value)), audio=audio, frame_rate=rate)
            return types.SimpleNamespace(get_components=lambda: component, get_bit_depth=lambda: 8)

        body = video(2, {"waveform": torch.ones((1, 2, 8)), "sample_rate": 10})
        accumulation = {"accum": [body]}
        with mock.patch.object(self.video, "torch", torch):
            for start, end, order in ((video(1), video(3), [1, 2, 3]),
                                      (video(1), None, [1, 2]),
                                      (None, video(3), [2, 3])):
                result, count = self.video.CombineVideoClipsNode().combine(accumulation, start, end)
                components = result[0]
                self.assertEqual(count, len(order))
                self.assertEqual(components.images[::2, 0, 0, 0].tolist(), order)
                expected = torch.zeros((1, 2, len(order) * 10))
                offset = order.index(2) * 10
                expected[..., offset:offset + 8] = 1
                self.assertTrue(torch.equal(components.audio["waveform"], expected))
                self.assertEqual(accumulation["accum"], [body])
            result, count = self.video.CombineVideoClipsNode().combine({"accum": []}, video(1), video(3))
            self.assertEqual(count, 2)
            self.assertIsNone(result[0].audio)
            with self.assertRaisesRegex(ValueError, "frame rate"):
                self.video.CombineVideoClipsNode().combine(accumulation, video(1, rate=24))

    def test_video_bookends_resize_to_body_without_mutating_sources(self):
        import torch

        def video(height, width, value):
            component = types.SimpleNamespace(
                images=torch.full((2, height, width, 3), float(value)),
                audio=None, frame_rate=24)
            return types.SimpleNamespace(get_components=lambda: component, get_bit_depth=lambda: 8)

        start, body, end = video(8, 8, 1), video(4, 8, 2), video(2, 8, 3)
        with mock.patch.object(self.video, "torch", torch):
            result, count = self.video.CombineVideoClipsNode().combine({"accum": [body]}, start, end)
            frames = result[0].images
            self.assertEqual(tuple(frames.shape), (6, 4, 8, 3))
            self.assertEqual(count, 3)
            self.assertTrue(torch.all(frames[:2, :, :2] == 0))
            self.assertTrue(torch.all(frames[:2, :, 2:6] == 1))
            self.assertTrue(torch.all(frames[2:4] == 2))
            self.assertTrue(torch.all(frames[4:, 0] == 0))
            self.assertTrue(torch.all(frames[4:, 1:3] == 3))
            self.assertEqual(tuple(start.get_components().images.shape), (2, 8, 8, 3))
            self.assertEqual(tuple(end.get_components().images.shape), (2, 2, 8, 3))
            with self.assertRaisesRegex(ValueError, "image dimensions"):
                self.video.CombineVideoClipsNode().combine({"accum": [body, video(8, 8, 4)]})

    def test_video_bookends_resample_to_accumulated_audio_rate(self):
        import torch

        def video(rate):
            t = torch.arange(rate, dtype=torch.float32) / rate
            waveform = torch.sin(2 * torch.pi * 440 * t).reshape(1, 1, -1)
            component = types.SimpleNamespace(
                images=torch.zeros((24, 2, 2, 3)),
                audio={"waveform": waveform, "sample_rate": rate}, frame_rate=24)
            return types.SimpleNamespace(get_components=lambda: component, get_bit_depth=lambda: 8)

        start, body, end = video(44100), video(32000), video(48000)
        with mock.patch.object(self.video, "torch", torch):
            result, count = self.video.CombineVideoClipsNode().combine({"accum": [body]}, start, end)
            audio = result[0].audio
            self.assertEqual(audio["sample_rate"], 32000)
            self.assertEqual(audio["waveform"].shape[-1], 96000)
            expected = body.get_components().audio["waveform"]
            for offset in (0, 32000, 64000):
                segment = audio["waveform"][..., offset:offset + 32000]
                self.assertLess(float((segment[..., 100:-100] - expected[..., 100:-100]).abs().max()), 0.01)
            self.assertEqual(start.get_components().audio["sample_rate"], 44100)
            self.assertEqual(end.get_components().audio["waveform"].shape[-1], 48000)

    def test_migrated_nodes_use_skeba_utility_category(self):
        classes = (
            self.images.BatchImageLoaderNode,
            self.images.ImageFromBatchNode,
            self.io_tags.SkebaBypass,
            self.video.CombineVideoClipsNode,
        )
        self.assertTrue(
            all(node.CATEGORY == "Skeba AI Nodes - Utilities" for node in classes)
        )


if __name__ == "__main__":
    unittest.main()

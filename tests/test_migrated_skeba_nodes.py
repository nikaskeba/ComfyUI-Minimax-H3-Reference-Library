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

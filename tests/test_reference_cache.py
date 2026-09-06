import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

import torch


MODULE_PATH = Path(__file__).parents[1] / "reference_cache.py"
PACKAGE_NAME = "h3_cache_test_package"
PACKAGE = types.ModuleType(PACKAGE_NAME)
PACKAGE.__path__ = []
sys.modules[PACKAGE_NAME] = PACKAGE
LIBRARY = types.ModuleType(f"{PACKAGE_NAME}.library")
LIBRARY.library_root = lambda: Path("unused")
sys.modules[f"{PACKAGE_NAME}.library"] = LIBRARY
SPEC = importlib.util.spec_from_file_location(
    f"{PACKAGE_NAME}.reference_cache", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ReferenceCacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        MODULE.cache_root = lambda: self.root / "cache" / "v1"

    def tearDown(self):
        self.temporary.cleanup()

    def test_image_cache_miss_then_hit_without_rebuilding(self):
        calls = []
        cache = MODULE.ReferenceTensorCache()
        entry = {"record_id": "nicholas", "tag": "Nicholas_Skeba"}
        metadata = {"latent_h": 2, "latent_w": 3, "source_sha256": "source"}

        def build():
            calls.append(True)
            return torch.arange(144, dtype=torch.float32).reshape(1, 24, 1, 2, 3)

        first, _, first_state = cache.get_or_create(
            "image", entry, "key", metadata, build)
        second, _, second_state = cache.get_or_create(
            "image", entry, "key", metadata, build)

        self.assertEqual(len(calls), 1)
        self.assertEqual(first_state, "MISS -> CREATED")
        self.assertEqual(second_state, "HIT")
        self.assertTrue(torch.equal(first.cpu(), second))

    def test_image_and_audio_invalidate_independently(self):
        calls = {"image": 0, "audio": 0}
        cache = MODULE.ReferenceTensorCache()
        entry = {"record_id": "person", "tag": "person"}

        def image():
            calls["image"] += 1
            return torch.zeros(1, 24, 1, 2, 2)

        def audio():
            calls["audio"] += 1
            return torch.zeros(1, 32, 2, 4)

        image_meta = {"latent_h": 2, "latent_w": 2}
        audio_meta = {}
        cache.get_or_create("image", entry, "image-a", image_meta, image)
        cache.get_or_create("audio", entry, "audio-a", audio_meta, audio)
        cache.get_or_create("image", entry, "image-a", image_meta, image)
        cache.get_or_create("audio", entry, "audio-b", audio_meta, audio)

        self.assertEqual(calls, {"image": 1, "audio": 2})

    def test_corrupt_tensor_is_ignored_and_rebuilt(self):
        cache = MODULE.ReferenceTensorCache()
        entry = {"record_id": "person", "tag": "person"}
        metadata = {"latent_h": 2, "latent_w": 2}
        cache.get_or_create(
            "image", entry, "broken", metadata,
            lambda: torch.zeros(1, 24, 1, 2, 2))
        tensor_file = next(self.root.rglob("broken.safetensors"))
        tensor_file.write_bytes(b"not safetensors")
        calls = []

        _, _, state = cache.get_or_create(
            "image", entry, "broken", metadata,
            lambda: calls.append(True) or torch.ones(1, 24, 1, 2, 2))

        self.assertEqual(calls, [True])
        self.assertEqual(state, "MISS -> CREATED")

    def test_manifest_records_audio_length(self):
        cache = MODULE.ReferenceTensorCache()
        entry = {"record_id": "voice", "tag": "voice"}
        cache.get_or_create(
            "audio", entry, "audio-key", {"source_sha256": "abc"},
            lambda: torch.zeros(1, 32, 2, 7))

        manifest = json.loads(next(self.root.rglob("manifest.json")).read_text())
        self.assertEqual(manifest["cache_schema_version"], 1)
        self.assertEqual(manifest["audio"]["audio-key"]["ref_audio_t"], 7)

    def test_disabled_mode_never_writes(self):
        cache = MODULE.ReferenceTensorCache()
        _, _, state = cache.get_or_create(
            "image", {"record_id": "x", "tag": "x"}, "key",
            {"latent_h": 1, "latent_w": 1},
            lambda: torch.zeros(1, 24, 1, 1, 1), "disabled")

        self.assertEqual(state, "DISABLED")
        self.assertFalse((self.root / "cache").exists())

    def test_qwen_visual_cache_miss_then_hit(self):
        calls = []
        cache = MODULE.ReferenceTensorCache()
        entry = {"record_id": "person", "tag": "person"}

        def build():
            calls.append(True)
            return {
                "merged": torch.ones(4, 8),
                "grid": torch.tensor([[1, 4, 4]]),
                "deepstack": [torch.full((4, 8), float(i)) for i in range(3)],
            }

        first, _, first_state = cache.get_or_create_visual(
            entry, "visual-key", {"source_sha256": "abc"}, build)
        second, _, second_state = cache.get_or_create_visual(
            entry, "visual-key", {"source_sha256": "abc"}, build)

        self.assertEqual(calls, [True])
        self.assertEqual(first_state, "MISS -> CREATED")
        self.assertEqual(second_state, "HIT")
        self.assertTrue(torch.equal(first["merged"].cpu(), second["merged"]))
        self.assertEqual(len(second["deepstack"]), 3)
        manifest = json.loads(next(self.root.rglob("manifest.json")).read_text())
        self.assertEqual(manifest["qwen"]["visual-key"]["deepstack_count"], 3)

    def test_video_latent_cache_miss_then_hit(self):
        calls = []
        cache = MODULE.ReferenceTensorCache()
        entry = {"record_id": "clip", "tag": "clip"}
        metadata = {"latent_h": 2, "latent_w": 3, "input_frames": 22}

        def build():
            calls.append(True)
            return torch.zeros(1, 24, 2, 2, 3)

        _, _, first_state = cache.get_or_create(
            "video", entry, "video-key", metadata, build)
        second, _, second_state = cache.get_or_create(
            "video", entry, "video-key", metadata, build)

        self.assertEqual(calls, [True])
        self.assertEqual(first_state, "MISS -> CREATED")
        self.assertEqual(second_state, "HIT")
        self.assertEqual(tuple(second.shape), (1, 24, 2, 2, 3))

    def test_compiled_reference_round_trip(self):
        cache = MODULE.ReferenceTensorCache()
        entry = {"record_id": "compiled-person", "tag": "person"}
        cache.save_compiled(
            entry,
            "compiled-key",
            "image",
            {
                "video_latent": torch.ones(1, 24, 1, 2, 3),
                "qwen_merged": torch.ones(4, 8),
            },
            {"latent_h": 2, "latent_w": 3},
        )

        tensors, metadata = cache.load_compiled(
            entry, "compiled-key", "image")
        self.assertTrue(torch.equal(
            tensors["video_latent"], torch.ones(1, 24, 1, 2, 3)))
        self.assertEqual(metadata["cache_schema_version"], 1)
        self.assertEqual(metadata["kind"], "image")


if __name__ == "__main__":
    unittest.main()

import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path

import torch


COMFY_ROOT = Path(__file__).parents[3]
PROJECT_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(COMFY_ROOT))
PACKAGE_NAME = "h3_cached_node_test_package"
PACKAGE = types.ModuleType(PACKAGE_NAME)
PACKAGE.__path__ = []
sys.modules[PACKAGE_NAME] = PACKAGE
LIBRARY = types.ModuleType(f"{PACKAGE_NAME}.library")
LIBRARY.library_root = lambda: Path("unused")
sys.modules[LIBRARY.__name__] = LIBRARY

CACHE_SPEC = importlib.util.spec_from_file_location(
    f"{PACKAGE_NAME}.reference_cache", PROJECT_ROOT / "reference_cache.py")
CACHE_MODULE = importlib.util.module_from_spec(CACHE_SPEC)
sys.modules[CACHE_SPEC.name] = CACHE_MODULE
CACHE_SPEC.loader.exec_module(CACHE_MODULE)

NODE_SPEC = importlib.util.spec_from_file_location(
    f"{PACKAGE_NAME}.cached_h3_reference", PROJECT_ROOT / "cached_h3_reference.py")
NODE_MODULE = importlib.util.module_from_spec(NODE_SPEC)
sys.modules[NODE_SPEC.name] = NODE_MODULE
NODE_SPEC.loader.exec_module(NODE_MODULE)


class _Model:
    pass


class _VAE:
    def __init__(self, path, audio=False):
        self.first_stage_model = _Model()
        self.patcher = types.SimpleNamespace(
            cached_patcher_init=(object(), (str(path), None, None)))
        self.audio_sample_rate = 32000
        self.audio = audio
        self.calls = 0
        self.last_input_shape = None

    def encode(self, value):
        self.calls += 1
        self.last_input_shape = tuple(value.shape)
        if self.audio:
            return torch.full((1, 32, 2, 4), 2.0)
        return torch.full(
            (1, 24, 1, value.shape[1] // 16, value.shape[2] // 16), 1.0)


class _VisualTransformer:
    def __init__(self):
        self.calls = 0

    def preprocess_embed(self, embed, device):
        self.calls += 1
        return torch.ones(4, 16), {
            "grid": torch.tensor([[1, 4, 4]]),
            "deepstack": [torch.full((4, 16), float(i)) for i in range(3)],
        }


class _Clip:
    def __init__(self, path=None):
        self.items = None
        self.visual = _VisualTransformer()
        if path is not None:
            self.patcher = types.SimpleNamespace(
                cached_patcher_init=(object(), ([str(path)], None, None)),
                forced_hooks=None,
                patches={},
                load_device=torch.device("cpu"),
            )
            inner = types.SimpleNamespace(transformer=self.visual)
            self.cond_stage_model = types.SimpleNamespace(
                clip="qwen3vl_32b", qwen3vl_32b=inner, dtypes={torch.float32})

    def load_model(self):
        return self.patcher

    def tokenize(self, prompt, minimax_ref_items=None):
        self.items = minimax_ref_items
        return prompt

    def encode_from_tokens_scheduled(self, tokens):
        return [[torch.zeros(1), {}]]


class CachedNodeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        CACHE_MODULE.cache_root = lambda: self.root / "cache" / "v1"
        self.video_model = self.root / "video-vae.safetensors"
        self.audio_model = self.root / "audio-vae.safetensors"
        self.qwen_model = self.root / "qwen.safetensors"
        self.image_source = self.root / "person.png"
        self.audio_source = self.root / "person.wav"
        for path, content in (
                (self.video_model, b"video-model"),
                (self.audio_model, b"audio-model"),
                (self.qwen_model, b"qwen-model"),
                (self.image_source, b"image"),
                (self.audio_source, b"audio")):
            path.write_bytes(content)
        self.original_empty = NODE_MODULE.h3._empty_av_latent
        NODE_MODULE.h3._empty_av_latent = lambda width, height, length: (
            {"samples": "empty"}, 5)

    def tearDown(self):
        NODE_MODULE.h3._empty_av_latent = self.original_empty
        self.temporary.cleanup()

    def test_second_execution_reuses_image_and_audio_latents(self):
        video_vae = _VAE(self.video_model)
        audio_vae = _VAE(self.audio_model, audio=True)
        clip = _Clip(self.qwen_model)
        bundle = {
            "images": [{"record_id": "person", "tag": "person",
                        "source_path": str(self.image_source)}],
            "audios": [{"record_id": "person", "tag": "person",
                        "source_path": str(self.audio_source)}],
        }
        arguments = dict(
            clip=clip, vae=video_vae, audio_vae=audio_vae, prompt="test",
            width=32, height=32, length=5, reference_bundle=bundle,
            ref_images={"ref_image_0": torch.zeros(1, 32, 32, 3)},
            ref_audios={"ref_audio_0": {
                "waveform": torch.zeros(1, 2, 3200), "sample_rate": 32000}},
        )

        first = NODE_MODULE.SkebaCachedMiniMaxH3ReferenceToVideo.execute(**arguments)
        supplied_images = arguments["ref_images"]
        supplied_audios = arguments["ref_audios"]
        arguments["ref_images"] = {"ref_image_0": None}
        arguments["ref_audios"] = {"ref_audio_0": None}
        original_image_loader = NODE_MODULE._load_image_source
        original_audio_loader = NODE_MODULE._load_audio_source
        try:
            NODE_MODULE._load_image_source = lambda path: self.fail(
                "image source was loaded on a compiled cache hit")
            NODE_MODULE._load_audio_source = lambda path: self.fail(
                "audio source was loaded on a compiled cache hit")
            second = NODE_MODULE.SkebaCachedMiniMaxH3ReferenceToVideo.execute(
                **arguments)
        finally:
            NODE_MODULE._load_image_source = original_image_loader
            NODE_MODULE._load_audio_source = original_audio_loader
            arguments["ref_images"] = supplied_images
            arguments["ref_audios"] = supplied_audios

        self.assertEqual(video_vae.calls, 1)
        self.assertEqual(audio_vae.calls, 1)
        self.assertIn("Image: MISS -> CREATED", first[2])
        self.assertIn("Audio: MISS -> CREATED", first[2])
        self.assertIn("Qwen: MISS -> CREATED", first[2])
        self.assertIn("Image: HIT", second[2])
        self.assertIn("Audio: HIT", second[2])
        self.assertIn("Qwen: HIT", second[2])
        self.assertIn("lazy bundle", second[2])
        self.assertEqual(clip.visual.calls, 1)
        cached_payload = clip.items[0]["data"]
        merged, extra = NODE_MODULE.MiniMaxQwen3VL.preprocess_embed(
            object(), {"type": "image", "data": cached_payload}, torch.device("cpu"))
        self.assertEqual(tuple(merged.shape), (4, 16))
        self.assertEqual(len(extra["deepstack"]), 3)
        refs = second[0][0][1]["minimax_refs"]
        self.assertEqual([item["kind"] for item in refs], ["image", "audio"])

        self.image_source.write_bytes(b"changed image")
        third = NODE_MODULE.SkebaCachedMiniMaxH3ReferenceToVideo.execute(**arguments)
        self.assertEqual(video_vae.calls, 2)
        self.assertEqual(audio_vae.calls, 1)
        self.assertIn("Image: MISS -> CREATED", third[2])
        self.assertIn("Audio: HIT", third[2])
        self.assertIn("Qwen: MISS -> CREATED", third[2])
        self.assertEqual(clip.visual.calls, 2)

        self.video_model.write_bytes(b"changed-video-model")
        fourth = NODE_MODULE.SkebaCachedMiniMaxH3ReferenceToVideo.execute(**arguments)
        self.assertEqual(video_vae.calls, 3)
        self.assertEqual(audio_vae.calls, 1)
        self.assertIn("Image: MISS -> CREATED", fourth[2])
        self.assertIn("Audio: HIT", fourth[2])
        self.assertIn("Qwen: HIT", fourth[2])
        self.assertEqual(clip.visual.calls, 2)

        arguments["width"] = 64
        fifth = NODE_MODULE.SkebaCachedMiniMaxH3ReferenceToVideo.execute(**arguments)
        self.assertEqual(video_vae.calls, 4)
        self.assertEqual(audio_vae.calls, 1)
        self.assertIn("Image: MISS -> CREATED", fifth[2])
        self.assertIn("Audio: HIT", fifth[2])
        self.assertIn("Qwen: HIT", fifth[2])
        self.assertEqual(clip.visual.calls, 2)

        arguments["prompt"] = "a different scene prompt"
        sixth = NODE_MODULE.SkebaCachedMiniMaxH3ReferenceToVideo.execute(**arguments)
        self.assertIn("Image: HIT", sixth[2])
        self.assertIn("Audio: HIT", sixth[2])
        self.assertIn("Qwen: HIT", sixth[2])
        self.assertEqual(clip.visual.calls, 2)

        self.qwen_model.write_bytes(b"changed-qwen-model")
        seventh = NODE_MODULE.SkebaCachedMiniMaxH3ReferenceToVideo.execute(**arguments)
        self.assertIn("Image: HIT", seventh[2])
        self.assertIn("Audio: HIT", seventh[2])
        self.assertIn("Qwen: MISS -> CREATED", seventh[2])
        self.assertEqual(clip.visual.calls, 3)

    def test_video_soundtrack_and_qwen_blocks_are_cached(self):
        video_vae = _VAE(self.video_model)
        audio_vae = _VAE(self.audio_model, audio=True)
        clip = _Clip(self.qwen_model)
        video_source = self.root / "performance.mp4"
        video_source.write_bytes(b"video-with-soundtrack")
        bundle = {
            "videos": [{
                "record_id": "performance",
                "tag": "performance",
                "source_path": str(video_source),
                "has_audio": True,
            }],
            "video_fps": 24.0,
        }
        arguments = dict(
            clip=clip, vae=video_vae, audio_vae=audio_vae, prompt="test",
            width=32, height=32, length=5, reference_bundle=bundle,
            ref_videos={"ref_video_0": torch.zeros(5, 32, 32, 3)},
            ref_video_audios={"ref_video_audio_0": {
                "waveform": torch.zeros(1, 2, 3200), "sample_rate": 32000}},
        )

        first = NODE_MODULE.SkebaCachedMiniMaxH3ReferenceToVideo.execute(**arguments)
        supplied_videos = arguments["ref_videos"]
        supplied_video_audio = arguments["ref_video_audios"]
        arguments["ref_videos"] = {"ref_video_0": None}
        arguments["ref_video_audios"] = {"ref_video_audio_0": None}
        original_video_loader = NODE_MODULE._load_video_source
        try:
            NODE_MODULE._load_video_source = lambda *args: self.fail(
                "video source was decoded on a compiled cache hit")
            second = NODE_MODULE.SkebaCachedMiniMaxH3ReferenceToVideo.execute(
                **arguments)
        finally:
            NODE_MODULE._load_video_source = original_video_loader
            arguments["ref_videos"] = supplied_videos
            arguments["ref_video_audios"] = supplied_video_audio

        self.assertEqual(video_vae.calls, 1)
        self.assertEqual(audio_vae.calls, 1)
        self.assertEqual(clip.visual.calls, 1)
        self.assertIn("Video: MISS -> CREATED", first[2])
        self.assertIn("Soundtrack: MISS -> CREATED", first[2])
        self.assertIn("Qwen Video: MISS -> CREATED 1 (1 blocks)", first[2])
        self.assertIn("Video: HIT", second[2])
        self.assertIn("Soundtrack: HIT", second[2])
        self.assertIn("Qwen Video: HIT 1 (1 blocks)", second[2])

        video_item = clip.items[-1]
        self.assertEqual(video_item["type"], "video")
        self.assertEqual(video_item["data"].shape[0], 2)
        payload = video_item["data"][0:2]
        merged, extra = NODE_MODULE.MiniMaxQwen3VL.preprocess_embed(
            object(), {"type": "image", "data": payload}, torch.device("cpu"))
        self.assertEqual(tuple(merged.shape), (4, 16))
        self.assertEqual(len(extra["deepstack"]), 3)

        video_source.write_bytes(b"changed-video-with-soundtrack")
        third = NODE_MODULE.SkebaCachedMiniMaxH3ReferenceToVideo.execute(**arguments)
        self.assertEqual(video_vae.calls, 2)
        self.assertEqual(audio_vae.calls, 2)
        self.assertEqual(clip.visual.calls, 2)
        self.assertIn("Video: MISS -> CREATED", third[2])
        self.assertIn("Soundtrack: MISS -> CREATED", third[2])
        self.assertIn("Qwen Video: MISS -> CREATED 1 (1 blocks)", third[2])

    def test_combined_node_keeps_references_and_first_last_keyframes(self):
        video_vae = _VAE(self.video_model)
        audio_vae = _VAE(self.audio_model, audio=True)
        clip = _Clip()
        result = NODE_MODULE.SkebaCachedMiniMaxH3ReferenceFirstLast.execute(
            clip=clip,
            vae=video_vae,
            audio_vae=audio_vae,
            prompt="the character crosses the room",
            width=32,
            height=32,
            length=5,
            cache_mode="disabled",
            ref_images={"ref_image_0": torch.zeros(1, 32, 32, 3)},
            first_frame=torch.ones(1, 24, 40, 3),
            last_frame=torch.full((1, 40, 24, 3), 0.5),
        )

        metadata = result[0][0][1]
        self.assertEqual([item["kind"] for item in metadata["minimax_refs"]],
                         ["image"])
        self.assertEqual(
            [item["resolved_frame_index"]
             for item in metadata["minimax_keyframes"]],
            [0, 4],
        )
        self.assertEqual(len(clip.items), 3)
        self.assertEqual(video_vae.calls, 3)
        self.assertIn("Frame Guides", result[2])
        self.assertIn("Keyframes: first + last", result[2])

    def test_combined_node_sizes_guides_from_second_pass_target_latent(self):
        video_vae = _VAE(self.video_model)
        audio_vae = _VAE(self.audio_model, audio=True)
        clip = _Clip()
        target_samples = types.SimpleNamespace(
            is_nested=True,
            tensors=(
                torch.zeros(1, 24, 7, 40, 68),
                torch.zeros(1, 32, 2, 50),
            ),
        )
        target_latent = {"samples": target_samples, "noise_mask": "preserved"}

        result = NODE_MODULE.SkebaCachedMiniMaxH3ReferenceFirstLast.execute(
            clip=clip,
            vae=video_vae,
            audio_vae=audio_vae,
            prompt="continue at upscale resolution",
            width=544,
            height=320,
            length=5,
            cache_mode="disabled",
            target_latent=target_latent,
            first_frame=torch.ones(1, 360, 632, 3),
        )

        self.assertIs(result[1], target_latent)
        self.assertEqual(video_vae.last_input_shape, (1, 640, 1088, 3))
        self.assertEqual(
            result[0][0][1]["minimax_keyframes"][0]["latent"].shape[-2:],
            (40, 68),
        )


if __name__ == "__main__":
    unittest.main()

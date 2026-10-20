"""Tail-only H3 continuation cache retains the exact source audio timing."""

import ast
import logging
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

try:
    import torch
    from safetensors import safe_open
    from safetensors.torch import load_file, save_file
except ImportError:
    torch = safe_open = load_file = save_file = None


ROOT = Path(__file__).resolve().parents[1]
TREE = ast.parse((ROOT / "motion_context" / "nodes.py").read_text(encoding="utf-8"))
NAMES = {
    "_pixel_frames", "_steps_for_frames", "_streams_from_latent",
    "_audio_tail_from_latent", "MiniMaxH3MotionContextSaveLatent",
    "MiniMaxH3MotionContextLoadLatent",
}
SELECTED = [node for node in TREE.body
            if isinstance(node, (ast.FunctionDef, ast.ClassDef))
            and node.name in NAMES]
NS = {
    "os": os,
    "FRAME_PER_TOKEN": (1, 4, 4, 4, 4),
    "FRAME_RESCALE": 5.0 / 3.0,
    "FPS": 24,
    "AUDIO_HZ": 40.0,
    "_LOG": logging.getLogger(__name__),
    "_st_save": save_file,
    "_st_load": load_file,
    "_st_open": safe_open,
}
exec(compile(ast.Module(body=SELECTED, type_ignores=[]), "<h3-tail-save>", "exec"), NS)


@unittest.skipUnless(torch is not None, "ComfyUI's torch/safetensors runtime required")
class TailSaveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        NS["folder_paths"] = SimpleNamespace(
            get_save_image_path=lambda prefix, root: (self.tmp.name, "clip", 1, "", ""),
            get_output_directory=lambda: self.tmp.name,
        )
        NS["_resolve_latent_path"] = lambda path, clip_index: path
        self.video = torch.arange(107, dtype=torch.float32).reshape(1, 1, 107, 1, 1)
        self.audio = torch.arange(604, dtype=torch.float32).reshape(1, 1, 1, 604)
        self.latent = {"samples": [self.video, self.audio]}

    def test_22_frame_tail_matches_original_and_preserves_audio_overhang(self):
        path, = NS["MiniMaxH3MotionContextSaveLatent"]().save(
            self.latent, "clip", 1, True, "22", 22)
        loaded, = NS["MiniMaxH3MotionContextLoadLatent"]().load(path)
        video, audio = loaded["samples"]
        self.assertEqual(video.shape[2], 7)
        self.assertEqual(audio.shape[-1], 37)
        self.assertTrue(torch.equal(video, self.video[:, :, -7:]))
        self.assertTrue(torch.equal(audio, self.audio[..., -37:]))
        original = NS["_audio_tail_from_latent"](self.latent, 22)
        cropped = NS["_audio_tail_from_latent"](loaded, 22)
        self.assertTrue(torch.equal(original[0], cropped[0]))
        self.assertAlmostEqual(original[2], cropped[2])
        # Neither input tensor is modified by the save/load path.
        self.assertEqual(self.video.shape[2], 107)
        self.assertEqual(self.audio.shape[-1], 604)

    def test_all_supported_video_windows_and_independent_audio_window(self):
        for frames, steps in ((5, 2), (22, 7), (39, 12), (56, 17)):
            with self.subTest(frames=frames):
                path, = NS["MiniMaxH3MotionContextSaveLatent"]().save(
                    self.latent, "clip", 1, True, str(frames), 96)
                loaded, = NS["MiniMaxH3MotionContextLoadLatent"]().load(path)
                self.assertEqual(loaded["samples"][0].shape[2], steps)
                self.assertEqual(loaded["samples"][1].shape[-1], 160)
                self.assertTrue(torch.equal(
                    NS["_audio_tail_from_latent"](loaded, 96)[0],
                    NS["_audio_tail_from_latent"](self.latent, 96)[0]))

    def test_default_keeps_full_streams_and_old_metadata_behavior(self):
        path, = NS["MiniMaxH3MotionContextSaveLatent"]().save(
            self.latent, "clip", 1, True)
        loaded, = NS["MiniMaxH3MotionContextLoadLatent"]().load(path)
        self.assertEqual(loaded["samples"][0].shape, self.video.shape)
        self.assertEqual(loaded["samples"][1].shape, self.audio.shape)
        self.assertNotIn("skeba_h3_original_audio_overhang_steps", loaded)


if __name__ == "__main__":
    unittest.main()

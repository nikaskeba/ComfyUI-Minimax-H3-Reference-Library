import importlib.util
from importlib.machinery import ModuleSpec
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock

import torch


ROOT = Path(__file__).resolve().parents[1]
COMFY_ROOT = ROOT.parents[1]
if str(COMFY_ROOT) not in sys.path:
    sys.path.insert(0, str(COMFY_ROOT))

PACKAGE = ModuleType("h3_tag_references")
PACKAGE.__path__ = [str(ROOT)]
PACKAGE.__spec__ = ModuleSpec("h3_tag_references", loader=None, is_package=True)
OLD_PACKAGE = sys.modules.get("h3_tag_references")
if OLD_PACKAGE is None:
    sys.modules["h3_tag_references"] = PACKAGE
SPEC = importlib.util.spec_from_file_location(
    "h3_tag_references.h3_upscale_context", ROOT / "h3_upscale_context.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
if OLD_PACKAGE is None:
    del sys.modules["h3_tag_references"]


class FakeVAE:
    def __init__(self):
        self.frames = []

    def encode(self, image):
        self.frames.append(image.clone())
        return torch.zeros((1, 24, 1, 2, 3))


def latent(frame_tokens=5):
    video = torch.zeros((1, 24, frame_tokens, 4, 6))
    audio = torch.zeros((1, 32, 2, 8))
    return {"samples": SimpleNamespace(is_nested=True, tensors=(video, audio))}


class UpscaleContextTests(unittest.TestCase):
    def setUp(self):
        self.latent = latent()
        self.frame_count = MODULE._latent_geometry(self.latent)[2]
        self.frames = torch.arange(self.frame_count, dtype=torch.float32).reshape(
            self.frame_count, 1, 1, 1).expand(-1, 1, 1, 3)

    def run_node(self, conditioning=None, frames=None, vae=None, mode="Automatic sparse"):
        conditioning = conditioning if conditioning is not None else [[torch.zeros(1), {}]]
        vae = vae if vae is not None else FakeVAE()
        with mock.patch.object(MODULE.h3, "_resize", side_effect=lambda image, *args: image):
            result = MODULE.SkebaH3UpscaleContextGuides.execute(
                conditioning, mode, self.latent,
                self.frames if frames is None else frames, vae)
        return result, vae

    def test_schema_exposes_off_by_default(self):
        schema = MODULE.SkebaH3UpscaleContextGuides.define_schema()
        self.assertEqual(schema.node_id, "SkebaH3UpscaleContextGuides")

    def test_off_is_lazy_and_preserves_conditioning(self):
        positive = [[torch.zeros(1), {"minimax_refs": ["reference"]}]]
        self.assertEqual(MODULE.SkebaH3UpscaleContextGuides.check_lazy_status(
            positive, "Off", None, None, None), [])
        result = MODULE.SkebaH3UpscaleContextGuides.execute(positive, "Off")
        self.assertIs(result[0], positive)

    def test_two_exact_interior_frames_and_existing_reference_preserved(self):
        positive = [[torch.zeros(1), {"minimax_refs": ["reference"]}]]
        result, vae = self.run_node(positive)
        positions = MODULE._sparse_positions(self.frame_count, set())
        self.assertEqual(len(positions), 2)
        self.assertEqual([kf["resolved_frame_index"] for kf in
                          result[0][0][1]["minimax_keyframes"]], positions)
        self.assertEqual([int(frame[0, 0, 0, 0]) for frame in vae.frames], positions)
        self.assertEqual(result[0][0][1]["minimax_refs"], ["reference"])
        self.assertNotIn("minimax_keyframes", positive[0][1])

    def test_skips_occupied_keyframe_without_reencoding_it(self):
        positions = MODULE._sparse_positions(self.frame_count, set())
        old = {"resolved_frame_index": positions[0], "latent": "original"}
        result, vae = self.run_node([[torch.zeros(1), {"minimax_keyframes": [old]}]])
        guides = result[0][0][1]["minimax_keyframes"]
        self.assertIs(guides[0], old)
        self.assertEqual([int(frame[0, 0, 0, 0]) for frame in vae.frames],
                         [positions[1]])

    def test_each_conditioning_entry_keeps_its_own_metadata(self):
        positions = MODULE._sparse_positions(self.frame_count, set())
        first = [torch.zeros(1), {"minimax_keyframes": [
            {"resolved_frame_index": positions[0], "latent": "first"}],
            "minimax_refs": ["A"]}]
        second = [torch.zeros(1), {"minimax_refs": ["B"]}]
        result, _ = self.run_node([first, second])
        self.assertEqual(result[0][0][1]["minimax_refs"], ["A"])
        self.assertEqual(result[0][1][1]["minimax_refs"], ["B"])
        self.assertEqual([kf["resolved_frame_index"] for kf in
                          result[0][0][1]["minimax_keyframes"]], positions)
        self.assertEqual([kf["resolved_frame_index"] for kf in
                          result[0][1][1]["minimax_keyframes"]], [positions[1]])

    def test_rejects_frame_count_mismatch_before_encoding(self):
        vae = FakeVAE()
        with self.assertRaisesRegex(ValueError, "Decode the same completed latent"):
            self.run_node(frames=self.frames[:-1], vae=vae)
        self.assertEqual(vae.frames, [])


if __name__ == "__main__":
    unittest.main()

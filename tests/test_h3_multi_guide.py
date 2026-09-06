import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import torch


ROOT = Path(__file__).resolve().parents[1]
COMFY_ROOT = ROOT.parents[1]
if str(COMFY_ROOT) not in sys.path:
    sys.path.insert(0, str(COMFY_ROOT))

SPEC = importlib.util.spec_from_file_location(
    "h3_multi_guide_test", ROOT / "h3_multi_guide.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FakeVAE:
    def __init__(self):
        self.frames = []

    def encode(self, image):
        self.frames.append(image.clone())
        return torch.zeros((1, 24, 1, 2, 3))


def h3_latent(latent_frames=3, latent_height=4, latent_width=6):
    video = torch.zeros((1, 24, latent_frames, latent_height, latent_width))
    audio = torch.zeros((1, 32, 2, 8))
    nested = SimpleNamespace(is_nested=True, tensors=(video, audio))
    return {"samples": nested}


def conditioning(existing=None):
    metadata = {}
    if existing is not None:
        metadata["minimax_keyframes"] = existing
    return [[torch.zeros((1, 1)), metadata]]


def keyframes(result):
    return result[0][0][1]["minimax_keyframes"]


class MultiFrameH3GuideTests(unittest.TestCase):
    def run_node(self, **kwargs):
        kwargs.setdefault("positive", conditioning())
        kwargs.setdefault("latent", h3_latent())
        kwargs.setdefault("vae", FakeVAE())
        with mock.patch.object(
            MODULE.h3, "_resize", side_effect=lambda image, width, height, crop: image
        ):
            return MODULE.SkebaMiniMaxH3MultiFrameGuideTest.execute(**kwargs)

    def test_bypass_is_lazy_and_returns_original_conditioning(self):
        positive = conditioning()
        needed = MODULE.SkebaMiniMaxH3MultiFrameGuideTest.check_lazy_status(
            positive,
            bypass=True,
            latent=None,
            vae=None,
            guide_batch=None,
            guide_image_1=None,
        )
        self.assertEqual(needed, [])
        result = MODULE.SkebaMiniMaxH3MultiFrameGuideTest.execute(
            positive=positive, bypass=True
        )
        self.assertIs(result[0], positive)

    def test_active_mode_requests_only_connected_lazy_inputs(self):
        needed = MODULE.SkebaMiniMaxH3MultiFrameGuideTest.check_lazy_status(
            conditioning(),
            bypass=False,
            latent=None,
            vae=None,
            guide_batch=None,
            guide_image_2=None,
        )
        self.assertEqual(needed, ["latent", "guide_batch", "guide_image_2", "vae"])

    def test_batch_sampling_covers_first_and_last_source_frames(self):
        batch = torch.arange(16.0).reshape(16, 1, 1, 1).expand(-1, 1, 1, 3)
        vae = FakeVAE()
        result = self.run_node(
            guide_batch=batch,
            batch_frame_indices="0, 1, 2, 3, 4, 5, 6, 7",
            vae=vae,
        )
        self.assertEqual([int(frame[0, 0, 0, 0]) for frame in vae.frames],
                         [0, 2, 4, 6, 9, 11, 13, 15])
        self.assertEqual([item["resolved_frame_index"] for item in keyframes(result)],
                         list(range(8)))

    def test_batch_repeats_source_when_more_guides_than_frames(self):
        batch = torch.tensor([1.0, 9.0]).reshape(2, 1, 1, 1).expand(-1, 1, 1, 3)
        vae = FakeVAE()
        self.run_node(
            guide_batch=batch,
            batch_frame_indices="0, 1, 2, 3",
            vae=vae,
        )
        self.assertEqual([int(frame[0, 0, 0, 0]) for frame in vae.frames],
                         [1, 1, 9, 9])

    def test_mixed_guides_are_sorted_and_negative_index_resolves(self):
        result = self.run_node(
            guide_batch=torch.zeros((2, 1, 1, 3)),
            batch_frame_indices="7, 2",
            guide_image_3=torch.ones((1, 1, 1, 3)),
            guide_frame_3=-1,
        )
        actual = [item["resolved_frame_index"] for item in keyframes(result)]
        frame_count = sum(
            MODULE.FRAME_PER_TOKEN[index % 5] for index in range(3)
        )
        self.assertEqual(actual, [2, 7, frame_count - 1])
        self.assertIn("individual guide 3", result[1])
        self.assertIn("estimated", result[1])

    def test_existing_keyframes_remain_and_sort_chronologically(self):
        old = {"resolved_frame_index": 7, "latent": "old"}
        result = self.run_node(
            positive=conditioning([old]),
            guide_image_1=torch.ones((1, 1, 1, 3)),
            guide_frame_1=1,
        )
        self.assertEqual(
            [item["resolved_frame_index"] for item in keyframes(result)], [1, 7]
        )
        self.assertIs(keyframes(result)[1], old)

    def test_duplicate_new_target_is_rejected_before_encoding(self):
        vae = FakeVAE()
        with self.assertRaisesRegex(ValueError, "conflicts with"):
            self.run_node(
                guide_batch=torch.zeros((1, 1, 1, 3)),
                batch_frame_indices="2",
                guide_image_1=torch.ones((1, 1, 1, 3)),
                guide_frame_1=2,
                vae=vae,
            )
        self.assertEqual(vae.frames, [])

    def test_existing_keyframe_collision_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "existing keyframe"):
            self.run_node(
                positive=conditioning([{"resolved_frame_index": 2}]),
                guide_image_1=torch.ones((1, 1, 1, 3)),
                guide_frame_1=2,
            )

    def test_invalid_or_duplicate_existing_keyframes_are_rejected(self):
        image = torch.ones((1, 1, 1, 3))
        with self.assertRaisesRegex(ValueError, "no valid resolved_frame_index"):
            self.run_node(
                positive=conditioning([{}]),
                guide_image_1=image,
                guide_frame_1=1,
            )
        with self.assertRaisesRegex(ValueError, "both target frame 2"):
            self.run_node(
                positive=conditioning([
                    {"resolved_frame_index": 2},
                    {"resolved_frame_index": 2},
                ]),
                guide_image_1=image,
                guide_frame_1=1,
            )

    def test_out_of_range_target_is_actionable(self):
        with self.assertRaisesRegex(ValueError, "outside the output video's"):
            self.run_node(
                guide_image_1=torch.ones((1, 1, 1, 3)),
                guide_frame_1=999,
            )

    def test_more_than_eight_combined_guides_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "combined batch and individual limit is 8"):
            self.run_node(
                guide_batch=torch.zeros((8, 1, 1, 3)),
                batch_frame_indices="0,1,2,3,4,5,6,7",
                guide_image_1=torch.ones((1, 1, 1, 3)),
                guide_frame_1=8,
            )

    def test_individual_image_batches_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "exactly one IMAGE frame"):
            self.run_node(
                guide_image_4=torch.ones((2, 1, 1, 3)),
                guide_frame_4=4,
            )


if __name__ == "__main__":
    unittest.main()

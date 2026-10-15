import importlib.util
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np
import torch


ROOT = Path(__file__).resolve().parents[1]
COMFY_ROOT = ROOT.parents[1]
if str(COMFY_ROOT) not in sys.path:
    sys.path.insert(0, str(COMFY_ROOT))
SPEC = importlib.util.spec_from_file_location(
    "h3_person_reference_mask_test", ROOT / "h3_person_reference_mask.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FakeBoxes:
    def __init__(self, boxes, classes=None):
        self.xyxy = torch.tensor(boxes, dtype=torch.float32).reshape(-1, 4)
        self.cls = torch.tensor(classes if classes is not None else [0] * len(boxes),
                                dtype=torch.float32)

    def __len__(self):
        return len(self.xyxy)


def result(boxes, masks=None, classes=None):
    return SimpleNamespace(boxes=FakeBoxes(boxes, classes),
                           masks=None if masks is None else SimpleNamespace(data=masks))


class PersonReferenceMaskTests(unittest.TestCase):
    def test_fill_holes_preserves_outer_boundary(self):
        mask = torch.zeros((9, 9))
        mask[1:8, 1:8] = 1
        mask[4, 4] = 0
        filled = MODULE._finish_mask(mask, 0, 0, fill_holes=True)
        self.assertEqual(float(filled[4, 4]), 1.0)
        self.assertEqual(float(filled[0, 0]), 0.0)

    def test_short_consistent_gap_is_bridged_but_crossing_is_not(self):
        left = torch.zeros((12, 12))
        right = torch.zeros((12, 12))
        left[2:8, 2:8] = 1
        right[2:8, 3:9] = 1
        output, kinds = MODULE._bridge_short_gaps(
            [left, torch.zeros_like(left), right], ["face", "none", "face"], 1)
        self.assertEqual(kinds[1], "bridged")
        self.assertGreater(int(output[1].sum()), 0)
        distant = torch.zeros_like(left)
        distant[2:8, 9:12] = 1
        _, kinds = MODULE._bridge_short_gaps(
            [left, torch.zeros_like(left), distant], ["face", "none", "face"], 1)
        self.assertEqual(kinds[1], "none")

    def test_lips_option_is_available(self):
        inputs = MODULE.SkebaPersonReferenceMask.INPUT_TYPES()
        self.assertIn("lips", inputs["required"]["subject_1_region"][0])

    def test_preview_size_is_optional_for_saved_workflows(self):
        inputs = MODULE.SkebaPersonReferenceMask.INPUT_TYPES()
        self.assertNotIn("preview_max_side", inputs["required"])
        self.assertEqual(inputs["optional"]["preview_max_side"][1]["default"], 640)

    def test_identity_selects_matching_person_not_largest(self):
        boxes = [[0, 0, 40, 80], [50, 0, 90, 80]]
        faces = [
            (np.array([10, 2, 25, 25]), np.array([0.2, 0.98])),
            (np.array([60, 2, 75, 25]), np.array([1.0, 0.0])),
        ]
        index, kind = MODULE._select_person(
            boxes, faces, np.array([1.0, 0.0]), 0.5)
        self.assertEqual((index, kind), (1, "face"))

    def test_tracking_is_short_and_requires_unambiguous_overlap(self):
        old = [0, 0, 40, 80]
        self.assertEqual(MODULE._select_person(
            [[2, 0, 42, 80]], [], np.array([1.0]), 0.5,
            previous_box=old, gap=0, max_gap=2), (0, "track"))
        self.assertEqual(MODULE._select_person(
            [[2, 0, 42, 80]], [], np.array([1.0]), 0.5,
            previous_box=old, gap=2, max_gap=2), (None, "none"))
        self.assertEqual(MODULE._select_person(
            [[2, 0, 42, 80], [3, 0, 43, 80]], [], np.array([1.0]), 0.5,
            previous_box=old), (None, "none"))

    def test_empty_detection_is_unmasked_and_wrong_model_is_actionable(self):
        self.assertEqual(MODULE._person_instances(result([]), 8, 8), ([], []))
        with self.assertRaisesRegex(ValueError, "segmentation masks"):
            MODULE._person_instances(result([[0, 0, 8, 8]]), 8, 8)

    def test_mask_follows_selected_body_and_preview_matches_frames(self):
        frames = torch.zeros((2, 8, 8, 3))
        ref = torch.ones((1, 8, 8, 3))
        masks = torch.zeros((2, 8, 8))
        masks[0, :, :4] = 1
        masks[1, :, 4:] = 1
        pred = result([[0, 0, 4, 8], [4, 0, 8, 8]], masks)
        segmenter = SimpleNamespace(predict=lambda *a, **kw: [pred])
        faces = [
            [(np.array([1, 1, 3, 3]), np.array([1.0, 0.0]))],
            [(np.array([1, 1, 3, 3]), np.array([1.0, 0.0]))],
            [(np.array([5, 1, 7, 3]), np.array([0.0, 1.0]))],
        ]
        with mock.patch.object(MODULE, "_face_recogniser", return_value=object()), \
             mock.patch.object(MODULE, "_faces", side_effect=faces), \
             mock.patch.object(MODULE, "_yolo", return_value=segmenter):
            mask, preview, status, second, details = MODULE.SkebaPersonReferenceMask().create_mask(
                frames, ref, "person_yolov8m-seg.pt", max_track_gap=0)
        self.assertEqual(tuple(mask.shape), (2, 8, 8))
        self.assertTrue(torch.all(mask[0, :, :4] == 1))
        self.assertTrue(torch.all(mask[0, :, 4:] == 0))
        self.assertTrue(torch.all(mask[1] == 0))
        self.assertEqual(tuple(preview.shape), tuple(frames.shape))
        self.assertEqual(int(second.sum()), 0)
        self.assertIn("identity/photo matched 1", status)
        self.assertEqual(json.loads(details)["track_1"][1]["pixels"], 0)

    def test_two_people_share_detection_and_keep_separate_masks(self):
        frames = torch.zeros((2, 8, 8, 3))
        ref_1, ref_2 = torch.zeros((1, 8, 8, 3)), torch.ones((1, 8, 8, 3))
        masks = torch.zeros((2, 8, 8))
        masks[0, :, :4], masks[1, :, 4:] = 1, 1
        pred = result([[0, 0, 4, 8], [4, 0, 8, 8]], masks)
        segmenter = mock.Mock()
        segmenter.predict.return_value = [pred]
        face_data = [
            [(np.array([1, 1, 3, 3]), np.array([1., 0.]))],
            [(np.array([5, 1, 7, 3]), np.array([0., 1.]))],
        ] + [[(np.array([1, 1, 3, 3]), np.array([1., 0.])),
              (np.array([5, 1, 7, 3]), np.array([0., 1.]))]] * 2
        with mock.patch.object(MODULE, "_face_recogniser", return_value=object()), \
             mock.patch.object(MODULE, "_faces", side_effect=face_data), \
             mock.patch.object(MODULE, "_yolo", return_value=segmenter):
            first, _, _, second, details = MODULE.SkebaPersonReferenceMask().create_mask(
                frames, ref_1, "person_yolov8m-seg.pt", reference_2=ref_2,
                subject_2_kind="human")
        self.assertEqual(segmenter.predict.call_count, 2)
        self.assertEqual(int(first.sum()), 64)
        self.assertEqual(int(second.sum()), 64)
        self.assertEqual(json.loads(details)["track_2"][0]["bbox"]["x"], 4)

    def test_crossing_uses_faces_before_body_tracking(self):
        frames = torch.zeros((2, 8, 8, 3))
        masks = torch.zeros((2, 8, 8))
        masks[0, :, :4], masks[1, :, 4:] = 1, 1
        pred = result([[0, 0, 4, 8], [4, 0, 8, 8]], masks)
        faces = [
            [(np.array([1, 1, 3, 3]), np.array([1., 0.]))],
            [(np.array([5, 1, 7, 3]), np.array([0., 1.]))],
            [(np.array([1, 1, 3, 3]), np.array([1., 0.])),
             (np.array([5, 1, 7, 3]), np.array([0., 1.]))],
            [(np.array([1, 1, 3, 3]), np.array([0., 1.])),
             (np.array([5, 1, 7, 3]), np.array([1., 0.]))],
        ]
        with mock.patch.object(MODULE, "_face_recogniser", return_value=object()), \
             mock.patch.object(MODULE, "_faces", side_effect=faces), \
             mock.patch.object(MODULE, "_yolo", return_value=SimpleNamespace(
                 predict=lambda *a, **kw: [pred])):
            first, _, _, second, _ = MODULE.SkebaPersonReferenceMask().create_mask(
                frames, torch.zeros((1, 8, 8, 3)), reference_2=torch.ones((1, 8, 8, 3)),
                subject_2_kind="human")
        self.assertEqual(int(first[0, :, :4].sum()), 32)
        self.assertEqual(int(first[1, :, 4:].sum()), 32)
        self.assertEqual(int(second[1, :, :4].sum()), 32)

    def test_face_and_head_regions_use_parser_and_no_match_is_empty(self):
        frames = torch.zeros((1, 8, 8, 3))
        ref = torch.zeros((1, 8, 8, 3))
        masks = torch.ones((1, 8, 8))
        pred = result([[0, 0, 8, 8]], masks)
        face = [(np.array([1, 1, 7, 7]), np.array([1., 0.]))]
        def region(_, __, mode):
            out = torch.zeros((8, 8))
            out[:2 if mode == "face" else 4, :] = 1
            return out
        with mock.patch.object(MODULE, "_face_recogniser", return_value=object()), \
             mock.patch.object(MODULE, "_faces", side_effect=[face, face, face, face]), \
             mock.patch.object(MODULE, "_yolo", return_value=SimpleNamespace(
                 predict=lambda *a, **kw: [pred])), \
             mock.patch.object(MODULE, "_face_region", side_effect=region):
            face_mask = MODULE.SkebaPersonReferenceMask().create_mask(
                frames, ref, subject_1_region="face")[0]
            head_mask = MODULE.SkebaPersonReferenceMask().create_mask(
                frames, ref, subject_1_region="head")[0]
        self.assertEqual(int(face_mask.sum()), 16)
        self.assertEqual(int(head_mask.sum()), 32)

    def test_seeded_object_and_unmatched_photo(self):
        frames = torch.zeros((2, 8, 8, 3))
        seed = torch.zeros((1, 8, 8))
        seed[0, 2:6, 2:6] = 1
        with mock.patch.object(MODULE, "_propagate_mask", return_value=seed[0]):
            first, _, _, second, details = MODULE.SkebaPersonReferenceMask().create_mask(
                frames, None, subject_1_kind="object", seed_mask_1=seed)
        self.assertEqual(int(first.sum()), 32)
        self.assertEqual(int(second.sum()), 0)
        self.assertEqual(json.loads(details)["track_1"][1]["source"], "track")
        with mock.patch.object(MODULE, "_photo_box", return_value=None):
            first = MODULE.SkebaPersonReferenceMask().create_mask(
                frames, torch.zeros((1, 8, 8, 3)), subject_1_kind="object")[0]
        self.assertEqual(int(first.sum()), 0)

    def test_object_mode_accepts_stale_human_region_from_saved_workflow(self):
        inputs = MODULE.SkebaPersonReferenceMask.INPUT_TYPES()
        self.assertIn("whole object", inputs["required"]["subject_1_region"][0])
        frames = torch.zeros((1, 8, 8, 3))
        seed = torch.zeros((1, 8, 8))
        seed[0, 2:6, 2:6] = 1
        with mock.patch.object(MODULE, "_propagate_mask", return_value=seed[0]):
            first, _, _, second, _ = MODULE.SkebaPersonReferenceMask().create_mask(
                frames, None, subject_1_kind="object", subject_1_region="head",
                seed_mask_1=seed, subject_2_kind="object",
                subject_2_region="face", seed_mask_2=seed)
        self.assertEqual(int(first.sum()), 16)
        self.assertEqual(int(second.sum()), 16)

    def test_sam3_object_tracking_uses_seed_and_keeps_tracks_separate(self):
        frames = torch.zeros((3, 8, 8, 3))
        seed_1 = torch.zeros((1, 8, 8))
        seed_2 = torch.zeros((1, 8, 8))
        seed_1[0, :, :4] = 1
        seed_2[0, :, 4:] = 1
        calls = []

        def fake_track(video, reference, seed_mask, box, seed_frame, model):
            calls.append(seed_mask.clone())
            return [seed_mask[0].clone() for _ in range(len(video))], ["seed", "sam3", "sam3"]

        with mock.patch.object(MODULE, "_sam3_object_track", side_effect=fake_track):
            first, _, status, second, details = MODULE.SkebaPersonReferenceMask().create_mask(
                frames, subject_1_kind="object", subject_2_kind="object",
                seed_mask_1=seed_1, seed_mask_2=seed_2,
                object_tracking="SAM3", sam3_model=object())
        self.assertEqual(len(calls), 2)
        self.assertEqual(int(first[:, :, :4].sum()), 96)
        self.assertEqual(int(first[:, :, 4:].sum()), 0)
        self.assertEqual(int(second[:, :, :4].sum()), 0)
        self.assertEqual(int(second[:, :, 4:].sum()), 96)
        self.assertIn("tracked 2", status)
        self.assertEqual(json.loads(details)["track_1"][1]["source"], "sam3")

    def test_sam3_tracker_propagates_both_directions_from_seed_frame(self):
        frames = torch.zeros((3, 8, 8, 3))
        seed = torch.zeros((1, 8, 8))
        seed[0, 2:6, 2:6] = 1
        lengths = []

        def forward_video(images, initial_masks, **kwargs):
            lengths.append(len(images))
            self.assertEqual(tuple(initial_masks.shape), (1, 1, 8, 8))
            return {"packed_masks": torch.ones((len(images), 1, 1, 1), dtype=torch.uint8)}

        model = SimpleNamespace(model=SimpleNamespace(
            get_dtype=lambda: torch.float32,
            diffusion_model=SimpleNamespace(forward_video=forward_video)))
        with mock.patch("comfy.model_management.load_model_gpu"), \
             mock.patch("comfy.model_management.get_torch_device", return_value="cpu"), \
             mock.patch("comfy.ldm.sam3.tracker.unpack_masks",
                        side_effect=lambda packed: torch.ones((len(packed), 8, 8))):
            masks, kinds = MODULE._sam3_object_track(
                frames, None, seed, "", 1, model)
        self.assertEqual(lengths, [2, 2])
        self.assertEqual(len(masks), 3)
        self.assertEqual(kinds, ["sam3", "seed", "sam3"])

    def test_object_photo_seeds_only_when_confident(self):
        frames = torch.zeros((2, 8, 8, 3))
        mask = torch.zeros((8, 8))
        mask[2:6, 2:6] = 1
        with mock.patch.object(MODULE, "_photo_box", side_effect=[None, (2, 2, 6, 6)]), \
             mock.patch.object(MODULE, "_mask_from_box", return_value=mask), \
             mock.patch.object(MODULE, "_propagate_mask", return_value=mask):
            first, _, _, _, details = MODULE.SkebaPersonReferenceMask().create_mask(
                frames, torch.ones((1, 8, 8, 3)), subject_1_kind="object")
        self.assertEqual(int(first.sum()), 32)
        sources = [item["source"] for item in json.loads(details)["track_1"]]
        self.assertEqual(sources, ["track", "photo"])

    def test_nonhuman_photo_candidate_and_ambiguous_match(self):
        # Synthetic red dog / blue dinosaur candidates exercise generic
        # appearance selection without relying on an external model download.
        reference = torch.zeros((8, 8, 3))
        reference[..., 0] = 1
        frame = torch.zeros((8, 16, 3))
        frame[:, :8, 0], frame[:, 8:, 2] = 1, 1
        dog = torch.zeros((8, 16))
        dino = torch.zeros((8, 16))
        dog[:, :8], dino[:, 8:] = 1, 1
        selected = MODULE._photo_candidate(reference, frame,
                                           [(None, dog), (None, dino)])
        self.assertIsNotNone(selected)
        self.assertTrue(torch.equal(selected, dog))
        self.assertIsNone(MODULE._photo_candidate(reference, frame,
                                                  [(None, dog), (None, dog)]))


if __name__ == "__main__":
    unittest.main()

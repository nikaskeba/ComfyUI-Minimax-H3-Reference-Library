import importlib.util
import json
import sys
import tempfile
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
    def test_generic_yolo_segmentation_weights_appear_in_person_selector(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / "ultralytics" / "segm"
            folder.mkdir(parents=True)
            for name in ("person_yolov8m-seg.pt", "yolo26x-seg.pt", "unrelated.pt"):
                (folder / name).touch()
            with mock.patch("folder_paths.models_dir", root):
                names = MODULE._model_names("segm", "fallback.pt")
        self.assertIn("yolo26x-seg.pt", names)
        self.assertIn("person_yolov8m-seg.pt", names)
        self.assertNotIn("unrelated.pt", names)

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

    def test_optical_flow_fills_bounded_miss_and_reports_kind(self):
        frame = torch.zeros((1, 64, 64, 3))
        frame[:, 15:45, 16:46] = 0.75
        frames = frame.expand(3, -1, -1, -1).clone()
        mask = torch.zeros((64, 64))
        mask[18:42, 20:44] = 1
        output, kinds = MODULE._stabilize_mask_sequence(
            [mask, torch.zeros_like(mask), mask.clone()],
            ["face", "none", "face"], frames, flow_gap_frames=1)
        self.assertEqual(kinds, ["face", "flow", "face"])
        self.assertGreater(float(output[1].sum()), 100)

    def test_persistence_is_short_and_never_invents_an_initial_mask(self):
        frames = torch.zeros((5, 32, 32, 3))
        mask = torch.zeros((32, 32))
        mask[8:24, 8:24] = 1
        zero = torch.zeros_like(mask)
        output, kinds = MODULE._stabilize_mask_sequence(
            [zero, mask, zero, zero, zero],
            ["none", "face", "none", "none", "none"], frames,
            persist_frames=2)
        self.assertEqual(kinds, ["none", "face", "persisted", "persisted", "none"])
        self.assertFalse(bool(output[0].any()))
        self.assertFalse(bool(output[4].any()))

    def test_detection_stride_two_keeps_full_rate_masks_and_halves_detection(self):
        frames = torch.zeros((4, 32, 32, 3))
        frames[:, 8:24, 8:24] = .8
        ref = frames[:1].clone()
        person_mask = torch.zeros((1, 32, 32))
        person_mask[:, 8:24, 8:24] = 1
        pred = result([[8, 8, 24, 24]], person_mask)
        segmenter = mock.Mock()
        segmenter.predict.return_value = [pred]
        face = [(np.array([10, 10, 20, 20]), np.array([1.0, 0.0]))]
        with mock.patch.object(MODULE, "_face_recogniser", return_value=object()), \
             mock.patch.object(MODULE, "_faces", side_effect=[face, face, face]), \
             mock.patch.object(MODULE, "_yolo", return_value=segmenter):
            masks, _, status, _, details = MODULE.SkebaPersonReferenceMask().create_mask(
                frames, ref, detection_stride=2)
        self.assertEqual(segmenter.predict.call_count, 2)
        self.assertEqual(tuple(masks.shape), (4, 32, 32))
        self.assertTrue(all(bool(frame.any()) for frame in masks))
        self.assertIn("propagated 2", status)
        self.assertEqual(json.loads(details)["track_1"][1]["source"], "propagated")

    def test_whole_person_survives_long_turn_without_face_detection(self):
        frames = torch.zeros((6, 32, 32, 3))
        frames[:, 4:29, 8:25] = .8
        ref = frames[:1].clone()
        body = torch.zeros((1, 32, 32))
        body[:, 4:29, 8:25] = 1
        prediction = result([[8, 4, 25, 29]], body)
        segmenter = SimpleNamespace(predict=lambda *args, **kwargs: [prediction])
        face = [(np.array([11, 5, 21, 15]), np.array([1.0, 0.0]))]
        with mock.patch.object(MODULE, "_face_recogniser", return_value=object()), \
             mock.patch.object(MODULE, "_faces", side_effect=[face, face] + [[]] * 5), \
             mock.patch.object(MODULE, "_yolo", return_value=segmenter):
            masks, _, status, _, details = MODULE.SkebaPersonReferenceMask().create_mask(
                frames, ref, max_track_gap=2)
        self.assertTrue(all(bool(mask.any()) for mask in masks))
        self.assertEqual(json.loads(details)["track_1"][5]["source"], "track")

    def test_head_region_survives_turn_and_reacquires_face(self):
        frames = torch.zeros((5, 32, 32, 3))
        frames[:, 4:29, 8:25] = .8
        ref = frames[:1].clone()
        body = torch.zeros((1, 32, 32))
        body[:, 4:29, 8:25] = 1
        head = torch.zeros((32, 32))
        head[5:16, 10:23] = 1
        prediction = result([[8, 4, 25, 29]], body)
        segmenter = SimpleNamespace(predict=lambda *args, **kwargs: [prediction])
        face = [(np.array([11, 5, 21, 15]), np.array([1.0, 0.0]))]
        with mock.patch.object(MODULE, "_face_recogniser", return_value=object()), \
             mock.patch.object(MODULE, "_faces", side_effect=[face, face, [], [], [], face]), \
             mock.patch.object(MODULE, "_yolo", return_value=segmenter), \
             mock.patch.object(MODULE, "_face_region", return_value=head):
            masks, _, status, _, details = MODULE.SkebaPersonReferenceMask().create_mask(
                frames, ref, subject_1_region="head", max_track_gap=2)
        sources = [item["source"] for item in json.loads(details)["track_1"]]
        self.assertEqual(sources, ["face", "head_track", "head_track", "head_track", "face"])
        self.assertIn("head tracked 3", status)
        self.assertTrue(all(bool(mask.any()) for mask in masks))

    def test_clothing_match_recovers_short_pan_without_flow_box_prediction(self):
        frames = torch.zeros((2, 32, 32, 3))
        frames[:, 10:28, 2:16, 0] = .8
        ref = frames[:1].clone()
        old = torch.zeros((1, 32, 32))
        old[:, 2:28, 2:10] = 1
        new = torch.zeros_like(old)
        new[:, 2:28, 7:15] = 1
        predictions = [result([[2, 2, 10, 28]], old),
                       result([[7, 2, 15, 28]], new)]
        segmenter = mock.Mock()
        segmenter.predict.side_effect = [[item] for item in predictions]
        face = [(np.array([3, 3, 9, 12]), np.array([1.0, 0.0]))]
        with mock.patch.object(MODULE, "_face_recogniser", return_value=object()), \
             mock.patch.object(MODULE, "_faces", side_effect=[face, face, []]), \
             mock.patch.object(MODULE, "_yolo", return_value=segmenter):
            masks, _, _, _, details = MODULE.SkebaPersonReferenceMask().create_mask(
                frames, ref, max_track_gap=2, clothing_match=True)
        self.assertTrue(bool(masks[1].any()))
        self.assertEqual(json.loads(details)["track_1"][1]["source"], "clothing")

    def test_clothing_match_rejects_ambiguous_identical_suits(self):
        frame = torch.zeros((32, 32, 3))
        frame[..., 0] = .8
        masks = []
        for left in (5, 11):
            mask = torch.zeros((32, 32))
            mask[2:28, left:left + 8] = 1
            masks.append(mask)
        boxes = [[5, 2, 13, 28], [11, 2, 19, 28]]
        anchor = MODULE._clothing_signature(frame, masks[0], boxes[0])
        self.assertIsNone(MODULE._clothing_choice(
            frame, boxes, masks, anchor, [8, 2, 16, 28], .75))

    def test_clothing_signature_distinguishes_different_outfits(self):
        red = torch.zeros((32, 32, 3))
        blue = torch.zeros_like(red)
        red[..., 0] = .9
        blue[..., 2] = .9
        mask = torch.ones((32, 32))
        box = [2, 2, 30, 30]
        first = MODULE._clothing_signature(red, mask, box)
        second = MODULE._clothing_signature(blue, mask, box)
        self.assertLess(MODULE._clothing_similarity(first, second), .7)

    def test_head_sliver_leaving_frame_is_not_carried_to_suit(self):
        import cv2
        frame = torch.zeros((32, 32, 3))
        head = torch.zeros((32, 32))
        head[:10, 10:22] = 1
        flow = np.zeros((32, 32, 2), dtype=np.float32)
        flow[..., 1] = 8  # head moves upward, leaving only two rows visible
        with mock.patch.object(cv2, "calcOpticalFlowFarneback", return_value=flow):
            carried = MODULE._propagate_mask_one_frame(
                head, frame, frame, min_retained_fraction=.35)
        self.assertIsNone(carried)

    def test_boundary_hysteresis_stays_near_current_detection(self):
        frames = torch.zeros((2, 32, 32, 3))
        first = torch.zeros((32, 32))
        second = torch.zeros((32, 32))
        first[8:24, 8:24] = 1
        second[8:24, 9:25] = 1
        output, kinds = MODULE._stabilize_mask_sequence(
            [first, second], ["face", "face"], frames,
            boundary_hysteresis=0.25)
        self.assertEqual(kinds, ["face", "face"])
        self.assertEqual(float(output[1][0, 0]), 0)
        self.assertGreater(float(output[1][12, 10]), 0.8)

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

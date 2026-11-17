"""Place a FlashHead face onto a still or moving person over a background plate."""

from __future__ import annotations

import cv2
import numpy as np
import torch


def _rgb(frame: torch.Tensor) -> np.ndarray:
    return np.clip(frame[..., :3].detach().cpu().numpy() * 255, 0, 255).astype(np.uint8)


def _candidates(detector, rgb: np.ndarray):
    faces = []
    for face in detector.get(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)):
        box = np.asarray(face.bbox, dtype=np.float32)
        points = np.asarray(face.kps, dtype=np.float32)
        embedding = getattr(face, "normed_embedding", None)
        if points.shape == (5, 2) and box[2] > box[0] and box[3] > box[1]:
            faces.append((box, points, None if embedding is None else np.asarray(embedding)))
    return faces


def _select_face(faces, reference=None, threshold=0.3):
    if not faces:
        return None
    if reference is None:
        return max(faces, key=lambda f: (f[0][2] - f[0][0]) * (f[0][3] - f[0][1]))
    scored = [(float(np.dot(f[2], reference)), f) for f in faces if f[2] is not None]
    if not scored:
        return None
    score, face = max(scored, key=lambda item: item[0])
    return face if score >= threshold else None


def _face_alpha(shape, box, region, feather):
    height, width = shape[:2]
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    fw, fh = x1 - x0, y1 - y0
    alpha = np.zeros((height, width), dtype=np.float32)
    if region == "head":
        center = (int(round(cx)), int(round(cy - .25 * fh)))
        axes = (max(1, int(round(.83 * fw))), max(1, int(round(1.05 * fh))))
    else:
        center = (int(round(cx)), int(round(cy)))
        axes = (max(1, int(round(.56 * fw))), max(1, int(round(.68 * fh))))
    cv2.ellipse(alpha, center, axes, 0, 0, 360, 1, -1)
    if feather:
        kernel = max(3, int(feather) * 2 + 1) | 1
        alpha = cv2.GaussianBlur(alpha, (kernel, kernel), 0)
    return alpha


def _warp_face(head, source_face, target_face, target_shape, region, feather):
    matrix, _ = cv2.estimateAffinePartial2D(source_face[1], target_face[1], method=cv2.LMEDS)
    if matrix is None or not np.isfinite(matrix).all():
        raise ValueError("Could not align the generated face to the person frame.")
    height, width = target_shape[:2]
    face = cv2.warpAffine(head, matrix, (width, height), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_CONSTANT)
    alpha = _face_alpha(head.shape, source_face[0], region, feather)
    alpha = cv2.warpAffine(alpha, matrix, (width, height), flags=cv2.INTER_LINEAR,
                           borderMode=cv2.BORDER_CONSTANT).clip(0, 1)
    return face, alpha


def _person_alpha(frame, face, model):
    from .h3_person_reference_mask import _person_instances

    result = model.predict(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR), verbose=False)[0]
    boxes, masks = _person_instances(result, frame.shape[0], frame.shape[1])
    cx = (face[0][0] + face[0][2]) / 2
    cy = (face[0][1] + face[0][3]) / 2
    matches = [(i, box) for i, box in enumerate(boxes)
               if box[0] <= cx <= box[2] and box[1] <= cy <= box[3]]
    if not matches:
        raise ValueError("No segmented person contains the selected face. Connect a person MASK or check the source frame.")
    index = min(matches, key=lambda item: (item[1][2] - item[1][0]) *
                (item[1][3] - item[1][1]))[0]
    return masks[index].numpy().clip(0, 1)


class SkebaTalkingAvatarComposite:
    CATEGORY = "Skeba AI Nodes - Reference/Experimental"
    FUNCTION = "composite"
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("frames", "status")
    DESCRIPTION = (
        "Track one face in person frames, align a FlashHead talking face to it, "
        "and place the person over a background. Person/background may be still "
        "images or frame batches. FlashHead and output run at 25 fps by default."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "person_frames": ("IMAGE",),
            "background": ("IMAGE",),
            "talking_head_frames": ("IMAGE",),
            "region": (["face", "head"], {"default": "face"}),
            "face_index": ("INT", {"default": 0, "min": 0, "max": 20}),
            "person_fps": ("FLOAT", {"default": 25.0, "min": 1.0, "max": 120.0}),
            "output_fps": ("FLOAT", {"default": 25.0, "min": 1.0, "max": 120.0}),
            "feather": ("INT", {"default": 20, "min": 0, "max": 100}),
            "identity_threshold": ("FLOAT", {"default": 0.3, "min": 0.0, "max": 1.0}),
        }, "optional": {
            "person_mask": ("MASK", {"tooltip": "Optional full-person mask; bypasses automatic YOLO segmentation."}),
        }}

    def composite(self, person_frames, background, talking_head_frames, region="face",
                  face_index=0, person_fps=25., output_fps=25., feather=20,
                  identity_threshold=.3, person_mask=None):
        from .h3_person_reference_mask import _face_recogniser, _yolo

        for label, images in (("person", person_frames), ("background", background),
                              ("talking head", talking_head_frames)):
            if images.ndim != 4 or images.shape[-1] < 3 or images.shape[0] < 1:
                raise ValueError(f"{label} must be a nonempty IMAGE batch [frames, height, width, channels].")
        count = len(talking_head_frames)
        person_indices = ([0] * count if len(person_frames) == 1 else
                          [int(round(i * person_fps / output_fps)) for i in range(count)])
        if max(person_indices) >= len(person_frames):
            raise ValueError("The person video ends before FlashHead. Trim the audio or provide a longer person video.")
        if len(background) not in (1, count, len(person_frames)):
            raise ValueError("Background must be one image, match FlashHead frames, or match person-video frames.")
        if person_mask is not None and len(person_mask) not in (1, len(person_frames)):
            raise ValueError("Person mask must contain one frame or match the person-video frame count.")
        detector = _face_recogniser()
        first = _rgb(person_frames[person_indices[0]])
        initial_faces = sorted(_candidates(detector, first), key=lambda f: f[0][0])
        if face_index >= len(initial_faces):
            raise ValueError(f"Person frame has {len(initial_faces)} detectable face(s); face_index={face_index} is unavailable.")
        reference = initial_faces[face_index][2]
        if reference is None:
            raise ValueError("Selected person face has no identity embedding.")
        model = None if person_mask is not None else _yolo("segm", "person_yolov8m-seg.pt")
        results = []
        tracked = skipped = 0
        last_target = None
        last_source = None
        gap = 0
        source_gap = 0
        person_cache = {}
        mask_cache = {}
        for i in range(count):
            pi = person_indices[i]
            if pi not in person_cache:
                person = _rgb(person_frames[pi])
                target = _select_face(_candidates(detector, person), reference, identity_threshold)
                person_cache[pi] = (person, target)
            person, target = person_cache[pi]
            source = _select_face(_candidates(detector, _rgb(talking_head_frames[i])))
            if target is not None:
                last_target, gap = target, 0
            else:
                gap += 1
                target = last_target if gap <= 3 else None
            if source is not None:
                last_source, source_gap = source, 0
            else:
                source_gap += 1
                source = last_source if source_gap <= 3 else None
            if len(background) == 1:
                bg_idx = 0
            elif len(background) == count:
                bg_idx = i
            else:
                bg_idx = pi
            bg = _rgb(background[bg_idx])
            height, width = person.shape[:2]
            if bg.shape[:2] != (height, width):
                bg = cv2.resize(bg, (width, height), interpolation=cv2.INTER_LINEAR)
            if target is None or source is None:
                # Never paste an untracked face onto a different person.
                results.append(person)
                skipped += 1
                continue
            if person_mask is not None:
                mi = 0 if len(person_mask) == 1 else pi
                mask = person_mask[mi].detach().cpu().numpy().astype(np.float32)
                if mask.shape != (height, width):
                    raise ValueError("Person MASK dimensions must match the person frames.")
            else:
                if pi not in mask_cache:
                    mask_cache[pi] = _person_alpha(person, target, model)
                mask = mask_cache[pi]
            mask = cv2.GaussianBlur(mask.clip(0, 1), (9, 9), 0)[..., None]
            plate = bg.astype(np.float32) * (1 - mask) + person.astype(np.float32) * mask
            warped, alpha = _warp_face(_rgb(talking_head_frames[i]), source, target,
                                       person.shape, region, feather)
            alpha = alpha[..., None]
            composed = plate * (1 - alpha) + warped.astype(np.float32) * alpha
            results.append(np.clip(composed, 0, 255).astype(np.uint8))
            tracked += 1
        images = torch.from_numpy(np.stack(results)).float().div_(255)
        return (images, f"Placed {tracked}/{count} talking-face frames; {skipped} untracked frames. "
                f"Person source: {'still' if len(person_frames) == 1 else 'video'}; output {output_fps:g} fps.")

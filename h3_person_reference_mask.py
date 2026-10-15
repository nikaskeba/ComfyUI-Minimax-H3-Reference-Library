"""Create independent, inspectable subject masks from human or object references."""

from __future__ import annotations

from pathlib import Path
import json
import math

import numpy as np
import torch
import torch.nn.functional as F


_MODELS = {}
_RECOGNISER = None
_FACE_PARSER = None


def _model_names(subfolder: str, fallback: str) -> list[str]:
    import folder_paths

    directory = Path(folder_paths.models_dir) / "ultralytics" / subfolder
    names = sorted(path.name for path in directory.glob("*.pt"))
    if subfolder == "segm":
        names = [name for name in names if "person" in name.lower()]
    elif subfolder == "bbox":
        names = [name for name in names if "face" in name.lower()]
    return names or [fallback]


def _model_path(subfolder: str, name: str) -> Path:
    import folder_paths

    # A dropdown selection must remain a filename within this local model folder.
    if Path(name).name != name:
        raise ValueError("Detector selection must be a model filename.")
    path = Path(folder_paths.models_dir) / "ultralytics" / subfolder / name
    if not path.is_file():
        raise FileNotFoundError(f"Missing {subfolder} model: {path}")
    return path


def _yolo(subfolder: str, name: str):
    path = _model_path(subfolder, name)
    key = str(path)
    if key not in _MODELS:
        from ultralytics import YOLO

        _MODELS[key] = YOLO(key)
    return _MODELS[key]


def _face_recogniser():
    global _RECOGNISER
    if _RECOGNISER is None:
        import folder_paths
        import insightface
        import onnxruntime

        root = Path(folder_paths.models_dir) / "insightface"
        pack = root / "models" / "buffalo_l"
        if not (pack / "det_10g.onnx").is_file() or not (pack / "w600k_r50.onnx").is_file():
            raise FileNotFoundError(
                f"Face identity model is missing in {pack}. Install buffalo_l locally."
            )
        available = onnxruntime.get_available_providers()
        cuda = "CUDAExecutionProvider" in available
        providers = (["CUDAExecutionProvider", "CPUExecutionProvider"] if cuda
                     else ["CPUExecutionProvider"])
        app = insightface.app.FaceAnalysis(
            name="buffalo_l", root=str(root),
            allowed_modules=["detection", "recognition"], providers=providers)
        app.prepare(ctx_id=0 if cuda else -1, det_size=(640, 640))
        _RECOGNISER = app
    return _RECOGNISER


def _bgr(image: torch.Tensor) -> np.ndarray:
    return ((image[..., :3].detach().clamp(0, 1).cpu().numpy() * 255)
            .astype(np.uint8)[..., ::-1].copy())


def _faces(app, bgr: np.ndarray):
    result = []
    for face in app.get(bgr):
        embedding = getattr(face, "normed_embedding", None)
        if embedding is not None:
            result.append((np.asarray(face.bbox, dtype=np.float32),
                           np.asarray(embedding, dtype=np.float32)))
    return result


def _iou(a, b) -> float:
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    area = max(0, x1 - x0) * max(0, y1 - y0)
    union = max(0, a[2] - a[0]) * max(0, a[3] - a[1]) \
        + max(0, b[2] - b[0]) * max(0, b[3] - b[1]) - area
    return float(area / union) if union else 0.0


def _select_person(person_boxes, face_matches, reference, threshold,
                   previous_box=None, gap=0, max_gap=6):
    """Return (person index, match kind), never select an unrelated largest body."""
    best = None
    for face_box, embedding in face_matches:
        score = float(np.dot(embedding, reference))
        if score < threshold:
            continue
        cx = (face_box[0] + face_box[2]) / 2
        cy = (face_box[1] + face_box[3]) / 2
        for index, box in enumerate(person_boxes):
            if box[0] <= cx <= box[2] and box[1] <= cy <= box[3]:
                if best is None or score > best[0]:
                    best = (score, index)
    if best is not None:
        return best[1], "face"
    if previous_box is None or gap >= max_gap or not person_boxes:
        return None, "none"
    overlaps = sorted(((_iou(box, previous_box), index)
                       for index, box in enumerate(person_boxes)), reverse=True)
    if overlaps[0][0] < 0.25:
        return None, "none"
    if len(overlaps) > 1 and overlaps[1][0] > overlaps[0][0] * 0.8:
        return None, "none"
    return overlaps[0][1], "track"


def _person_instances(result, height: int, width: int, class_filter=0):
    if len(result.boxes) == 0:
        return [], []
    if result.masks is None:
        raise ValueError("The selected person model has no segmentation masks. "
                         "Select a *-seg.pt model from models/ultralytics/segm.")
    boxes = result.boxes.xyxy.detach().cpu().numpy()
    classes = result.boxes.cls.detach().cpu().numpy()
    masks = result.masks.data
    if masks.ndim != 3 or len(masks) != len(boxes):
        raise ValueError("Person detector returned mismatched boxes and masks.")
    indices = [i for i, value in enumerate(classes)
               if class_filter is None or int(value) == class_filter]
    selected_boxes = [boxes[i] for i in indices]
    selected_masks = []
    for i in indices:
        mask = masks[i:i + 1, None].float()
        if mask.shape[-2:] != (height, width):
            mask = F.interpolate(mask, size=(height, width), mode="bilinear",
                                 align_corners=False)
        selected_masks.append(mask[0, 0].detach().cpu())
    return selected_boxes, selected_masks


def _fill_mask_holes(mask: torch.Tensor) -> torch.Tensor:
    """Fill enclosed black islands without expanding the exterior silhouette."""
    import cv2

    selected = (mask.detach().cpu().numpy() >= 0.5).astype(np.uint8)
    padded = cv2.copyMakeBorder(selected, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
    outside = (1 - padded).copy()
    flood_mask = np.zeros((outside.shape[0] + 2, outside.shape[1] + 2), np.uint8)
    cv2.floodFill(outside, flood_mask, (0, 0), 2)
    holes = outside[1:-1, 1:-1] == 1
    return torch.from_numpy(np.maximum(selected, holes.astype(np.uint8)).astype(np.float32))


def _mask_box(mask: torch.Tensor):
    points = torch.nonzero(mask >= 0.5)
    if points.numel() == 0:
        return None
    y0, x0 = points.min(dim=0).values.tolist()
    y1, x1 = points.max(dim=0).values.tolist()
    return (x0, y0, x1 + 1, y1 + 1)


def _bridge_short_gaps(masks: list[torch.Tensor], kinds: list[str], limit: int):
    """Repair only short gaps between spatially consistent detections."""
    if limit <= 0:
        return masks, kinds
    masks, kinds = list(masks), list(kinds)
    index = 0
    while index < len(masks):
        if bool(masks[index].any()):
            index += 1
            continue
        first = index
        while index < len(masks) and not bool(masks[index].any()):
            index += 1
        last = index - 1
        if first == 0 or index == len(masks) or last - first + 1 > limit:
            continue
        left, right = masks[first - 1], masks[index]
        left_box, right_box = _mask_box(left), _mask_box(right)
        if left_box is None or right_box is None or _iou(left_box, right_box) < 0.35:
            continue
        left_area, right_area = int((left >= 0.5).sum()), int((right >= 0.5).sum())
        if min(left_area, right_area) * 2 < max(left_area, right_area):
            continue
        for position in range(first, index):
            # Use the closer confirmed silhouette. Blending masks can erase a
            # thin face or lip region; copying does not invent a new identity.
            masks[position] = (left if position - first < index - 1 - position else right).clone()
            kinds[position] = "bridged"
    return masks, kinds


def _finish_mask(mask: torch.Tensor, expand: int, feather: int,
                 fill_holes: bool = False) -> torch.Tensor:
    mask = (mask >= 0.5).float()
    if fill_holes:
        mask = _fill_mask_holes(mask)
    if expand:
        kernel = expand * 2 + 1
        mask = F.max_pool2d(mask[None, None], kernel, stride=1,
                            padding=expand)[0, 0]
    if feather:
        import cv2

        radius = feather * 2 + 1
        blurred = cv2.GaussianBlur(mask.numpy(), (radius, radius),
                                   sigmaX=max(0.1, feather / 2))
        mask = torch.from_numpy(blurred)
    return mask.clamp(0, 1)


def _face_parser():
    """Load the local FaceXLib ParseNet checkpoint only for face/head mode."""
    global _FACE_PARSER
    if _FACE_PARSER is None:
        import folder_paths
        from facexlib.parsing.parsenet import ParseNet

        path = Path(folder_paths.models_dir) / "facedetection" / "parsing_parsenet.pth"
        if not path.is_file():
            raise FileNotFoundError(
                f"Face/head masks need the FaceXLib ParseNet checkpoint at {path}."
            )
        model = ParseNet(in_size=512, out_size=512, parsing_ch=19)
        state = torch.load(path, map_location="cpu", weights_only=True)
        model.load_state_dict(state, strict=True)
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        _FACE_PARSER = model.eval().to(device)
    return _FACE_PARSER


def _face_region(frame: torch.Tensor, face_box, region: str) -> torch.Tensor:
    """Segment the visible face/head in a detected face crop, at frame resolution."""
    height, width = frame.shape[:2]
    left, top, right, bottom = [float(v) for v in face_box]
    side = max(right - left, bottom - top) * 1.9
    cx, cy = (left + right) / 2, (top + bottom) / 2
    x0, y0 = max(0, math.floor(cx - side / 2)), max(0, math.floor(cy - side / 2))
    x1, y1 = min(width, math.ceil(cx + side / 2)), min(height, math.ceil(cy + side / 2))
    result = torch.zeros((height, width), dtype=torch.float32)
    if x1 - x0 < 8 or y1 - y0 < 8:
        return result
    crop = frame[y0:y1, x0:x1, :3].detach().cpu().float()
    parser = _face_parser()
    crop = crop.to(next(parser.parameters()).device)
    resized = F.interpolate(crop.permute(2, 0, 1)[None], size=(512, 512),
                            mode="bilinear", align_corners=False)
    with torch.inference_mode():
        logits = parser(resized.mul(2).sub(1))
    if isinstance(logits, (tuple, list)):
        logits = logits[0]
    labels = F.interpolate(logits.float(), size=(y1 - y0, x1 - x0),
                           mode="bilinear", align_corners=False).argmax(dim=1)[0].cpu()
    # FaceXLib ParseNet/CelebAMask-HQ order: skin, facial features and ears.
    classes = {11, 12} if region == "lips" else set(range(1, 13))
    if region == "head":
        classes.update((13, 14))  # hair and hat
    local = torch.zeros_like(labels, dtype=torch.bool)
    for class_id in classes:
        local |= labels == class_id
    result[y0:y1, x0:x1] = local.float()
    return result


def _box_from_input(value, width: int, height: int):
    """Accept an optional JSON {x,y,width,height} seed box."""
    if value is None or value == "":
        return None
    try:
        box = json.loads(value) if isinstance(value, str) else value
        x, y, w, h = (float(box[key]) for key in ("x", "y", "width", "height"))
    except (ValueError, TypeError, KeyError) as error:
        raise ValueError("Seed box must be JSON with x, y, width, height.") from error
    if not all(math.isfinite(v) for v in (x, y, w, h)) or w <= 0 or h <= 0:
        raise ValueError("Seed box coordinates must be finite with positive size.")
    x0, y0 = max(0, int(x)), max(0, int(y))
    x1, y1 = min(width, int(x + w)), min(height, int(y + h))
    if x1 <= x0 or y1 <= y0:
        raise ValueError("Seed box falls outside the video frame.")
    return x0, y0, x1, y1


def _mask_from_box(frame: torch.Tensor, box) -> torch.Tensor:
    """GrabCut within a seed box; retain the box if GrabCut cannot converge."""
    import cv2
    height, width = frame.shape[:2]
    x0, y0, x1, y1 = box
    mask = np.zeros((height, width), dtype=np.uint8)
    mask[y0:y1, x0:x1] = 1
    if x0 == 0 and y0 == 0 and x1 == width and y1 == height:
        return torch.from_numpy(mask).float()
    bgr = _bgr(frame)
    grab = np.zeros((height, width), dtype=np.uint8)
    bg, fg = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(bgr, grab, (x0, y0, x1 - x0, y1 - y0), bg, fg,
                    3, cv2.GC_INIT_WITH_RECT)
        mask = np.where((grab == cv2.GC_FGD) | (grab == cv2.GC_PR_FGD), 1, 0).astype(np.uint8)
    except cv2.error:
        pass
    if not mask.any():
        mask[y0:y1, x0:x1] = 1
    return torch.from_numpy(mask).float()


def _photo_box(reference: torch.Tensor, frame: torch.Tensor):
    """Conservative local-feature match for an object photo; never guess a body."""
    import cv2
    ref_gray = cv2.cvtColor(_bgr(reference), cv2.COLOR_BGR2GRAY)
    frame_gray = cv2.cvtColor(_bgr(frame), cv2.COLOR_BGR2GRAY)
    detector = cv2.SIFT_create()
    ref_points, ref_desc = detector.detectAndCompute(ref_gray, None)
    frame_points, frame_desc = detector.detectAndCompute(frame_gray, None)
    if ref_desc is None or frame_desc is None or len(ref_points) < 8:
        return None
    pairs = cv2.BFMatcher().knnMatch(ref_desc, frame_desc, k=2)
    good = [a for pair in pairs if len(pair) == 2 for a, b in [pair]
            if a.distance < 0.7 * b.distance]
    if len(good) < 8:
        return None
    source = np.float32([ref_points[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    target = np.float32([frame_points[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    homography, inliers = cv2.findHomography(source, target, cv2.RANSAC, 4.0)
    if homography is None or inliers is None or int(inliers.sum()) < 8 \
            or float(inliers.mean()) < 0.55:
        return None
    rh, rw = reference.shape[:2]
    corners = cv2.perspectiveTransform(
        np.float32([[0, 0], [rw, 0], [rw, rh], [0, rh]]).reshape(-1, 1, 2),
        homography).reshape(-1, 2)
    height, width = frame.shape[:2]
    x0, y0 = np.floor(corners.min(axis=0)).astype(int)
    x1, y1 = np.ceil(corners.max(axis=0)).astype(int)
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(width, x1), min(height, y1)
    if x1 - x0 < 8 or y1 - y0 < 8 or (x1 - x0) * (y1 - y0) > width * height * 0.9:
        return None
    return x0, y0, x1, y1


def _photo_candidate(reference: torch.Tensor, frame: torch.Tensor, candidates):
    """Choose a segmented object only when its appearance is distinctive."""
    import cv2
    ref = cv2.cvtColor(_bgr(reference), cv2.COLOR_BGR2HSV)
    ref_hist = cv2.calcHist([ref], [0, 1], None, [24, 16], [0, 180, 0, 256])
    cv2.normalize(ref_hist, ref_hist)
    bgr = _bgr(frame)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    scored = []
    for box, mask in candidates:
        binary = (mask.numpy() >= 0.5).astype(np.uint8) * 255
        if binary.sum() == 0:
            continue
        hist = cv2.calcHist([hsv], [0, 1], binary, [24, 16], [0, 180, 0, 256])
        cv2.normalize(hist, hist)
        similarity = 1.0 - cv2.compareHist(ref_hist, hist, cv2.HISTCMP_BHATTACHARYYA)
        scored.append((float(similarity), box, mask))
    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored or scored[0][0] < 0.72:
        return None
    if len(scored) > 1 and scored[0][0] - scored[1][0] < 0.08:
        return None
    return scored[0][2]


def _propagate_mask(source: torch.Tensor, target: torch.Tensor,
                    mask: torch.Tensor) -> torch.Tensor:
    import cv2
    src = cv2.cvtColor(_bgr(source), cv2.COLOR_BGR2GRAY)
    dst = cv2.cvtColor(_bgr(target), cv2.COLOR_BGR2GRAY)
    flow = cv2.calcOpticalFlowFarneback(dst, src, None, 0.5, 3, 21, 3, 5, 1.2, 0)
    height, width = src.shape
    grid_x, grid_y = np.meshgrid(np.arange(width), np.arange(height))
    warped = cv2.remap(mask.numpy().astype(np.float32),
                       (grid_x + flow[..., 0]).astype(np.float32),
                       (grid_y + flow[..., 1]).astype(np.float32),
                       cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    candidate = (warped >= 0.5).astype(np.uint8)
    if candidate.sum() < 24:
        return torch.zeros_like(mask)
    area_ratio = float(candidate.sum()) / max(1, int((mask.numpy() >= 0.5).sum()))
    if not 0.5 <= area_ratio <= 2.0:
        return torch.zeros_like(mask)
    # Reject a track that has drifted away from its source appearance.
    source_pixels = _bgr(source)[mask.numpy() >= 0.5]
    target_pixels = _bgr(target)[candidate != 0]
    if len(source_pixels) < 24 or len(target_pixels) < 24:
        return torch.zeros_like(mask)
    mean_gap = np.abs(source_pixels.mean(axis=0) - target_pixels.mean(axis=0)).mean()
    if mean_gap > 75:
        return torch.zeros_like(mask)
    return torch.from_numpy(candidate.astype(np.float32))


def _generic_track(frames: torch.Tensor, reference, seed_mask, seed_box,
                   seed_frame: int, object_candidates=None):
    count, height, width = frames.shape[:3]
    output = [torch.zeros((height, width), dtype=torch.float32) for _ in range(count)]
    kinds = ["none"] * count
    def candidates_at(index):
        return (object_candidates(index) if callable(object_candidates)
                else object_candidates[index])
    if seed_frame < 0 or seed_frame >= count:
        raise ValueError(f"Seed frame {seed_frame} is outside the video.")
    if seed_mask is not None:
        if seed_mask.ndim != 3 or seed_mask.shape[-2:] != (height, width):
            raise ValueError("Seed mask must be a MASK matching video width and height.")
        if len(seed_mask) not in (1, count):
            raise ValueError("Seed mask must have one frame or match the video frame count.")
        chosen = seed_mask[seed_frame if len(seed_mask) == count else 0].detach().cpu().float()
        if not bool((chosen >= 0.5).any()):
            raise ValueError("Selected seed mask is empty.")
        output[seed_frame], kinds[seed_frame] = (chosen >= 0.5).float(), "seed"
    else:
        box = _box_from_input(seed_box, width, height)
        if box is not None:
            output[seed_frame], kinds[seed_frame] = _mask_from_box(frames[seed_frame], box), "seed"
        elif reference is not None:
            for index in range(count):
                box = _photo_box(reference[0], frames[index])
                if box is not None:
                    seed_frame = index
                    output[index], kinds[index] = _mask_from_box(frames[index], box), "photo"
                    break
                if object_candidates is not None:
                    candidate = _photo_candidate(reference[0], frames[index],
                                                 candidates_at(index))
                    if candidate is not None:
                        seed_frame = index
                        output[index], kinds[index] = candidate, "photo"
                        break
        else:
            raise ValueError("An object track needs a reference photo, seed mask, or seed box.")
    if kinds[seed_frame] == "none":
        return output, kinds
    for direction in (1, -1):
        previous = seed_frame
        for index in range(seed_frame + direction, count if direction == 1 else -1, direction):
            if kinds[previous] == "none":
                candidate = torch.zeros((height, width))
            else:
                candidate = _propagate_mask(frames[previous], frames[index], output[previous])
            if bool(candidate.any()):
                output[index], kinds[index] = candidate, "track"
            elif reference is not None:
                box = _photo_box(reference[0], frames[index])
                if box is not None:
                    output[index], kinds[index] = _mask_from_box(frames[index], box), "photo"
                elif object_candidates is not None:
                    selected = _photo_candidate(reference[0], frames[index],
                                                candidates_at(index))
                    if selected is not None:
                        output[index], kinds[index] = selected, "photo"
            previous = index
    return output, kinds


def _sam3_object_track(frames, reference, seed_mask, seed_box, seed_frame, model):
    """Track one seeded object with ComfyUI's native SAM3 video model."""
    import comfy.model_management as mm
    from comfy.ldm.sam3.tracker import unpack_masks

    count, height, width = frames.shape[:3]
    if not 0 <= seed_frame < count:
        raise ValueError(f"Seed frame {seed_frame} is outside the video.")
    if seed_mask is not None:
        if seed_mask.ndim != 3 or seed_mask.shape[-2:] != (height, width) \
                or len(seed_mask) not in (1, count):
            raise ValueError("Seed mask must have one frame or match the video frame count and size.")
        seed = seed_mask[seed_frame if len(seed_mask) == count else 0].detach().cpu().float()
    else:
        box = _box_from_input(seed_box, width, height)
        if box is None and reference is not None:
            for index in range(count):
                box = _photo_box(reference[0], frames[index])
                if box is not None:
                    seed_frame = index
                    break
        if box is None:
            raise ValueError("SAM3 object tracking needs a seed mask, seed box, or a photo found in the video.")
        seed = _mask_from_box(frames[seed_frame], box)
    seed = (seed >= 0.5).float()
    if not bool(seed.any()):
        raise ValueError("SAM3 object seed is empty; choose a visible frame and mask or box.")

    mm.load_model_gpu(model)
    device = mm.get_torch_device()
    dtype = model.model.get_dtype()
    sam = model.model.diffusion_model

    def propagate(batch):
        from torch.nn.attention import SDPBackend, sdpa_kernel
        mm.throw_exception_if_processing_interrupted()
        # Match native SAM3 Detect's backend selection: cuDNN fused attention
        # can fail with an opaque mha_graph error on some PyTorch builds.
        with sdpa_kernel([SDPBackend.FLASH_ATTENTION,
                          SDPBackend.EFFICIENT_ATTENTION, SDPBackend.MATH]):
            result = sam.forward_video(
                images=batch[..., :3].movedim(-1, 1),
                initial_masks=seed[None, None].to(device=device, dtype=dtype),
                target_device=device, target_dtype=dtype)
        packed = result.get("packed_masks")
        if packed is None or packed.shape[1] < 1:
            return torch.zeros((len(batch), height, width))
        masks = unpack_masks(packed[:, 0]).unsqueeze(1).float()
        return F.interpolate(masks, size=(height, width), mode="bilinear",
                             align_corners=False)[:, 0].detach().cpu()

    forward = propagate(frames[seed_frame:])
    backward = propagate(frames[:seed_frame + 1].flip(0)).flip(0)[:-1] \
        if seed_frame else torch.empty((0, height, width))
    masks = torch.cat((backward, forward), dim=0)
    kinds = ["sam3" if bool(mask.any()) else "none" for mask in masks]
    kinds[seed_frame] = "seed"
    return list(masks), kinds


def _frame_diagnostics(masks, kinds):
    frames = []
    for index, (mask, kind) in enumerate(zip(masks, kinds)):
        active = (mask >= 0.5).nonzero()
        box = None
        if len(active):
            y0, x0 = active.min(dim=0).values.tolist()
            y1, x1 = active.max(dim=0).values.tolist()
            box = {"x": x0, "y": y0, "width": x1 - x0 + 1, "height": y1 - y0 + 1}
        frames.append({"frame": index, "masked": bool(len(active)),
                       "pixels": int(len(active)), "coverage": float(len(active) / mask.numel()),
                       "bbox": box, "source": kind if len(active) else "none"})
    return frames


class SkebaPersonReferenceMask:
    """Two independently selected subjects with frame-by-frame diagnostics."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "video_frames": ("IMAGE",),
            "person_model": (_model_names("segm", "person_yolov8m-seg.pt"),),
            "identity_threshold": ("FLOAT", {"default": 0.28, "min": 0.0,
                                             "max": 1.0, "step": 0.01}),
            "person_confidence": ("FLOAT", {"default": 0.35, "min": 0.05,
                                            "max": 0.95, "step": 0.05}),
            "max_track_gap": ("INT", {"default": 6, "min": 0, "max": 48}),
            "mask_expand": ("INT", {"default": 0, "min": 0, "max": 64}),
            "mask_feather": ("INT", {"default": 0, "min": 0, "max": 64}),
            "subject_1_kind": (["human", "object"],),
            "subject_1_region": (["whole person", "face", "head", "lips", "whole object"],),
            "subject_2_kind": (["off", "human", "object"],),
            "subject_2_region": (["whole person", "face", "head", "lips", "whole object"],),
            "seed_frame_1": ("INT", {"default": 0, "min": 0, "max": 999999}),
            "seed_frame_2": ("INT", {"default": 0, "min": 0, "max": 999999}),
            "seed_box_1": ("STRING", {"default": ""}),
            "seed_box_2": ("STRING", {"default": ""}),
        }, "optional": {
            "preview_max_side": ("INT", {"default": 640, "min": 256, "max": 2048,
                                        "step": 64}),
            "face_reference": ("IMAGE",),
            "reference_2": ("IMAGE",),
            "seed_mask_1": ("MASK",),
            "seed_mask_2": ("MASK",),
            "object_tracking": (["local", "SAM3"], {"default": "local"}),
            "sam3_model": ("MODEL",),
            "fill_mask_holes": ("BOOLEAN", {"default": False}),
            "bridge_gap_frames": ("INT", {"default": 0, "min": 0, "max": 24}),
        }}

    # Keep the original three socket positions for existing workflows.
    RETURN_TYPES = ("MASK", "IMAGE", "STRING", "MASK", "STRING")
    RETURN_NAMES = ("mask_1", "preview", "status", "mask_2", "frame_data_json")
    FUNCTION = "create_mask"
    CATEGORY = "Skeba AI Nodes - Reference/Mask"
    DESCRIPTION = ("Mask two independent humans or objects in decoded video. "
                   "Face/head mode uses the local ParseNet face parser.")

    def create_mask(self, video_frames, face_reference=None, person_model="person_yolov8m-seg.pt",
                    identity_threshold=0.28, person_confidence=0.35,
                    max_track_gap=6, mask_expand=0, mask_feather=0,
                    preview_max_side=640,
                    subject_1_kind="human", subject_1_region="whole person",
                    subject_2_kind="off", subject_2_region="whole person",
                    object_tracking="local", sam3_model=None,
                    seed_frame_1=0, seed_frame_2=0, seed_box_1="", seed_box_2="",
                    reference_2=None, seed_mask_1=None, seed_mask_2=None,
                    fill_mask_holes=False, bridge_gap_frames=0):
        if video_frames.ndim != 4 or video_frames.shape[0] < 1 \
                or video_frames.shape[-1] < 3:
            raise ValueError("video_frames must be a nonempty IMAGE batch.")
        count, height, width = map(int, video_frames.shape[:3])
        tracks = [
            {"kind": subject_1_kind, "region": subject_1_region,
             "reference": face_reference, "seed_mask": seed_mask_1,
             "seed_box": seed_box_1, "seed_frame": seed_frame_1},
            {"kind": subject_2_kind, "region": subject_2_region,
             "reference": reference_2, "seed_mask": seed_mask_2,
             "seed_box": seed_box_2, "seed_frame": seed_frame_2},
        ]
        for index, track in enumerate(tracks, 1):
            ref = track["reference"]
            if track["kind"] != "off" and ref is not None and (
                    ref.ndim != 4 or ref.shape[0] < 1 or ref.shape[-1] < 3):
                raise ValueError(f"Subject {index} reference must contain an RGB image.")
            if track["kind"] == "human" and ref is None:
                raise ValueError(f"Subject {index} human mode needs a face reference image.")
            # Saved workflows may retain a human region after switching the
            # track to object mode. Object masking always uses the full subject.
            if track["kind"] == "object":
                track["region"] = "whole object"
            elif track["kind"] == "human" and track["region"] == "whole object":
                track["region"] = "whole person"
        if object_tracking == "SAM3" and any(t["kind"] == "object" for t in tracks) \
                and sam3_model is None:
            raise ValueError("SAM3 object tracking needs a connected SAM3.1 model.")
        import comfy.model_management as mm
        human_tracks = [track for track in tracks if track["kind"] == "human"]
        if human_tracks:
            recogniser = _face_recogniser()
            segmenter = _yolo("segm", person_model)
            for track in human_tracks:
                candidates = _faces(recogniser, _bgr(track["reference"][0]))
                if not candidates:
                    raise ValueError("No recognizable face in the human reference photo.")
                _, track["embedding"] = max(candidates,
                    key=lambda item: (item[0][2] - item[0][0]) *
                                     (item[0][3] - item[0][1]))
                track.update(output=[], kinds=[], previous=None, gap=0)
            import comfy.utils
            progress = comfy.utils.ProgressBar(count)
            for frame_index, frame in enumerate(video_frames):
                mm.throw_exception_if_processing_interrupted()
                prediction = segmenter.predict(
                    _bgr(frame), conf=person_confidence, classes=[0],
                    retina_masks=True, verbose=False)[0]
                boxes, masks = _person_instances(prediction, height, width)
                faces = _faces(recogniser, _bgr(frame)) if boxes else []
                # Reserve direct identity matches before allowing either track
                # to use body continuity. This prevents a crossing from stealing
                # the other person's face-matched instance.
                assignments = {}
                assigned = set()
                for track in human_tracks:
                    choice, kind = _select_person(
                        boxes, faces, track["embedding"], identity_threshold,
                        max_gap=0)
                    if choice is not None and choice not in assigned:
                        assignments[id(track)] = (choice, kind)
                        assigned.add(choice)
                for track in human_tracks:
                    if id(track) not in assignments:
                        remaining = [i for i in range(len(boxes)) if i not in assigned]
                        subset = [boxes[i] for i in remaining]
                        local_choice, kind = _select_person(
                            subset, [], track["embedding"], identity_threshold,
                            previous_box=track["previous"], gap=track["gap"],
                            max_gap=max_track_gap)
                        choice = remaining[local_choice] if local_choice is not None else None
                        if choice is not None:
                            assigned.add(choice)
                        assignments[id(track)] = (choice, kind)
                for track in human_tracks:
                    choice, kind = assignments[id(track)]
                    if choice is None:
                        track["output"].append(torch.zeros((height, width)))
                        track["kinds"].append("none")
                        track["gap"] += 1
                        continue
                    assigned.add(choice)
                    selected = masks[choice]
                    if track["region"] != "whole person":
                        matched_face = None
                        for box, embedding in faces:
                            cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
                            if boxes[choice][0] <= cx <= boxes[choice][2] \
                                    and boxes[choice][1] <= cy <= boxes[choice][3] \
                                    and float(np.dot(embedding, track["embedding"])) >= identity_threshold:
                                matched_face = box
                                break
                        if matched_face is None:
                            selected = torch.zeros_like(selected)
                            kind = "none"
                        else:
                            selected = selected * _face_region(frame, matched_face,
                                                               track["region"])
                    selected = _finish_mask(selected, mask_expand, mask_feather,
                                            fill_mask_holes)
                    track["output"].append(selected)
                    track["kinds"].append(kind if bool(selected.any()) else "none")
                    track["previous"] = boxes[choice]
                    track["gap"] = 0 if kind == "face" else track["gap"] + 1
                progress.update(1)
                if frame_index == 0 or (frame_index + 1) % 24 == 0:
                    print(f"[SKEBA Reference Subject Mask] processed "
                          f"{frame_index + 1}/{count} frames", flush=True)
        photo_objects = [track for track in tracks if object_tracking == "local"
                         and track["kind"] == "object"
                         and track["reference"] is not None
                         and track["seed_mask"] is None and not track["seed_box"]]
        if photo_objects:
            import folder_paths
            object_path = (Path(folder_paths.models_dir) / "ultralytics" /
                           "segm" / "yolov8m-seg.pt")
            if object_path.is_file():
                object_model = _yolo("segm", "yolov8m-seg.pt")
                encoded_cache = {}
                def candidates_at(index):
                    import cv2
                    if index in encoded_cache:
                        return [(box, torch.from_numpy(cv2.imdecode(
                                    np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE
                                ).astype(np.float32) / 255))
                                for box, data in encoded_cache[index]]
                    mm.throw_exception_if_processing_interrupted()
                    prediction = object_model.predict(
                        _bgr(video_frames[index]), conf=person_confidence, retina_masks=True,
                        verbose=False)[0]
                    boxes, masks = _person_instances(prediction, height, width,
                                                     class_filter=None)
                    encoded_cache[index] = [
                        (box, cv2.imencode(".png", (mask.numpy().clip(0, 1) * 255).astype(np.uint8))[1].tobytes())
                        for box, mask in zip(boxes, masks)]
                    return list(zip(boxes, masks))
                for track in photo_objects:
                    track["candidates"] = candidates_at
        for track in tracks:
            if track["kind"] == "object":
                if object_tracking == "SAM3":
                    masks, kinds = _sam3_object_track(
                        video_frames, track["reference"], track["seed_mask"],
                        track["seed_box"], track["seed_frame"], sam3_model)
                else:
                    masks, kinds = _generic_track(
                        video_frames, track["reference"], track["seed_mask"],
                        track["seed_box"], track["seed_frame"],
                        track.get("candidates"))
                track["output"] = [_finish_mask(mask, mask_expand, mask_feather,
                                                fill_mask_holes)
                                   for mask in masks]
                track["kinds"] = kinds
            elif track["kind"] == "off":
                track["output"] = torch.zeros((1, height, width)).expand(count, -1, -1)
                track["kinds"] = ["none"] * count
        for track in tracks:
            if track["kind"] != "off":
                track["output"], track["kinds"] = _bridge_short_gaps(
                    track["output"], track["kinds"], int(bridge_gap_frames))
        first, second = (track["output"] if torch.is_tensor(track["output"])
                         else torch.stack(track["output"]) for track in tracks)
        scale = min(1.0, float(preview_max_side) / max(height, width))
        preview_height = max(1, round(height * scale))
        preview_width = max(1, round(width * scale))
        preview = F.interpolate(video_frames[..., :3].detach().cpu().permute(0, 3, 1, 2),
                                size=(preview_height, preview_width), mode="bilinear",
                                align_corners=False).permute(0, 2, 3, 1)
        for mask, tint_values in ((first, [0.1, 1.0, 0.2]),
                                  (second, [1.0, 0.45, 0.1])):
            tint = torch.tensor(tint_values, dtype=preview.dtype)
            small_mask = F.interpolate(mask[:, None], size=(preview_height, preview_width),
                                       mode="nearest")[:, 0]
            alpha = small_mask.to(preview.dtype)[..., None] * 0.4
            preview = preview * (1 - alpha) + tint * alpha
        data = {f"track_{index}": _frame_diagnostics(track["output"], track["kinds"])
                for index, track in enumerate(tracks, 1)}
        status_parts = []
        for index, track in enumerate(tracks, 1):
            kinds = track["kinds"]
            status_parts.append(
                f"track {index}: identity/photo matched {kinds.count('face') + kinds.count('photo')}, "
                f"seeded {kinds.count('seed')}, tracked {kinds.count('track') + kinds.count('sam3')}, "
                f"bridged {kinds.count('bridged')}, "
                f"unmasked {kinds.count('none')}")
        status = f"{count} frames: " + "; ".join(status_parts)
        return first, preview, status, second, json.dumps(data, separators=(",", ":"))

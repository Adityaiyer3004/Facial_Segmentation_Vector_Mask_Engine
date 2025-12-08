# app/services/image_processor.py
from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple, Optional

import cv2
import numpy as np

from app.utils.logging import logger
from overlay_core import generate_overlay_svg  # expects (image_bytes, seg_bytes)


@dataclass
class RegionContour:
    name: str
    points: List[Tuple[float, float]]


MIN_LANDMARKS = 10  # threshold for saying "this is a face"


# ---------- Base64 / OpenCV helpers ----------

def _decode_base64_to_bytes(image_b64: str) -> bytes:
    """Decode base64 into raw bytes."""
    try:
        return base64.b64decode(image_b64)
    except Exception as e:
        raise ValueError("Invalid base64 image data") from e


def _decode_b64_to_cv2(image_b64: str, as_gray: bool = False) -> np.ndarray:
    """Decode base64 string into an OpenCV image (BGR or GRAY)."""
    try:
        data = base64.b64decode(image_b64)
    except Exception as e:
        raise ValueError("Invalid base64 image data") from e

    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE if as_gray else cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image from base64")
    return img


def _encode_cv2_to_png_bytes(img: np.ndarray) -> bytes:
    """Encode an OpenCV image to PNG bytes."""
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise ValueError("Could not encode image to PNG")
    return buf.tobytes()


# ---------- Landmark-based rotation & cropping ----------

def _compute_rotation_matrix(
    landmarks: List[Dict[str, float]],
    width: int,
    height: int,
) -> np.ndarray:
    """
    Compute an affine rotation matrix that makes the eye-line horizontal.

    We assume MediaPipe FaceMesh-style landmarks (478 points) and use:
      - 33: outer corner of one eye
      - 263: outer corner of the other eye
    """
    if len(landmarks) <= 263:
        raise ValueError("NoFace: not enough landmarks for eye-based rotation")

    # Eye corners (0-based indices from FaceMesh)
    pL = (landmarks[33]["x"], landmarks[33]["y"])
    pR = (landmarks[263]["x"], landmarks[263]["y"])

    dx = pR[0] - pL[0]
    dy = pR[1] - pL[1]

    # Angle of the line connecting the two eyes
    angle_deg = np.degrees(np.arctan2(dy, dx))

    # For OpenCV's coordinate system, rotate by this angle to flatten eye-line
    cx, cy = width / 2.0, height / 2.0
    M = cv2.getRotationMatrix2D((cx, cy), angle_deg, 1.0)
    logger.info(f"Eye-based rotation angle: {angle_deg:.2f} degrees")

    return M


def _apply_affine_to_points(
    landmarks: List[Dict[str, float]],
    M: np.ndarray,
) -> List[Dict[str, float]]:
    """Apply a 2x3 affine transform to all landmarks."""
    transformed: List[Dict[str, float]] = []
    for lm in landmarks:
        x, y = lm["x"], lm["y"]
        x_r = M[0, 0] * x + M[0, 1] * y + M[0, 2]
        y_r = M[1, 0] * x + M[1, 1] * y + M[1, 2]
        transformed.append({"x": float(x_r), "y": float(y_r)})
    return transformed


def _rotate_images_and_landmarks(
    img: np.ndarray,
    seg: np.ndarray,
    landmarks: List[Dict[str, float]],
) -> tuple[np.ndarray, np.ndarray, List[Dict[str, float]]]:
    """
    Rotate image, segmentation map, and landmarks using the same affine transform.
    """
    h, w = img.shape[:2]
    M = _compute_rotation_matrix(landmarks, w, h)

    img_rot = cv2.warpAffine(
        img,
        M,
        (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )

    seg_rot = cv2.warpAffine(
        seg,
        M,
        (w, h),
        flags=cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )

    landmarks_rot = _apply_affine_to_points(landmarks, M)
    return img_rot, seg_rot, landmarks_rot


def _tight_crop_from_landmarks(
    img: np.ndarray,
    seg: np.ndarray,
    landmarks: List[Dict[str, float]],
    margin_ratio: float = 0.10,
    forehead_extra: float = 0.35,
    chin_extra: float = 0.12,
) -> tuple[np.ndarray, np.ndarray, List[Dict[str, float]]]:
    """
    Crop both image and segmentation map around landmarks with asymmetric margins.

    - margin_ratio: horizontal padding (left/right) as a fraction of face width.
    - forehead_extra: extra space ABOVE the topmost landmark (fraction of face height).
    - chin_extra: extra space BELOW the lowest landmark (fraction of face height).

    This explicitly gives more room to the forehead so it doesn't get cropped out.
    """
    h, w = img.shape[:2]
    pts = np.array([[lm["x"], lm["y"]] for lm in landmarks], dtype=np.float32)

    x_min, y_min = pts.min(axis=0)
    x_max, y_max = pts.max(axis=0)

    box_w = x_max - x_min
    box_h = y_max - y_min

    # Horizontal: symmetric padding
    x_min -= margin_ratio * box_w
    x_max += margin_ratio * box_w

    # Vertical: more generous at the top (forehead) than the bottom (chin/neck)
    y_min -= forehead_extra * box_h
    y_max += chin_extra * box_h

    # Clamp to image bounds
    x_min = max(0, int(x_min))
    y_min = max(0, int(y_min))
    x_max = min(w, int(x_max))
    y_max = min(h, int(y_max))

    if x_max <= x_min or y_max <= y_min:
        raise ValueError("NoFace: invalid crop bounds from landmarks")

    img_crop = img[y_min:y_max, x_min:x_max]
    seg_crop = seg[y_min:y_max, x_min:x_max]

    # Shift landmarks into the cropped coordinate frame
    landmarks_crop: List[Dict[str, float]] = []
    for lm in landmarks:
        landmarks_crop.append(
            {
                "x": float(lm["x"] - x_min),
                "y": float(lm["y"] - y_min),
            }
        )

    return img_crop, seg_crop, landmarks_crop


# ---------- Low-level wrapper (kept for compatibility) ----------

def process_image_base64(
    image_b64: str,
    segmentation_b64: Optional[str] = None,
) -> tuple[str, List[RegionContour]]:
    """
    Simple wrapper if you *just* want to call overlay_core directly
    without landmarks / rotation / crop.
    NOT what /frontal/crop/submit uses any more.
    """
    img_bytes = _decode_base64_to_bytes(image_b64)

    if segmentation_b64 is None:
        raise ValueError("segmentation_map is required for OpenCV overlay")

    seg_bytes = _decode_base64_to_bytes(segmentation_b64)

    svg, raw_contours = generate_overlay_svg(img_bytes, seg_bytes)

    contours: List[RegionContour] = [
        RegionContour(name=c.name, points=list(c.points))
        for c in raw_contours
    ]

    return svg, contours


# ---------- High-level pipeline (used by /frontal/crop/submit & job endpoints) ----------

def process_image(
    image_b64: str,
    landmarks: Optional[List[Dict[str, Any]]] = None,
    segmentation_b64: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Full pipeline:

    1. Validate landmarks & segmentation_map.
    2. Decode image + segmentation into OpenCV arrays.
    3. Auto-rotate using eye-based landmarks (FaceMesh indices 33 & 263).
    4. Tightly crop around the rotated landmarks (with extra forehead space).
    5. Encode rotated+cropped image & seg to PNG bytes.
    6. Call overlay_core.generate_overlay_svg on the cropped data.
    7. Return JSON-friendly payload.

    Raises ValueError("NoFace: ...") if we can't reliably locate a face.
    """
    logger.info("Starting image processing")

    if not segmentation_b64:
        raise ValueError("segmentation_map is required")

    # Landmark sanity check -> drives NoFace / 422
    if not landmarks or len(landmarks) < MIN_LANDMARKS:
        raise ValueError("NoFace: insufficient landmarks provided")

    # 1) Decode image & segmentation to OpenCV
    img = _decode_b64_to_cv2(image_b64, as_gray=False)
    seg = _decode_b64_to_cv2(segmentation_b64, as_gray=True)

    # 2) Ensure seg matches image size
    h, w = img.shape[:2]
    if seg.shape[:2] != (h, w):
        seg = cv2.resize(seg, (w, h), interpolation=cv2.INTER_NEAREST)

    # 3) Rotate both using landmarks (eye-based)
    img_rot, seg_rot, landmarks_rot = _rotate_images_and_landmarks(
        img,
        seg,
        landmarks,
    )

    # 4) Tight crop using rotated landmarks (forehead-aware)
    img_crop, seg_crop, landmarks_crop = _tight_crop_from_landmarks(
        img_rot,
        seg_rot,
        landmarks_rot,
        margin_ratio=0.10,
        forehead_extra=0.35,  # bump this if you still want more forehead
        chin_extra=0.12,
    )

    # 5) Encode cropped data back to PNG bytes
    img_bytes_crop = _encode_cv2_to_png_bytes(img_crop)
    seg_bytes_crop = _encode_cv2_to_png_bytes(seg_crop)

    # 6) Core overlay generation (now on upright, tightly-cropped face)
    svg, raw_contours = generate_overlay_svg(img_bytes_crop, seg_bytes_crop)

    contours_payload = [
        {
            "name": c.name,
            "points": [{"x": float(x), "y": float(y)} for (x, y) in c.points],
        }
        for c in raw_contours
    ]

    result = {
        "svg": svg,
        "mask_contours": contours_payload,
    }

    logger.info("Finished image processing")
    return result

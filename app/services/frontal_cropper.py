

# NOTE:
# This module contains an alternative frontal cropping helper for 68-pt dlib-style landmarks.
# The production pipeline for this task currently uses FaceMesh-style landmarks and
# `_tight_crop_from_landmarks` in `image_processor.py`, so this helper is not used.


from dataclasses import dataclass
from typing import Tuple

import numpy as np


@dataclass
class FrontalCropConfig:
    # Ratios you can tune later
    forehead_extra: float = 0.55   # how much *above* brows (as a fraction of face height)
    chin_extra: float = 0.20       # how much *below* chin
    side_extra: float = 0.25       # left/right padding around cheeks
    make_square: bool = True


def compute_frontal_face_box(
    landmarks: np.ndarray,
    img_w: int,
    img_h: int,
    cfg: FrontalCropConfig,
) -> Tuple[int, int, int, int]:
    """
    landmarks: np.array of shape (N, 2) in image coordinates.
    Returns (left, top, right, bottom).
    Assumes 68-pt dlib layout; change indices if yours differ.
    """

    if landmarks is None or len(landmarks) < 27:
        # Failsafe – return whole image
        return 0, 0, img_w, img_h

    # dlib 68-point indices:
    # 3, 13  -> cheeks
    # 8      -> chin
    # 19,24  -> brows
    chin = landmarks[8]
    left_cheek = landmarks[3]
    right_cheek = landmarks[13]
    left_brow = landmarks[19]
    right_brow = landmarks[24]

    chin_y = float(chin[1])
    brow_mid_y = float(left_brow[1] + right_brow[1]) / 2.0

    face_h = max(1.0, chin_y - brow_mid_y)
    face_w = max(1.0, float(right_cheek[0] - left_cheek[0]))

    # ✅ Push the top ABOVE the brows to grab forehead
    top = int(brow_mid_y - cfg.forehead_extra * face_h)
    bottom = int(chin_y + cfg.chin_extra * face_h)

    # Horizontal margins around cheeks
    left = int(left_cheek[0] - cfg.side_extra * face_w)
    right = int(right_cheek[0] + cfg.side_extra * face_w)

    # Clamp to image
    top = max(0, top)
    left = max(0, left)
    bottom = min(img_h, bottom)
    right = min(img_w, right)

    if cfg.make_square:
        width = right - left
        height = bottom - top
        side = max(width, height)

        cx = left + width // 2
        cy = top + height // 2
        half = side // 2

        left = cx - half
        right = cx + half
        top = cy - half
        bottom = cy + half

        # Clamp again
        if left < 0:
            right -= left
            left = 0
        if top < 0:
            bottom -= top
            top = 0
        if right > img_w:
            shift = right - img_w
            left -= shift
            right = img_w
        if bottom > img_h:
            shift = bottom - img_h
            top -= shift
            bottom = img_h

        left = max(0, left)
        top = max(0, top)

    return left, top, right, bottom

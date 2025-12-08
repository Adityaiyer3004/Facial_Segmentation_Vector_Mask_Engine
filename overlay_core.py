from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

import base64
import cv2
import numpy as np


@dataclass
class RegionContour:
    id: int
    name: str
    points: List[Tuple[float, float]]  # [(x, y), ...]


def _bytes_to_cv2_color(image_bytes: bytes) -> np.ndarray:
    """Decode raw image bytes into a BGR OpenCV image."""
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("overlay_core: failed to decode image bytes")
    return img


def _bytes_to_cv2_gray(image_bytes: bytes) -> np.ndarray:
    """Decode raw segmentation bytes into a GRAY OpenCV image."""
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError("overlay_core: failed to decode segmentation bytes")
    return img


def _build_svg_path(points: List[Tuple[float, float]]) -> str:
    """Convert list[(x,y)] into an SVG path 'M x0 y0 L x1 y1 ... Z'."""
    if not points:
        return ""
    parts = [f"M {points[0][0]:.1f} {points[0][1]:.1f}"]
    for x, y in points[1:]:
        parts.append(f"L {x:.1f} {y:.1f}")
    parts.append("Z")
    return " ".join(parts)


def _contours_from_segmentation(seg: np.ndarray) -> List[RegionContour]:
    """
    Given a grayscale segmentation map, extract one contour per non-zero label.

    Assumes:
      - Background label = 0
      - Each facial region has a distinct non-zero label value.

    Design:
      - The *largest* label id is treated as 'hair' and skipped.
        (Matches common face-parsing models where hair is the last class.)
      - All other labels are kept as face regions.
      - The first two face labels get nicer names:
          * face_labels[0] -> "right_cheek"
          * face_labels[1] -> "right_undereye"
    """
    h, w = seg.shape[:2]
    labels = sorted(v for v in np.unique(seg) if v != 0)
    if not labels:
        return []

    # Hair is usually the highest label id in standard face-parsing maps.
    hair_label = max(labels)
    face_labels = [lbl for lbl in labels if lbl != hair_label]

    if not face_labels:
        # Fall back: if we somehow only had hair, just skip everything.
        return []

    contours: List[RegionContour] = []
    region_id = 1

    # Nicer names for the first two face labels
    label_to_name: dict[int, str] = {}
    if len(face_labels) >= 1:
        label_to_name[face_labels[0]] = "right_cheek"
    if len(face_labels) >= 2:
        label_to_name[face_labels[1]] = "right_undereye"

    # Mild smoothing kernel for face regions only (not hair, which we removed)
    smooth_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))

    for lbl in face_labels:
        # Base mask for this label
        mask = (seg == lbl).astype(np.uint8)

        # Close small gaps / holes along boundaries without pulling in big hair chunks
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, smooth_kernel)

        mask_255 = (mask * 255).astype(np.uint8)

        # Find external contours for this label
        cnts, _ = cv2.findContours(
            mask_255, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        if not cnts:
            continue

        # Take the largest contour
        cnt = max(cnts, key=cv2.contourArea)

        # Smooth it a bit
        epsilon = 0.005 * cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, epsilon, True)

        pts = [(float(p[0][0]), float(p[0][1])) for p in approx]
        name = label_to_name.get(lbl, f"region_{region_id}")

        contours.append(
            RegionContour(
                id=region_id,
                name=name,
                points=pts,
            )
        )
        region_id += 1

    return contours


def generate_overlay_svg(
    image_bytes: bytes,
    seg_bytes: bytes,
) -> tuple[str, List[RegionContour]]:
    """
    Core function used by the high-level pipeline:

      - image_bytes: PNG/JPEG bytes of the (already rotated + cropped) face
      - seg_bytes:   PNG grayscale bytes of the (already rotated + cropped) segmentation map

    Returns:
      - svg_str: SVG markup embedding the base image + translucent region overlays
      - mask_contours: list[RegionContour] with polygon coordinates in image pixel space
    """
    # Decode both images
    img = _bytes_to_cv2_color(image_bytes)
    seg = _bytes_to_cv2_gray(seg_bytes)

    h, w = img.shape[:2]
    if seg.shape[:2] != (h, w):
        seg = cv2.resize(seg, (w, h), interpolation=cv2.INTER_NEAREST)

    # Extract region polygons
    contours = _contours_from_segmentation(seg)

    # Base64 encode original (cropped, rotated) image
    img_b64 = base64.b64encode(image_bytes).decode("ascii")

    # Build SVG
    svg_parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        '  <!-- base image -->',
        f'  <image href="data:image/png;base64,{img_b64}" x="0" y="0" width="{w}" height="{h}" />',
        "",
    ]

    # Draw each region as a translucent polygon
    for c in contours:
        path_d = _build_svg_path(c.points)

        # Color by region name for a prettier overlay
        if c.name == "right_cheek":
            fill = "#bf5fff"   # purple
        elif c.name == "right_undereye":
            fill = "#00ffff"   # teal
        else:
            fill = "#ff0000"   # fallback red for any other region


        svg_parts.append(
            f'  <path d="{path_d}" '
            f'fill="{fill}" fill-opacity="0.35" '
            'stroke="#ffffff" stroke-width="2" stroke-dasharray="6 4" />'
        )


    svg_parts.append("</svg>")
    svg_str = "\n".join(svg_parts)

    return svg_str, contours

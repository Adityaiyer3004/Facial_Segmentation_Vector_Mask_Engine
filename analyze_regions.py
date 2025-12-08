# overlay_core.py
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


# Kernel size for smoothing the big skin region.
SKIN_KERNEL_SIZE = 7  # tweak to 5 / 9 if needed


def _contours_from_segmentation(seg: np.ndarray) -> List[RegionContour]:
    """
    Given a grayscale segmentation map, extract one contour per non-zero label.

    Assumes:
      - Background label = 0
      - Each facial region has a distinct non-zero label value

    Heuristics:
      - The label with the largest area is treated as "full-face skin".
      - Any *non-skin* label that touches the image border is treated as hair/edge
        and is skipped completely so we don't tint hair.
      - Among the remaining non-border labels, the largest is called "right_undereye".
    """
    h, w = seg.shape[:2]
    labels = [int(v) for v in np.unique(seg) if v != 0]

    if not labels:
        return []

    # --- compute stats per label ---
    stats: dict[int, dict] = {}
    for lbl in labels:
        ys, xs = np.where(seg == lbl)
        if len(xs) == 0:
            continue

        x_min, x_max = int(xs.min()), int(xs.max())
        y_min, y_max = int(ys.min()), int(ys.max())

        stats[lbl] = {
            "area": int(len(xs)),
            "cx": float(xs.mean()),
            "cy": float(ys.mean()),
            "x_min": x_min,
            "x_max": x_max,
            "y_min": y_min,
            "y_max": y_max,
        }

    if not stats:
        return []

    def touches_border(info: dict) -> bool:
        # allow a 1-pixel tolerance
        return (
            info["x_min"] <= 1
            or info["y_min"] <= 1
            or info["x_max"] >= w - 2
            or info["y_max"] >= h - 2
        )

    # Largest label -> assume full-face skin
    skin_label = max(stats.keys(), key=lambda l: stats[l]["area"])

    # Candidate non-skin, non-border labels (nose, lips, under-eye, etc.)
    interior_labels = [
        lbl for lbl in labels
        if lbl != skin_label and not touches_border(stats[lbl])
    ]

    # Among those, pick the largest as "right_undereye" (nice name only)
    label_to_name: dict[int, str] = {skin_label: "right_cheek"}
    if interior_labels:
        undereye_label = max(interior_labels, key=lambda l: stats[l]["area"])
        label_to_name[undereye_label] = "right_undereye"

    # Kernel for the skin smoothing
    skin_kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (SKIN_KERNEL_SIZE, SKIN_KERNEL_SIZE)
    )

    contours: List[RegionContour] = []
    region_id = 1

    for lbl in labels:
        info = stats.get(lbl)
        if info is None:
            continue

        # Skip non-skin labels that hit any image edge -> hair/edge junk
        if lbl != skin_label and touches_border(info):
            continue

        mask = (seg == lbl).astype(np.uint8)

        # For the big skin region, smooth out thin protrusions (hair spikes)
        if lbl == skin_label:
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, skin_kernel)

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
            'stroke="#ffffff" stroke-width="2" />'
        )

    svg_parts.append("</svg>")
    svg_str = "\n".join(svg_parts)

    return svg_str, contours

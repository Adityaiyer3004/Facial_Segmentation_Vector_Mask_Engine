from pathlib import Path
import re

import numpy as np
from PIL import Image, ImageDraw


DATA_DIR = Path("data")
OUT_DIR = Path("output")


def load_image(name: str) -> Image.Image:
    path = DATA_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Missing image: {path}")
    return Image.open(path).convert("RGB")


def load_segmentation(name: str) -> Image.Image:
    path = DATA_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Missing segmentation map: {path}")
    # keep as single-channel labels
    return Image.open(path).convert("L")


def parse_polygon_from_html(html_path: Path, path_index: int = -1):
    """
    Parse a polygon from an exported HTML/SVG file.

    In these QOVES files:
      - path[0] = big face outline (same in both files)
      - path[1] = actual region (cheek or undereye)

    So by default we take the *last* path (index = -1).
    """
    text = html_path.read_text(encoding="utf-8")

    # find all path 'd' attributes
    ds = re.findall(r'<path[^>]*\sd="([^"]+)"', text)
    if not ds:
        raise ValueError(f"No <path d=\"...\"> found in {html_path}")

    # choose which path to use (last by default)
    d = ds[path_index]

    # extract "x,y" pairs like 123.4,567.8
    coord_re = re.compile(r'(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)')
    coords = coord_re.findall(d)
    if not coords:
        raise ValueError(f"No coordinate pairs found in chosen path for {html_path}")

    polygon = [(float(x), float(y)) for x, y in coords]
    return polygon


def polygon_mask(size, polygon):
    """
    Return boolean mask with True inside polygon.

    size is (width, height) as used by Pillow.
    The returned NumPy array has shape (height, width).
    """
    mask_img = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask_img)
    draw.polygon(polygon, outline=1, fill=1)
    return np.array(mask_img, dtype=bool)


def colourise_segmentation(seg: Image.Image, base_size):
    """Turn label map into an RGB image using a simple deterministic colour map."""
    seg_resized = seg.resize(base_size, resample=Image.NEAREST)
    seg_np = np.array(seg_resized)
    labels = np.unique(seg_np)

    colour_seg = np.zeros((*seg_np.shape, 3), dtype=np.uint8)
    for label in labels:
        if label == 0:
            continue  # background
        l = int(label)
        r = (37 * l) % 256
        g = (91 * l) % 256
        b = (53 * l) % 256
        colour_seg[seg_np == label] = [r, g, b]

    return Image.fromarray(colour_seg)


def make_mask_index_image(cheek_mask, eye_mask):
    """
    Build an RGB image visualising which pixels belong to which mask:
      0 -> background (dark purple)
      1 -> cheek (yellow)
      2 -> undereye (cyan)
    """
    idx = cheek_mask.astype(int) + 2 * eye_mask.astype(int)
    h, w = idx.shape
    rgb = np.zeros((h, w, 3), dtype=np.uint8)

    # background
    rgb[idx == 0] = [40, 0, 60]
    # cheek
    rgb[idx == 1] = [255, 255, 0]
    # undereye
    rgb[idx == 2] = [0, 255, 255]
    # overlap (if any)
    rgb[idx == 3] = [255, 0, 255]

    return Image.fromarray(rgb)


def main():
    OUT_DIR.mkdir(exist_ok=True)

    original = load_image("original_image.png")
    seg = load_segmentation("segmentation_map.png")

    # Use the *last* <path> from each HTML: actual regions
    cheek_poly = parse_polygon_from_html(DATA_DIR / "skin_right_cheek.html", path_index=-1)
    eye_poly = parse_polygon_from_html(DATA_DIR / "skin_right_undereye.html", path_index=-1)

    cheek_mask = polygon_mask(original.size, cheek_poly)
    eye_mask = polygon_mask(original.size, eye_poly)

    print("Original size (W,H):", original.size)
    print("Cheek mask shape (H,W):", cheek_mask.shape)
    print("Undereye mask shape (H,W):", eye_mask.shape)
    print("Masks identical?:", np.array_equal(cheek_mask, eye_mask))

    # Build coloured overlay
    img_np = np.array(original)
    overlay = img_np.copy()
    overlay[cheek_mask] = [255, 0, 0]   # cheek -> red
    overlay[eye_mask] = [0, 0, 255]     # undereye -> blue
    blended = (0.6 * img_np + 0.4 * overlay).astype(np.uint8)
    blended_img = Image.fromarray(blended)

    seg_colour = colourise_segmentation(seg, original.size)
    mask_index_img = make_mask_index_image(cheek_mask, eye_mask)

    # ---- Build 2x2 grid with pure Pillow ----
    w, h = original.size
    canvas = Image.new("RGB", (2 * w, 2 * h), (255, 255, 255))

    # top-left: original
    canvas.paste(original, (0, 0))
    # top-right: segmentation labels
    canvas.paste(seg_colour, (w, 0))
    # bottom-left: blended overlay
    canvas.paste(blended_img, (0, h))
    # bottom-right: mask index map
    canvas.paste(mask_index_img, (w, h))

    out_path = OUT_DIR / "debug_regions.png"
    canvas.save(out_path)
    print(f"Saved debug visualisation to {out_path.resolve()}")


if __name__ == "__main__":
    main()

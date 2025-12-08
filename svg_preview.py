from pathlib import Path
import re
import base64
import numpy as np
from PIL import Image, ImageDraw

DATA_DIR = Path("data")
OUT_DIR = Path("output")


def load_image(name: str) -> Image.Image:
    path = DATA_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Missing image: {path}")
    return Image.open(path).convert("RGB")


def parse_polygon_from_html(html_path: Path, path_index: int = -1):
    """
    Parse a polygon from an exported HTML/SVG file.

    In these QOVES files:
      - path[0] = big face outline (same in both files)
      - path[1] = actual region (cheek or undereye)

    So by default we take the *last* path (index = -1).
    """
    text = html_path.read_text(encoding="utf-8")
    ds = re.findall(r'<path[^>]*\sd="([^"]+)"', text)
    if not ds:
        raise ValueError(f"No <path d=\"...\"> found in {html_path}")
    d = ds[path_index]

    coord_re = re.compile(r'(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)')
    coords = coord_re.findall(d)
    if not coords:
        raise ValueError(f"No coordinate pairs found in chosen path for {html_path}")

    return [(float(x), float(y)) for x, y in coords]


def polygon_mask(size, polygon):
    """Return boolean mask with True inside polygon."""
    mask_img = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask_img)
    draw.polygon(polygon, outline=1, fill=1)
    return np.array(mask_img, dtype=bool)


def centroid_from_mask(mask: np.ndarray):
    """Return (cx, cy) = centroid of True pixels."""
    ys, xs = np.where(mask)
    if ys.size == 0:
        return None
    return float(xs.mean()), float(ys.mean())


def polygon_to_svg_path(poly):
    """Convert list[(x,y)] to an SVG path string."""
    if not poly:
        return ""
    parts = [f"M {poly[0][0]:.1f} {poly[0][1]:.1f}"]
    for x, y in poly[1:]:
        parts.append(f"L {x:.1f} {y:.1f}")
    parts.append("Z")
    return " ".join(parts)


def main():
    OUT_DIR.mkdir(exist_ok=True)

    # --- load base image & polygons ---
    original = load_image("original_image.png")
    w, h = original.size

    cheek_poly = parse_polygon_from_html(DATA_DIR / "skin_right_cheek.html", path_index=-1)
    eye_poly = parse_polygon_from_html(DATA_DIR / "skin_right_undereye.html", path_index=-1)

    cheek_mask = polygon_mask(original.size, cheek_poly)
    eye_mask = polygon_mask(original.size, eye_poly)

    # centroids for text labels
    cheek_c = centroid_from_mask(cheek_mask)
    eye_c = centroid_from_mask(eye_mask)

    # base64 encode the PNG for embedding in SVG
    img_bytes = DATA_DIR.joinpath("original_image.png").read_bytes()
    img_b64 = base64.b64encode(img_bytes).decode("ascii")

    # build SVG string
    cheek_path = polygon_to_svg_path(cheek_poly)
    eye_path = polygon_to_svg_path(eye_poly)

    svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     width="{w}" height="{h}"
     viewBox="0 0 {w} {h}">
  <!-- base image -->
  <image href="data:image/png;base64,{img_b64}"
         x="0" y="0" width="{w}" height="{h}" />

  <!-- cheek region in purple -->
  <path d="{cheek_path}"
        fill="#bf5fff"
        fill-opacity="0.35"
        stroke="#ffffff"
        stroke-width="2" />

  <!-- undereye region in teal -->
  <path d="{eye_path}"
        fill="#00ffff"
        fill-opacity="0.35"
        stroke="#ffffff"
        stroke-width="2" />
"""

    # add simple numeric labels if we have centroids
    if cheek_c is not None:
        cx, cy = cheek_c
        svg += f"""  <text x="{cx:.1f}" y="{cy:.1f}"
        fill="#ffffff" font-size="36" text-anchor="middle" dominant-baseline="middle">
    1
  </text>
"""
    if eye_c is not None:
        cx, cy = eye_c
        svg += f"""  <text x="{cx:.1f}" y="{cy:.1f}"
        fill="#ffffff" font-size="36" text-anchor="middle" dominant-baseline="middle">
    2
  </text>
"""

    svg += "</svg>\n"

    out_path = OUT_DIR / "example_overlay.svg"
    out_path.write_text(svg, encoding="utf-8")
    print(f"Saved SVG overlay to: {out_path.resolve()}")


if __name__ == "__main__":
    main()

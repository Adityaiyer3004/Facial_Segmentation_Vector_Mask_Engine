from pathlib import Path
import ast

import numpy as np
from PIL import Image, ImageDraw

DATA_DIR = Path("data")
OUT_DIR = Path("output")


def load_image(name: str) -> Image.Image:
    path = DATA_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Missing image: {path}")
    return Image.open(path).convert("RGB")


def load_landmarks(path: Path):
    """
    landmarks.txt is a Python dict string like:
    {'landmarks': [[{'x': ..., 'y': ...}, ...]]}

    We parse it safely with ast.literal_eval and return a list of (x, y).
    """
    txt = path.read_text(encoding="utf-8")
    data = ast.literal_eval(txt)

    # Some detectors support multiple faces; here we just take the first one.
    raw = data["landmarks"][0]

    pts = [(float(p["x"]), float(p["y"])) for p in raw]
    return pts


def draw_landmarks(img: Image.Image, points, radius: int = 3) -> Image.Image:
    """
    Draw small white circles at each landmark point.
    """
    out = img.copy()
    draw = ImageDraw.Draw(out)

    for x, y in points:
        # (x, y) are in image coordinates (float).
        # We draw a small filled circle.
        bbox = (x - radius, y - radius, x + radius, y + radius)
        draw.ellipse(bbox, outline="white", fill="white")

    return out


def main():
    OUT_DIR.mkdir(exist_ok=True)

    img = load_image("original_image.png")
    lm_path = DATA_DIR / "landmarks.txt"
    pts = load_landmarks(lm_path)

    print(f"Loaded {len(pts)} landmarks")

    overlay = draw_landmarks(img, pts, radius=2)

    out_path = OUT_DIR / "landmarks_overlay.png"
    overlay.save(out_path)
    print(f"Saved landmarks overlay to: {out_path.resolve()}")


if __name__ == "__main__":
    main()

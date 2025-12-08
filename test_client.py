# test_client.py
from __future__ import annotations

import ast          # <-- use this instead of json for landmarks.txt
import base64
from pathlib import Path

import requests

API_URL = "http://127.0.0.1:8000/api/v1/frontal/crop/submit"


def to_b64(path: str) -> str:
    data = Path(path).read_bytes()
    return base64.b64encode(data).decode("ascii")


def load_landmarks(path: str):
    """
    landmarks.txt contains a *Python* dict literal like:
      {'landmarks': [[{'x':..., 'y':...}, ...], ...]}

    So we must use ast.literal_eval, NOT json.loads.
    """
    raw = Path(path).read_text()
    obj = ast.literal_eval(raw)     # <-- this is the critical change
    # take first face's landmarks
    return obj["landmarks"][0]


def main():
    # 1) Encode image + segmentation map
    image_b64 = to_b64("data/original_image.png")
    seg_b64 = to_b64("data/segmentation_map.png")

    # 2) Load landmarks from landmarks.txt
    landmarks = load_landmarks("data/landmarks.txt")

    # sanity check
    print(f"Loaded {len(landmarks)} landmarks, first 3:", landmarks[:3])

    payload = {
        "image": image_b64,
        "landmarks": landmarks,         # list of {x, y}
        "segmentation_map": seg_b64,    # base64 seg map
    }

    resp = requests.post(API_URL, json=payload)
    print("Status:", resp.status_code)

    if resp.status_code != 200:
        print("Error body:", resp.text)
        return

    data = resp.json()

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    svg_path = output_dir / "example_overlay.svg"
    svg_path.write_text(data["svg"], encoding="utf-8")

    print("Wrote SVG to:", svg_path)
    print("Mask regions returned:", [r["name"] for r in data["mask_contours"]])

    if data["mask_contours"]:
        first = data["mask_contours"][0]["points"][:3]
        print("First contour point sample:", first)


if __name__ == "__main__":
    main()

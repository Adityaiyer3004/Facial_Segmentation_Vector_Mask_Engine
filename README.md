# QOVES Backend Task – Frontal Crop API

This repo contains my implementation of the QOVES backend take-home task.

It exposes a FastAPI service that:

- Accepts a frontal face image + 2D facial landmarks + segmentation map
- Rotates and crops the face into a consistent frontal view
- Builds an SVG overlay with highlighted right cheek + right undereye
- Caches processed results in Postgres
- Exposes both synchronous and async “job” style endpoints
- Emits Prometheus metrics and ships with a docker-compose stack
  (app + Postgres + Prometheus)

---

## Tech Stack

- **Language:** Python 3.11
- **Web framework:** FastAPI + Uvicorn
- **Image processing:** OpenCV (`cv2`), NumPy
- **DB:** SQLite (local dev) / Postgres 16 (docker-compose)
- **ORM:** SQLAlchemy
- **Metrics:** Prometheus `/metrics` endpoint + Prometheus server
- **Containerisation:** Docker + docker-compose

---

## Project Structure (high level)

- `app/main.py` – FastAPI app, mounts API router, `/metrics`, `/health`
- `app/api/routes.py` – All HTTP endpoints (`/frontal/crop/submit`, job APIs, raw debug)
- `app/api/models.py` – Pydantic request/response models
- `app/core/config.py` – Settings (reads `DATABASE_URL`, etc.)
- `app/core/database.py` – SQLAlchemy engine/session + `processed_images` model
- `app/services/frontal_cropper.py` – Face crop box computation from landmarks
- `app/services/image_processor.py` – High-level pipeline:
  - decode base64
  - rotate based on eye landmarks
  - compute crop
  - apply segmentation
  - call `overlay_core.generate_overlay_svg`
- `overlay_core.py` – SVG overlay generator + contour extraction
- `app/services/cache_service.py` – Cache key generation + Postgres read/write
- `app/services/tasks.py` – In-memory job store + background job runner
- `docker-compose.yml` – app + Postgres + Prometheus stack
- `prometheus.yml` – Prometheus scrape config
- `sample_payload.json` – Example request body for testing

---

## Running Locally (no Docker)

Requirements:

- Python 3.11
- `virtualenv` or `venv`

```bash
cd qoves-task
python -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt

# Use SQLite by default
export DATABASE_URL="sqlite:///./qoves_cache.db"

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000


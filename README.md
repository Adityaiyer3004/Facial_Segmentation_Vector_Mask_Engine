# QOVES Backend Task – Frontal Crop & Overlay API

This repository contains my implementation of the QOVES **Backend Task – FastAPI (Task 1, July 2025)**.

The service:

- Accepts a **portrait image**, **2D facial landmarks**, and a **segmentation map**  
- Automatically **rotates** the face to upright and **crops** it to a consistent frontal view  
- Generates an **SVG overlay** with smooth contour masks for key regions (right cheek, right undereye, nose, lips, face outline, etc.)  
- **Caches** processed results in a relational database (SQLite / Postgres)  
- Exposes both **synchronous** and **asynchronous (job-style)** APIs  
- Publishes **Prometheus metrics** and runs as a **docker-compose stack** (app + Postgres + Prometheus)

---

## 1. Tech Stack

- **Language:** Python 3.11  
- **Framework:** FastAPI + Uvicorn  
- **Image processing:** OpenCV (`cv2`), NumPy  
- **Database:**
  - Local dev: SQLite
  - Docker: Postgres 16
- **ORM:** SQLAlchemy  
- **Metrics:** `prometheus_client` (`/metrics` endpoint) + Prometheus server  
- **Logging:** `rich` (colourful structured logs)  
- **Containerisation:** Docker + docker-compose  
- **Tests:** FastAPI `TestClient` integration tests

---

## 2. High-Level Architecture

**Core layout**

- `app/main.py`  
  - Creates the FastAPI app  
  - Mounts API router at `/api/v1`  
  - Adds `/health` and `/metrics` endpoints  
  - Initialises the database and creates the cache table if needed

- `app/api/routes.py`  
  - `POST /api/v1/frontal/crop/submit` – main crop + SVG endpoint  
  - `POST /api/v1/crop/submit` – async job submission (non-blocking)  
  - `GET  /api/v1/crop/status/{job_id}` – async job status  
  - `POST /api/v1/crop/submit/raw` – debug endpoint returning full JSON payload

- `app/api/models.py`  
  - Pydantic models for request and response validation:
    - `CropSubmitRequest`
    - `SVGResponse`
    - `JobResponse`
    - `JobStatusResponse`

- `app/core/config.py`  
  - Central configuration (reads env vars like `DATABASE_URL`)

- `app/core/database.py`  
  - SQLAlchemy engine & session  
  - `ProcessedImage` model for the cache table

- `app/services/frontal_cropper.py`  
  - Computes a **frontal crop box** from 68-point landmarks
  - Uses brows, cheeks, and chin to define a padded rectangle
  - Supports tunable ratios via `FrontalCropConfig`
  - Optionally forces a **square** crop for consistent aspect ratio
  - Falls back to the whole image if landmarks are unusable

- `app/services/image_processor.py`  
  - High-level pipeline:
    1. Decode base64 image & segmentation PNG
    2. Compute eye centres from landmarks
    3. Derive rotation angle from the eye line and **rotate image + segmentation map together**
    4. Compute frontal crop box via `compute_frontal_face_box`
    5. Crop both the image and the segmentation
    6. Call `overlay_core.generate_overlay_svg` to build SVG + region contours
    7. Return `{"svg": svg_str, "mask_contours": [...]}`

- `overlay_core.py`  
  - Decodes the rotated + cropped RGB image and grayscale segmentation map
  - Treats background as label `0`
  - Treats the **highest label id as hair** and excludes it from face regions
  - For each remaining label:
    - Builds a binary mask
    - Applies **morphological closing** to seal gaps and smooth edges
    - Finds external contours, selects the largest, and simplifies it with `approxPolyDP`
    - Produces a `RegionContour` with an ID, semantic name, and polygon points
  - Generates the final SVG:
    - Embeds the base image as `data:image/png;base64,...`
    - Renders translucent polygons with white **dashed** borders over the face

- `app/services/cache_service.py`  
  - `generate_cache_key(image, landmarks, segmentation)` – SHA-256 hash over the payload
  - `get_cached_result(cache_key, db)`
  - `cache_result(cache_key, result, db)`

- `app/services/tasks.py`  
  - In-memory `JobStore` mapping job IDs → `{status, result, error}`
  - `run_crop_job(job_id, image_b64, landmarks, segmentation_b64)`:
    - Optional simulated delay
    - Calls `process_image`
    - Stores SVG result or error into `JobStore`

- `docker-compose.yml`  
  - Brings up:
    - `qoves-app` (FastAPI)
    - `qoves-db` (Postgres)
    - `qoves-prometheus` (Prometheus)

- `prometheus.yml`  
  - Targets `qoves-app:8000` and scrapes `/metrics` on a fixed interval

- `sample_payload.json`  
  - Example payload wired to the task’s source image, landmarks, and segmentation map

---

## 3. Endpoints

All endpoints are under the `/api/v1` prefix.

### 3.1 `POST /api/v1/frontal/crop/submit`

**Purpose:** Main spec endpoint – takes original image + landmarks + segmentation map and returns SVG overlay with mask contours.

**Request body**

```json
{
  "image": "<base64_encoded_original_image>",
  "landmarks": [
    { "x": 123.4, "y": 234.5 },
    { "x": 130.0, "y": 240.0 }
    // ...
  ],
  "segmentation_map": "<base64_encoded_segmentation_png>"

### 3.1 Successful response (`SVGResponse`)

```json
{
  "svg": "<svg ...>...</svg>",
  "mask_contours": [
    {
      "id": 1,
      "name": "right_cheek",
      "points": [
        { "x": 512.3, "y": 234.1 },
        { "x": 520.0, "y": 240.0 }
      ]
    },
    {
      "id": 2,
      "name": "right_undereye",
      "points": [ /* ... */ ]
    }
  ]
}

}

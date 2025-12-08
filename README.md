QOVES Backend Task – Frontal Crop & Overlay API
===============================================

This repository contains my implementation of the QOVES **Backend Task – FastAPI (Task 1, July 2025)**.

The service:

*   Accepts a **portrait image**, **2D facial landmarks**, and a **segmentation map**
    
*   Automatically **rotates** the face to upright and **crops** it to a consistent frontal view
    
*   Generates an **SVG overlay** with smooth contour masks for key regions (right cheek, right undereye, nose, lips, face outline, etc.)
    
*   **Caches** processed results in a relational database (SQLite / Postgres)
    
*   Exposes both **synchronous** and **asynchronous (job-style)** APIs
    
*   Publishes **Prometheus metrics** and runs as a **docker-compose stack** (app + Postgres + Prometheus)
    

1\. Tech Stack
--------------

*   **Language:** Python 3.11
    
*   **Framework:** FastAPI + Uvicorn
    
*   **Image processing:** OpenCV (cv2), NumPy
    
*   **Database:**
    
    *   Local dev: SQLite
        
    *   Docker: Postgres 16
        
*   **ORM:** SQLAlchemy
    
*   **Metrics:** prometheus\_client (/metrics endpoint) + Prometheus server
    
*   **Logging:** rich (coloured, structured logs)
    
*   **Containerisation:** Docker + docker-compose
    
*   **Tests:** FastAPI TestClient integration tests
    

2\. High-Level Architecture
---------------------------

**Core layout**

*   app/main.py
    
    *   Creates the FastAPI app
        
    *   Mounts API router at /api/v1
        
    *   Adds /health and /metrics endpoints
        
    *   Initialises the database and creates the cache table if needed
        
*   app/api/routes.py
    
    *   POST /api/v1/frontal/crop/submit – main crop + SVG endpoint
        
    *   POST /api/v1/crop/submit – async job submission (non-blocking)
        
    *   GET /api/v1/crop/status/{job\_id} – async job status lookup
        
    *   POST /api/v1/crop/submit/raw – debug endpoint returning full JSON payload
        
*   app/api/models.py
    
    *   Pydantic models:
        
        *   CropSubmitRequest
            
        *   SVGResponse
            
        *   JobResponse
            
        *   JobStatusResponse
            
*   app/core/config.py
    
    *   Central configuration (reads env vars like DATABASE\_URL, CACHE\_ENABLED, etc.)
        
*   app/core/database.py
    
    *   SQLAlchemy engine & session
        
    *   ProcessedImage model for the cache table (processed\_images)
        
*   app/services/frontal\_cropper.py
    
    *   Computes a **frontal crop box** from 68-point landmarks
        
    *   Uses brows, cheeks, and chin to define a padded rectangle
        
    *   Supports tunable ratios via FrontalCropConfig
        
    *   Optionally forces a **square crop** for consistent aspect ratio
        
    *   Falls back to the whole image if landmarks are unusable
        
*   app/services/image\_processor.py
    
    *   High-level pipeline:
        
        1.  Decode base64 image & segmentation PNG
            
        2.  Compute eye centres from landmarks
            
        3.  Derive rotation angle from the eye line and **rotate image + segmentation together**
            
        4.  Compute frontal crop box via compute\_frontal\_face\_box
            
        5.  Crop both the image and the segmentation
            
        6.  Call overlay\_core.generate\_overlay\_svg to build SVG + region contours
            
        7.  Return {"svg": svg\_str, "mask\_contours": \[...\]}
            
*   overlay\_core.py
    
    *   Decodes the rotated + cropped RGB image and grayscale segmentation map
        
    *   Treats background as label 0
        
    *   Treats the **highest label id as hair** and excludes it from face regions
        
    *   For each remaining label:
        
        *   Builds a binary mask
            
        *   Applies **morphological closing** to seal gaps and smooth edges
            
        *   Finds external contours, selects the largest, and simplifies it with approxPolyDP
            
        *   Produces a RegionContour with an ID, semantic name, and polygon points
            
    *   Generates the final SVG:
        
        *   Embeds the base image as data:image/png;base64,...
            
        *   Renders translucent polygons with white **dashed** borders over the face
            
*   app/services/cache\_service.py
    
    *   generate\_cache\_key(image, landmarks, segmentation) – SHA-256 hash over payload
        
    *   get\_cached\_result(cache\_key, db)
        
    *   cache\_result(cache\_key, result, db)
        
*   app/services/tasks.py
    
    *   In-memory JobStore mapping job IDs → {status, result, error}
        
    *   run\_crop\_job(job\_id, image\_b64, landmarks, segmentation\_b64):
        
        *   Optional simulated delay
            
        *   Calls process\_image
            
        *   Stores SVG result or error into JobStore
            
*   docker-compose.yml
    
    *   Brings up:
        
        *   qoves-app (FastAPI)
            
        *   qoves-db (Postgres)
            
        *   qoves-prometheus (Prometheus)
            
*   prometheus.yml
    
    *   Targets qoves-app:8000 and scrapes /metrics on a fixed interval
        
*   sample\_payload.json
    
    *   Example payload wired to the task’s source image, landmarks, and segmentation map
        

3\. Endpoints
-------------

All endpoints are under the /api/v1 prefix.

### 3.1 POST /api/v1/frontal/crop/submit

**Purpose:** Main spec endpoint – takes original image + landmarks + segmentation map and returns SVG overlay with mask contours.

#### Request body

```

{
  "image": "<base64_encoded_original_image>",
  "landmarks": [
    { "x": 123.4, "y": 234.5 },
    { "x": 130.0, "y": 240.0 }
    // ...
  ],
  "segmentation_map": "<base64_encoded_segmentation_png>"
}

```

#### Successful response (SVGResponse)

```
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
      "points": [
        { "x": 500.0, "y": 220.0 }
        // ...
      ]
    }
  ]
}

```

#### Error responses

**No usable face / invalid crop / insufficient landmarks**

```
HTTP 422
{ "detail": "NoFace" }
```
**Other validation problems**

```
HTTP 422
{ "detail": "<error message>" }
```

**Unexpected internal error**

```
HTTP 500
{ "detail": "Internal server error" }

```

### 3.2 Async Job-Style API (Bonus #1)

#### 3.2.1 POST /api/v1/crop/submit

Same request body as /frontal/crop/submit.

Returns immediately with a job ID and "pending" status:

```
{
  "id": "0eb347a3-a186-46dc-b9f6-69742924258c",
  "status": "pending"
}

```
The heavy work runs in a FastAPI BackgroundTasks worker.

#### 3.2.2 GET /api/v1/crop/status/{job\_id}

Returns job status plus SVG when completed:

```
{
  "id": "0eb347a3-a186-46dc-b9f6-69742924258c",
  "status": "completed",      // "pending" | "completed" | "failed"
  "result": "<svg ...>...</svg>",
  "error": null               // e.g. "NoFace" on failure
}

```
Unknown job\_id:

```
HTTP 404
{ "detail": "Job not found" }

```

### 3.3 POST /api/v1/crop/submit/raw

Debug endpoint that bypasses caching and returns the **full** result from process\_image() – including:

*   SVG
    
*   Contours
    
*   Optional metadata like rotation angle and crop box
    

Useful for development and visual verification.

### 3.4 Health & Metrics

*   { "status": "ok" }
    
*   GET /metrics – Prometheus metrics (request counts, latencies, etc.)
    

4\. Image Geometry & Overlay Details
------------------------------------

### 4.1 Rotation

*   Landmarks are assumed to be **68-point landmarks**.
    
*   Eye centres (left and right) are computed from their respective landmark groups.
    
*   The angle between the eye line and the horizontal is calculated.
    
*   The original image and the segmentation map are rotated together around the image centre using:
    
    *   cv2.getRotationMatrix2D
        
    *   cv2.warpAffine
        
*   This normalises head tilt so the downstream crop and contours always operate on an upright face.
    

### 4.2 Frontal Crop Box

Implemented in frontal\_cropper.py via compute\_frontal\_face\_box:

Uses:

*   Chin point
    
*   Left cheek / right cheek
    
*   Left brow / right brow
    

Calculates a base face rectangle and inflates it with tunable ratios:

*   forehead\_extra – how far above the brows to go
    
*   chin\_extra – padding below the chin
    
*   side\_extra – lateral padding around cheeks
    
*   make\_square – whether to convert to a square box
    

The box is:

*   Clamped to image boundaries
    
*   Adjusted if the square extends outside the frame
    

If landmarks are missing / invalid, the function falls back to returning the full image bounds, which upstream code interprets as **“no special crop”**.

### 4.3 Segmentation → Clean Contours

In overlay\_core.py:

*   Grayscale segmentation is loaded, with 0 treated as background.
    
*   Unique non-zero labels are extracted; the **largest label id is treated as hair** and ignored.
    

For each remaining label:

1.  Build a binary mask: seg == label
    
2.  Apply morphological closing with an elliptical 7x7 kernel to clean small gaps and jagged edges
    
3.  Find external contours, keep the largest region only
    
4.  Simplify the contour with approxPolyDP to produce a smooth polygon
    

Region naming:

*   First non-hair label → "right\_cheek"
    
*   Second non-hair label → "right\_undereye"
    
*   Others → "region\_3", "region\_4", …
    

### 4.4 SVG Styling

Each RegionContour is rendered as:

```
<path
  d="M x0 y0 L x1 y1 ... Z"
  fill="#bf5fff"           <!-- for right_cheek -->
  fill-opacity="0.35"
  stroke="#ffffff"
  stroke-width="2"
  stroke-dasharray="6 4"
/>

```

Colour scheme:

*   right\_cheek → purple fill
    
*   right\_undereye → teal fill
    
*   Other regions → red fallback
    

All masks are semi-transparent with a white dashed border, matching the **“production-quality mask overlay”** requirement.

5\. Caching in the Database (Bonus #2)
--------------------------------------

The spec asks for a cache that avoids recomputing identical requests. This is implemented via the processed\_images table.

### 5.1 Table Schema (simplified)

ProcessedImage fields:

*   id – primary key
    
*   cache\_key – SHA-256 hash of (image, landmarks, segmentation)
    
*   svg\_result – SVG markup as a string
    
*   mask\_contours\_json – JSON representation of contours
    
*   created\_at – timestamp
    

The table is created automatically on application startup.

### 5.2 Cache Workflow

For each /frontal/crop/submit call:

1.  cache\_key = generate\_cache\_key(image, landmarks, segmentation\_map)
    
2.  If CACHE\_ENABLED is true:
    
    *   Attempt to fetch from DB:
        
        *   On **HIT**: return cached result immediately (logs show Cache HIT).
            
        *   On **MISS**: fall through to processing and then cache the result.
            
3.  If CACHE\_ENABLED is false:
    
    *   Skip cache and always recompute.
        

### 5.3 Cache Toggle

*   CACHE\_ENABLED (env var, optional)
    
    *   Default: "1" (cache on)
        
    *   "0" → skip reads and writes to processed\_images
        

6\. Async Jobs & Loadtesting Mode (Bonus #1 + #4)
-------------------------------------------------

### 6.1 Config Flags

Defined in app/services/tasks.py:

*   JOB\_DELAY\_SECONDS – simulated delay before processing jobs
    
*   LOADTEST\_MODE – when true, skip the artificial delay entirely
    

These read from environment variables:

*   JOB\_DELAY\_SECONDS (default: 20)
    
*   LOADTEST\_MODE (default: "0")
    

### 6.2 Behaviour

In run\_crop\_job:

```
delay = 0 if LOADTEST_MODE else JOB_DELAY_SECONDS


if delay > 0:
    time.sleep(delay)  # simulate heavy processing
`
```
**Normal mode (default):**

*   /crop/submit responds immediately with "pending".
    
*   The job becomes "completed" after approximately JOB\_DELAY\_SECONDS plus real processing time.
    

**Loadtest mode (Bonus #4):**

*   LOADTEST\_MODE=1 makes delay = 0.
    
*   Background jobs execute as fast as possible, so load-testing tools measure **real throughput** without artificial sleep.
    

7\. Running the Project
-----------------------

This is the bit you were asking about, these are the **install & run** instructions.

### 7.1 Local (SQLite, no Docker)

**Requirements:**

*   Python 3.11
    
*   virtualenv / venv
    

```bash


git clone <REPO_URL> qoves-task
cd qoves-task

python -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt

# Use a local SQLite DB for caching
export DATABASE_URL="sqlite:///./qoves_cache.db"

# Optional flags
export CACHE_ENABLED=1
export LOADTEST_MODE=0
export JOB_DELAY_SECONDS=20

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000


```
### 7.2 Docker / docker-compose (Postgres + Prometheus)

Ensure Docker is running, then:

```
cd qoves-task
docker compose up --build\
```

This will start:

*   qoves-app on http://localhost:8000
    
*   qoves-db (Postgres) on localhost:5432
    
*   qoves-prometheus on http://localhost:9090
    

The app container is configured in docker-compose.yml with:
```
environment:
  - DATABASE_URL=postgresql+psycopg2://qoves:qoves@db:5432/qoves
  - CACHE_ENABLED=1
  - LOADTEST_MODE=0
  - JOB_DELAY_SECONDS=20
```

To run in **loadtest mode**, override:

```
LOADTEST_MODE=1 JOB_DELAY_SECONDS=20 docker compose up --build
```

(or edit the environment: block).

8\. Configuration Summary
-------------------------

```
| Env var             | Default                      | Description                                           |
| ------------------- | ---------------------------- | ----------------------------------------------------- |
| `DATABASE_URL`      | `sqlite:///./qoves_cache.db` | DB connection string (SQLite local / Postgres Docker) |
| `CACHE_ENABLED`     | `"1"`                        | `"1"` = use DB cache, `"0"` = always recompute        |
| `LOADTEST_MODE`     | `"0"`                        | `"1"` = disable artificial job delay                  |
| `JOB_DELAY_SECONDS` | `"20"`                       | Simulated delay when `LOADTEST_MODE=0`                |

```

9\. Testing
-----------

With the virtual environment active:

```
pytest  `

```

Tests (in tests/) cover:

*   Happy-path /frontal/crop/submit:
    
    *   returns HTTP 200
        
    *   non-empty svg
        
    *   non-empty mask\_contours
        
*   Basic async job flow: /crop/submit → /crop/status/{id}
    

Additional tests can be added for edge cases and error paths.

10\. Mapping to Task Criteria
-----------------------------

### Minimum Criteria

*   docker compose up --build brings up **all services** with no manual edits.
    
*   POST /api/v1/frontal/crop/submit:
    
    *   Accepts the expected payload (image, landmarks, segmentation).
        
    *   Returns svg + mask\_contours in the required structure.
        
*   Clear error mapping:
    
    *   All “no useful face” scenarios → HTTP 422 { "detail": "NoFace" }.
        

### Moderate Criteria

*   Autorotation of the input image using eye landmarks.
    
*   Landmark-driven frontal crop that generalises beyond the provided example.
    
*   Smooth, production-ready mask overlays:
    
    *   segmentation-based polygon extraction
        
    *   morphological smoothing
        
    *   consistent colours and dashed outlines
        
*   Clean, modular FastAPI design:
    
    *   routers separate from services
        
    *   independent overlay core
        
    *   database abstraction
        

### Advanced / Bonus Criteria

*   **Bonus #1 – Async / non-blocking job system**
    
    *   /crop/submit + /crop/status/{id} with simulated delay
        
*   **Bonus #2 – Persistent caching**
    
    *   processed\_images table storing SVG + contours keyed by deterministic hash
        
*   **Bonus #3 – Observability & infra**
    
    *   /metrics endpoint, Prometheus container configured in prometheus.yml
        
*   **Bonus #4 – Loadtesting mode**
    
    *   LOADTEST\_MODE=1 disables artificial delay so the API runs at maximum throughput
        
*   **Logging**
    
    *   Structured logs for:
        
        *   cache hits/misses
            
        *   job lifecycle
            
        *   image processing steps
            

11\. Possible Future Improvements
---------------------------------

If given more time, I would:

1.  Refine region naming to exactly match the numbered regions in the PDF and add more semantic masks (e.g., separate nose bridge vs. tip, split cheek regions).
    
2.  Add golden-file tests that compare generated SVGs against reference outputs.
    
3.  Introduce a proper task queue (Redis + RQ / Celery) instead of in-memory jobs for horizontal scaling.
    
4.  Integrate a face-parsing model directly so segmentation can be computed on the fly from raw images.
    

QOVES Backend Task – Frontal Crop & Overlay API
This repository contains my implementation of the QOVES Backend Task – FastAPI (Task 1, July 2025).
The service:
Accepts a portrait image, 2D facial landmarks, and a segmentation map
Automatically rotates the face to upright and crops it to a consistent frontal view
Generates an SVG overlay with smooth contour masks for key regions (right cheek, right undereye, nose, lips, face outline, etc.)
Caches processed results in a relational database (SQLite / Postgres)
Exposes both synchronous and asynchronous (job-style) APIs
Publishes Prometheus metrics and runs as a docker-compose stack (app + Postgres + Prometheus)

1. Tech Stack
Language: Python 3.11
Framework: FastAPI + Uvicorn
Image processing: OpenCV (cv2), NumPy
Database:
Local dev: SQLite
Docker: Postgres 16

ORM: SQLAlchemy
Metrics: prometheus_client (/metrics endpoint) + Prometheus server
Logging: rich (coloured, structured logs)
Containerisation: Docker + docker-compose
Tests: FastAPI TestClient integration tests

2. High-Level Architecture
Core layout
app/main.py
Creates the FastAPI app
Mounts API router at /api/v1
Adds /health and /metrics endpoints
Initialises the database and creates the cache table if needed

app/api/routes.py
POST /api/v1/frontal/crop/submit – main crop + SVG endpoint
POST /api/v1/crop/submit – async job submission (non-blocking)
GET  /api/v1/crop/status/{job_id} – async job status lookup
POST /api/v1/crop/submit/raw – debug endpoint returning full JSON payload

app/api/models.py
Pydantic models:
CropSubmitRequest
SVGResponse
JobResponse
JobStatusResponse


app/core/config.py
Central configuration (reads env vars like DATABASE_URL, CACHE_ENABLED, etc.)

app/core/database.py
SQLAlchemy engine & session
ProcessedImage model for the cache table (processed_images)

app/services/frontal_cropper.py
Computes a frontal crop box from 68-point landmarks
Uses brows, cheeks, and chin to define a padded rectangle
Supports tunable ratios via FrontalCropConfig
Optionally forces a square crop for consistent aspect ratio
Falls back to the whole image if landmarks are unusable

app/services/image_processor.py
High-level pipeline:
Decode base64 image & segmentation PNG
Compute eye centres from landmarks
Derive rotation angle from the eye line and rotate image + segmentation together
Compute frontal crop box via compute_frontal_face_box
Crop both the image and the segmentation
Call overlay_core.generate_overlay_svg to build SVG + region contours
Return {"svg": svg_str, "mask_contours": [...]}


overlay_core.py
Decodes the rotated + cropped RGB image and grayscale segmentation map
Treats background as label 0
Treats the highest label id as hair and excludes it from face regions
For each remaining label:
Builds a binary mask
Applies morphological closing to seal gaps and smooth edges
Finds external contours, selects the largest, and simplifies it with approxPolyDP
Produces a RegionContour with an ID, semantic name, and polygon points

Generates the final SVG:
Embeds the base image as data:image/png;base64,...
Renders translucent polygons with white dashed borders over the face


app/services/cache_service.py
generate_cache_key(image, landmarks, segmentation) – SHA-256 hash over payload
get_cached_result(cache_key, db)
cache_result(cache_key, result, db)

app/services/tasks.py
In-memory JobStore mapping job IDs → {status, result, error}
run_crop_job(job_id, image_b64, landmarks, segmentation_b64):
Optional simulated delay
Calls process_image
Stores SVG result or error into JobStore


docker-compose.yml
Brings up:
qoves-app (FastAPI)
qoves-db (Postgres)
qoves-prometheus (Prometheus)


prometheus.yml
Targets qoves-app:8000 and scrapes /metrics on a fixed interval

sample_payload.json
Example payload wired to the task’s source image, landmarks, and segmentation map


3. Endpoints
All endpoints are under the /api/v1 prefix.
3.1 POST /api/v1/frontal/crop/submit
Purpose: Main spec endpoint – takes original image + landmarks + segmentation map and returns SVG overlay with mask contours.
Request body
Plain text
ANTLR4
Bash
C
C#
CSS
CoffeeScript
CMake
Dart
Django
Docker
EJS
Erlang
Git
Go
GraphQL
Groovy
HTML
Java
JavaScript
JSON
JSX
Kotlin
LaTeX
Less
Lua
Makefile
Markdown
MATLAB
Markup
Objective-C
Perl
PHP
PowerShell
.properties
Protocol Buffers
Python
R
Ruby
Sass (Sass)
Sass (Scss)
Scheme
SQL
Shell
Swift
SVG
TSX
TypeScript
WebAssembly
YAML
XML

{
  "image": "<base64_encoded_original_image>",
  "landmarks": [
    { "x": 123.4, "y": 234.5 },
    { "x": 130.0, "y": 240.0 }
    // ...
  ],
  "segmentation_map": "<base64_encoded_segmentation_png>"
}



Successful response (SVGResponse)
Plain text
ANTLR4
Bash
C
C#
CSS
CoffeeScript
CMake
Dart
Django
Docker
EJS
Erlang
Git
Go
GraphQL
Groovy
HTML
Java
JavaScript
JSON
JSX
Kotlin
LaTeX
Less
Lua
Makefile
Markdown
MATLAB
Markup
Objective-C
Perl
PHP
PowerShell
.properties
Protocol Buffers
Python
R
Ruby
Sass (Sass)
Sass (Scss)
Scheme
SQL
Shell
Swift
SVG
TSX
TypeScript
WebAssembly
YAML
XML

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



Error responses
No usable face / invalid crop / insufficient landmarks
Plain text
ANTLR4
Bash
C
C#
CSS
CoffeeScript
CMake
Dart
Django
Docker
EJS
Erlang
Git
Go
GraphQL
Groovy
HTML
Java
JavaScript
JSON
JSX
Kotlin
LaTeX
Less
Lua
Makefile
Markdown
MATLAB
Markup
Objective-C
Perl
PHP
PowerShell
.properties
Protocol Buffers
Python
R
Ruby
Sass (Sass)
Sass (Scss)
Scheme
SQL
Shell
Swift
SVG
TSX
TypeScript
WebAssembly
YAML
XML

HTTP 422
{ "detail": "NoFace" }



Other validation problems
Plain text
ANTLR4
Bash
C
C#
CSS
CoffeeScript
CMake
Dart
Django
Docker
EJS
Erlang
Git
Go
GraphQL
Groovy
HTML
Java
JavaScript
JSON
JSX
Kotlin
LaTeX
Less
Lua
Makefile
Markdown
MATLAB
Markup
Objective-C
Perl
PHP
PowerShell
.properties
Protocol Buffers
Python
R
Ruby
Sass (Sass)
Sass (Scss)
Scheme
SQL
Shell
Swift
SVG
TSX
TypeScript
WebAssembly
YAML
XML

HTTP 422
{ "detail": "<error message>" }



Unexpected internal error
Plain text
ANTLR4
Bash
C
C#
CSS
CoffeeScript
CMake
Dart
Django
Docker
EJS
Erlang
Git
Go
GraphQL
Groovy
HTML
Java
JavaScript
JSON
JSX
Kotlin
LaTeX
Less
Lua
Makefile
Markdown
MATLAB
Markup
Objective-C
Perl
PHP
PowerShell
.properties
Protocol Buffers
Python
R
Ruby
Sass (Sass)
Sass (Scss)
Scheme
SQL
Shell
Swift
SVG
TSX
TypeScript
WebAssembly
YAML
XML

HTTP 500
{ "detail": "Internal server error" }



3.2 Async Job-Style API (Bonus #1)
3.2.1 POST /api/v1/crop/submit
Same request body as /frontal/crop/submit.
Returns immediately with a job ID and "pending" status:
Plain text
ANTLR4
Bash
C
C#
CSS
CoffeeScript
CMake
Dart
Django
Docker
EJS
Erlang
Git
Go
GraphQL
Groovy
HTML
Java
JavaScript
JSON
JSX
Kotlin
LaTeX
Less
Lua
Makefile
Markdown
MATLAB
Markup
Objective-C
Perl
PHP
PowerShell
.properties
Protocol Buffers
Python
R
Ruby
Sass (Sass)
Sass (Scss)
Scheme
SQL
Shell
Swift
SVG
TSX
TypeScript
WebAssembly
YAML
XML

{
  "id": "0eb347a3-a186-46dc-b9f6-69742924258c",
  "status": "pending"
}



The heavy work runs in a FastAPI BackgroundTasks worker.
3.2.2 GET /api/v1/crop/status/{job_id}
Returns job status plus SVG when completed:
Plain text
ANTLR4
Bash
C
C#
CSS
CoffeeScript
CMake
Dart
Django
Docker
EJS
Erlang
Git
Go
GraphQL
Groovy
HTML
Java
JavaScript
JSON
JSX
Kotlin
LaTeX
Less
Lua
Makefile
Markdown
MATLAB
Markup
Objective-C
Perl
PHP
PowerShell
.properties
Protocol Buffers
Python
R
Ruby
Sass (Sass)
Sass (Scss)
Scheme
SQL
Shell
Swift
SVG
TSX
TypeScript
WebAssembly
YAML
XML

{
  "id": "0eb347a3-a186-46dc-b9f6-69742924258c",
  "status": "completed",      // "pending" | "completed" | "failed"
  "result": "<svg ...>...</svg>",
  "error": null               // e.g. "NoFace" on failure
}



Unknown job_id:
Plain text
ANTLR4
Bash
C
C#
CSS
CoffeeScript
CMake
Dart
Django
Docker
EJS
Erlang
Git
Go
GraphQL
Groovy
HTML
Java
JavaScript
JSON
JSX
Kotlin
LaTeX
Less
Lua
Makefile
Markdown
MATLAB
Markup
Objective-C
Perl
PHP
PowerShell
.properties
Protocol Buffers
Python
R
Ruby
Sass (Sass)
Sass (Scss)
Scheme
SQL
Shell
Swift
SVG
TSX
TypeScript
WebAssembly
YAML
XML

HTTP 404
{ "detail": "Job not found" }



3.3 POST /api/v1/crop/submit/raw
Debug endpoint that bypasses caching and returns the full result from process_image() – including:
SVG
Contours
Optional metadata like rotation angle and crop box

Useful for development and visual verification.
3.4 Health & Metrics
{ "status": "ok" }
GET /metrics – Prometheus metrics (request counts, latencies, etc.)

4. Image Geometry & Overlay Details
4.1 Rotation
Landmarks are assumed to be 68-point landmarks.
Eye centres (left and right) are computed from their respective landmark groups.
The angle between the eye line and horizontal is calculated.
The original image and the segmentation map are rotated together around the image centre using:
cv2.getRotationMatrix2D
cv2.warpAffine

This normalises head tilt so the downstream crop and contours always operate on an upright face.

4.2 Frontal Crop Box
Implemented in frontal_cropper.py via compute_frontal_face_box:
Uses:
Chin point
Left cheek / right cheek
Left brow / right brow

Calculates a base face rectangle and inflates it with tunable ratios:
forehead_extra – how far above the brows to go
chin_extra – padding below the chin
side_extra – lateral padding around cheeks
make_square – whether to convert to a square box

The box is:
Clamped to image boundaries
Adjusted if the square extends outside the frame

If landmarks are missing / invalid, the function falls back to returning the full image bounds, which upstream code interprets as “no special crop”.
4.3 Segmentation → Clean Contours
In overlay_core.py:
Grayscale segmentation is loaded, with 0 treated as background.
Unique non-zero labels are extracted; the largest label id is treated as hair and ignored.

For each remaining label:
Build a binary mask: seg == label
Apply morphological closing with an elliptical 7x7 kernel to clean small gaps and jagged edges
Find external contours, keep the largest region only
Simplify the contour with approxPolyDP to produce a smooth polygon

Region naming:
First non-hair label → "right_cheek"
Second non-hair label → "right_undereye"
Others → "region_3", "region_4", …

4.4 SVG Styling
Each RegionContour is rendered as:
Plain text
ANTLR4
Bash
C
C#
CSS
CoffeeScript
CMake
Dart
Django
Docker
EJS
Erlang
Git
Go
GraphQL
Groovy
HTML
Java
JavaScript
JSON
JSX
Kotlin
LaTeX
Less
Lua
Makefile
Markdown
MATLAB
Markup
Objective-C
Perl
PHP
PowerShell
.properties
Protocol Buffers
Python
R
Ruby
Sass (Sass)
Sass (Scss)
Scheme
SQL
Shell
Swift
SVG
TSX
TypeScript
WebAssembly
YAML
XML




Colour scheme:
right_cheek → purple fill
right_undereye → teal fill
Other regions → red fallback

All masks are semi-transparent with a white dashed border, matching the “production-quality mask overlay” requirement.
5. Caching in the Database (Bonus #2)
The spec asks for a cache that avoids recomputing identical requests. This is implemented via the processed_images table.
5.1 Table Schema (simplified)
ProcessedImage fields:
id – primary key
cache_key – SHA-256 hash of (image, landmarks, segmentation)
svg_result – SVG markup as a string
mask_contours_json – JSON representation of contours
created_at – timestamp

The table is created automatically on application startup.
5.2 Cache Workflow
For each /frontal/crop/submit call:
cache_key = generate_cache_key(image, landmarks, segmentation_map)
If CACHE_ENABLED is true:
Attempt to fetch from DB:
On HIT: return cached result immediately (logs show Cache HIT).
On MISS: fall through to processing and then cache the result.


If CACHE_ENABLED is false:
Skip cache and always recompute.


5.3 Cache Toggle
CACHE_ENABLED (env var, optional)
Default: "1" (cache on)
"0" → skip reads and writes to processed_images


6. Async Jobs & Loadtesting Mode (Bonus #1 + #4)
6.1 Config Flags
Defined in app/services/tasks.py:
JOB_DELAY_SECONDS – simulated delay before processing jobs
LOADTEST_MODE – when true, skip the artificial delay entirely

These read from environment variables:
JOB_DELAY_SECONDS (default: 20)
LOADTEST_MODE (default: "0")

6.2 Behaviour
In run_crop_job:
Plain text
ANTLR4
Bash
C
C#
CSS
CoffeeScript
CMake
Dart
Django
Docker
EJS
Erlang
Git
Go
GraphQL
Groovy
HTML
Java
JavaScript
JSON
JSX
Kotlin
LaTeX
Less
Lua
Makefile
Markdown
MATLAB
Markup
Objective-C
Perl
PHP
PowerShell
.properties
Protocol Buffers
Python
R
Ruby
Sass (Sass)
Sass (Scss)
Scheme
SQL
Shell
Swift
SVG
TSX
TypeScript
WebAssembly
YAML
XML

delay = 0 if LOADTEST_MODE else JOB_DELAY_SECONDS


if delay > 0:
    time.sleep(delay)  # simulate heavy processing



Normal mode (default):
/crop/submit responds immediately with "pending".
The job becomes "completed" after approximately JOB_DELAY_SECONDS plus real processing time.

Loadtest mode (Bonus #4):
LOADTEST_MODE=1 makes delay = 0.
Background jobs execute as fast as possible, so load-testing tools measure real throughput without artificial sleep.

7. Running the Project
This is the bit you were asking about – these are the install & run instructions.
7.1 Local (SQLite, no Docker)
Requirements:
Python 3.11
virtualenv / venv

Plain text
ANTLR4
Bash
C
C#
CSS
CoffeeScript
CMake
Dart
Django
Docker
EJS
Erlang
Git
Go
GraphQL
Groovy
HTML
Java
JavaScript
JSON
JSX
Kotlin
LaTeX
Less
Lua
Makefile
Markdown
MATLAB
Markup
Objective-C
Perl
PHP
PowerShell
.properties
Protocol Buffers
Python
R
Ruby
Sass (Sass)
Sass (Scss)
Scheme
SQL
Shell
Swift
SVG
TSX
TypeScript
WebAssembly
YAML
XML

git clone <PRIVATE_REPO_URL> qoves-task
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



Then open:
Swagger / OpenAPI: http://localhost:8000/docs
Health check: http://localhost:8000/health
Prometheus metrics: http://localhost:8000/metrics

Use sample_payload.json as the request body to test /frontal/crop/submit.
7.2 Docker / docker-compose (Postgres + Prometheus)
Ensure Docker is running, then:
Plain text
ANTLR4
Bash
C
C#
CSS
CoffeeScript
CMake
Dart
Django
Docker
EJS
Erlang
Git
Go
GraphQL
Groovy
HTML
Java
JavaScript
JSON
JSX
Kotlin
LaTeX
Less
Lua
Makefile
Markdown
MATLAB
Markup
Objective-C
Perl
PHP
PowerShell
.properties
Protocol Buffers
Python
R
Ruby
Sass (Sass)
Sass (Scss)
Scheme
SQL
Shell
Swift
SVG
TSX
TypeScript
WebAssembly
YAML
XML

cd qoves-task
docker compose up --build



This will start:
qoves-app on http://localhost:8000
qoves-db (Postgres) on localhost:5432
qoves-prometheus on http://localhost:9090

The app container is configured in docker-compose.yml with:
Plain text
ANTLR4
Bash
C
C#
CSS
CoffeeScript
CMake
Dart
Django
Docker
EJS
Erlang
Git
Go
GraphQL
Groovy
HTML
Java
JavaScript
JSON
JSX
Kotlin
LaTeX
Less
Lua
Makefile
Markdown
MATLAB
Markup
Objective-C
Perl
PHP
PowerShell
.properties
Protocol Buffers
Python
R
Ruby
Sass (Sass)
Sass (Scss)
Scheme
SQL
Shell
Swift
SVG
TSX
TypeScript
WebAssembly
YAML
XML

environment:
  - DATABASE_URL=postgresql+psycopg2://qoves:qoves@db:5432/qoves
  - CACHE_ENABLED=1
  - LOADTEST_MODE=0
  - JOB_DELAY_SECONDS=20



To run in loadtest mode, override:
Plain text
ANTLR4
Bash
C
C#
CSS
CoffeeScript
CMake
Dart
Django
Docker
EJS
Erlang
Git
Go
GraphQL
Groovy
HTML
Java
JavaScript
JSON
JSX
Kotlin
LaTeX
Less
Lua
Makefile
Markdown
MATLAB
Markup
Objective-C
Perl
PHP
PowerShell
.properties
Protocol Buffers
Python
R
Ruby
Sass (Sass)
Sass (Scss)
Scheme
SQL
Shell
Swift
SVG
TSX
TypeScript
WebAssembly
YAML
XML

LOADTEST_MODE=1 JOB_DELAY_SECONDS=20 docker compose up --build



(or edit the environment: block).
8. Configuration Summary
Env varDefaultDescriptionDATABASE_URLsqlite:///./qoves_cache.dbDB connection string (SQLite local / Postgres in Docker)CACHE_ENABLED"1""1" = use DB cache, "0" = always recomputeLOADTEST_MODE"0""1" = disable artificial job delayJOB_DELAY_SECONDS"20"Simulated delay when LOADTEST_MODE=0
9. Testing
With the virtual environment active:
Plain text
ANTLR4
Bash
C
C#
CSS
CoffeeScript
CMake
Dart
Django
Docker
EJS
Erlang
Git
Go
GraphQL
Groovy
HTML
Java
JavaScript
JSON
JSX
Kotlin
LaTeX
Less
Lua
Makefile
Markdown
MATLAB
Markup
Objective-C
Perl
PHP
PowerShell
.properties
Protocol Buffers
Python
R
Ruby
Sass (Sass)
Sass (Scss)
Scheme
SQL
Shell
Swift
SVG
TSX
TypeScript
WebAssembly
YAML
XML

pytest



Tests (in tests/) cover:
Happy-path /frontal/crop/submit:
returns HTTP 200
non-empty svg
non-empty mask_contours

Basic async job flow: /crop/submit → /crop/status/{id}

Additional tests can be added for edge cases and error paths.
10. Mapping to Task Criteria
Minimum Criteria
docker compose up --build brings up all services with no manual edits.
POST /api/v1/frontal/crop/submit:
Accepts the expected payload (image, landmarks, segmentation).
Returns svg + mask_contours in the required structure.

Clear error mapping:
All “no useful face” scenarios → HTTP 422 { "detail": "NoFace" }.


Moderate Criteria
Autorotation of the input image using eye landmarks.
Landmark-driven frontal crop that generalises beyond the provided example.
Smooth, production-ready mask overlays:
segmentation-based polygon extraction
morphological smoothing
consistent colours and dashed outlines

Clean, modular FastAPI design:
routers separate from services
independent overlay core
database abstraction


Advanced / Bonus Criteria
Bonus #1 – Async / non-blocking job system
/crop/submit + /crop/status/{id} with simulated delay

Bonus #2 – Persistent caching
processed_images table storing SVG + contours keyed by deterministic hash

Bonus #3 – Observability & infra
/metrics endpoint, Prometheus container configured in prometheus.yml

Bonus #4 – Loadtesting mode
LOADTEST_MODE=1 disables artificial delay so the API runs at maximum throughput

Logging
Structured logs for:
cache hits/misses
job lifecycle
image processing steps



11. Possible Future Improvements
If given more time, I would:
Refine region naming to exactly match the numbered regions in the PDF and add more semantic masks (e.g. separate nose bridge vs. tip, split cheek regions).
Add golden-file tests that compare generated SVGs against reference outputs.
Introduce a proper task queue (Redis + RQ / Celery) instead of in-memory jobs for horizontal scaling.
Integrate a face-parsing model directly so segmentation can be computed on the fly from raw images.

If you paste this into README.md, you’re fully covered on install + run, plus all the criteria / bonus points are explicitly mapped.



Extended thinkingChatGPT can make mistakes. Check important info. See Cookie Preferences.

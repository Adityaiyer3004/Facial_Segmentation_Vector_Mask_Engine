from __future__ import annotations

import os
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from app.api.models import (
    CropSubmitRequest,
    JobResponse,
    JobStatusResponse,
    SVGResponse,
)
from app.core.database import get_db
from app.services.image_processor import process_image  # ⬅️ high-level pipeline
from app.services.cache_service import (
    generate_cache_key,
    get_cached_result,
    cache_result,
)
from app.services.tasks import job_store, run_crop_job
from app.utils.logging import console, logger


router = APIRouter()

# Toggle caching via env var. Default = ON.
CACHE_ENABLED = os.getenv("CACHE_ENABLED", "1") == "1"


@router.post(
    "/frontal/crop/submit",
    response_model=SVGResponse,
    status_code=200,
)
async def frontal_crop_submit(
    payload: CropSubmitRequest,
    db: Session = Depends(get_db),
):
    """
    Main QOVES endpoint:
    - Accepts base64 image + landmarks + segmentation_map
    - Uses OpenCV pipeline (rotation + crop + seg-based overlay)
    - Returns SVG + mask contours in JSON
    """

    # Cache key from image + landmarks + segmentation
    cache_key = generate_cache_key(
        payload.image,
        [p.model_dump() for p in payload.landmarks],
        payload.segmentation_map or "",
    )

    # -------- CACHE LOOKUP (optional) --------
    if CACHE_ENABLED:
        cached = get_cached_result(cache_key, db)
        if cached:
            console.log("[green]Serving SVG from cache[/green]")
            return cached  # {"svg": ..., "mask_contours": [...]}

    try:
        # Always compute using the latest pipeline
        result = process_image(
            image_b64=payload.image,
            landmarks=[p.model_dump() for p in payload.landmarks],
            segmentation_b64=payload.segmentation_map,
        )

        # Store in cache if enabled
        if CACHE_ENABLED:
            cache_result(cache_key, result, db)

        return result

    except ValueError as e:
        msg = str(e)

        # Map all "no useful face" flavours to 422 NoFace (spec requirement)
        if (
            "NoFace" in msg
            or "Insufficient landmarks" in msg
            or "invalid crop bounds" in msg
        ):
            raise HTTPException(status_code=422, detail="NoFace")

        # Any other validation error -> 422 with detail
        raise HTTPException(status_code=422, detail=msg)

    except Exception:
        logger.exception("Unexpected error in /frontal/crop/submit")
        raise HTTPException(status_code=500, detail="Internal server error")


# ---------- BONUS: async job-style endpoints ----------

@router.post("/crop/submit", response_model=JobResponse)
async def crop_submit_job_style(
    payload: CropSubmitRequest,
    background_tasks: BackgroundTasks,
):
    """
    Job-style endpoint (non-blocking, for bonus points):
      - Immediately returns {id, status:"pending"}
      - Heavy work runs in a background task
      - Result (SVG) is available via /crop/status/{id}
    """
    job_id = job_store.create_job()

    background_tasks.add_task(
        run_crop_job,
        job_id,
        payload.image,
        [p.model_dump() for p in payload.landmarks],
        payload.segmentation_map,
    )

    return JobResponse(id=job_id, status="pending")


@router.get("/crop/status/{job_id}", response_model=JobStatusResponse)
async def crop_status(job_id: str):
    """
    Check status of an async crop job.
    - If completed, `result` contains the SVG string.
    - If pending, result is null.
    - If failed, `error` is populated.
    """
    data = job_store.get(job_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobStatusResponse(
        id=job_id,
        status=data["status"],
        result=data["result"],
        error=data["error"],
    )


# ---------- Debug / raw output endpoint ----------

@router.post("/crop/submit/raw")
async def crop_submit_raw(payload: CropSubmitRequest):
    """
    Debug/testing endpoint:
    - returns full JSON payload from process_image()
      (svg + mask_contours)
    """
    try:
        out = process_image(
            image_b64=payload.image,
            landmarks=[p.model_dump() for p in payload.landmarks],
            segmentation_b64=payload.segmentation_map,
        )
        return out

    except ValueError as e:
        msg = str(e)
        # Keep behaviour consistent with /frontal/crop/submit
        if (
            "NoFace" in msg
            or "Insufficient landmarks" in msg
            or "invalid crop bounds" in msg
        ):
            raise HTTPException(status_code=422, detail="NoFace")
        raise HTTPException(status_code=422, detail=msg)

    except Exception:
        logger.exception("Unexpected error in /crop/submit/raw")
        raise HTTPException(status_code=500, detail="Internal server error")

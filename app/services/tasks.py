# app/services/tasks.py
from __future__ import annotations

import os
import time
import uuid
from typing import Dict, Optional, Any, List

from app.services.image_processor import process_image
from app.utils.logging import logger

# --- Config flags for delay / loadtest mode ---

# Spec suggests ~20s simulated delay
DEFAULT_DELAY_SECONDS = 20

# Allow override via env: JOB_DELAY_SECONDS=10, etc.
JOB_DELAY_SECONDS = int(os.getenv("JOB_DELAY_SECONDS", str(DEFAULT_DELAY_SECONDS)))

# LOADTEST_MODE=1 -> skip artificial delay entirely
LOADTEST_MODE = os.getenv("LOADTEST_MODE", "0") == "1"


# Very simple in-memory job store for the take-home.
# In production you'd use Redis / Celery / RQ etc.
class JobStore:
    def __init__(self):
        # id -> dict(status, result, error)
        self._jobs: Dict[str, Dict[str, Optional[str]]] = {}

    def create_job(self) -> str:
        job_id = str(uuid.uuid4())
        self._jobs[job_id] = {
            "status": "pending",
            "result": None,
            "error": None,
        }
        return job_id

    def set_result(self, job_id: str, result: str) -> None:
        if job_id in self._jobs:
            self._jobs[job_id]["status"] = "completed"
            self._jobs[job_id]["result"] = result
            self._jobs[job_id]["error"] = None

    def set_error(self, job_id: str, error: str) -> None:
        if job_id in self._jobs:
            self._jobs[job_id]["status"] = "failed"
            self._jobs[job_id]["result"] = None
            self._jobs[job_id]["error"] = error

    def get(self, job_id: str) -> Optional[Dict[str, Optional[str]]]:
        return self._jobs.get(job_id)


job_store = JobStore()


def run_crop_job(
    job_id: str,
    image_b64: str,
    landmarks: List[Dict[str, Any]],
    segmentation_b64: Optional[str],
) -> None:
    """
    Background task that actually runs the heavy processing.

    - Normal mode: simulate a slow job with configurable sleep
      (default 20s, as per spec).
    - LOADTEST_MODE: skip artificial delay so performance is bound only
      by real processing.
    """
    logger.info(
        f"Starting background job {job_id} "
        f"(LOADTEST_MODE={LOADTEST_MODE}, JOB_DELAY_SECONDS={JOB_DELAY_SECONDS})"
    )

    try:
        # --- Artificial delay (spec / bonus #1) ---
        delay = 0 if LOADTEST_MODE else JOB_DELAY_SECONDS

        if delay > 0:
            logger.info(f"Simulating slow job: sleeping {delay} seconds")
            time.sleep(delay)
        else:
            logger.info("LOADTEST_MODE enabled – skipping artificial delay")

        # --- Real work ---
        result = process_image(
            image_b64=image_b64,
            landmarks=landmarks,
            segmentation_b64=segmentation_b64,
        )

        # Only store SVG string for the job endpoint, as per spec.
        job_store.set_result(job_id, result["svg"])
        logger.info(f"Job {job_id} completed")

    except ValueError as e:
        msg = str(e)
        logger.warning(f"Job {job_id} failed with ValueError: {msg}")

        # Mirror /frontal/crop/submit behaviour
        if (
            "NoFace" in msg
            or "invalid crop bounds" in msg
            or "insufficient landmarks" in msg.lower()
        ):
            job_store.set_error(job_id, "NoFace")
        else:
            job_store.set_error(job_id, msg)

    except Exception:
        logger.exception(f"Job {job_id} failed with unexpected error")
        job_store.set_error(job_id, "Internal server error")

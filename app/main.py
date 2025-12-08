# app/main.py
from __future__ import annotations

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.routes import router as api_router
from app.core.database import init_db
from app.utils.logging import logger

app = FastAPI(title="QOVES Facial Segmentation Service")

# Create an instrumentator instance (so we can tweak options if needed)
instrumentator = Instrumentator(
    should_group_status_codes=True,
    should_ignore_untemplated=True,
)

# IMPORTANT: instrument + expose BEFORE startup so middleware is added
instrumentator.instrument(app).expose(
    app,
    endpoint="/metrics",
    include_in_schema=False,
)
logger.info("Prometheus metrics exposed at /metrics")


@app.on_event("startup")
def on_startup():
    """
    Initialise DB and any other startup hooks.
    Do NOT add middleware / instrumentator here.
    """
    init_db()
    logger.info("Database initialised")


# Mount all API routes under /api/v1
app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok"}

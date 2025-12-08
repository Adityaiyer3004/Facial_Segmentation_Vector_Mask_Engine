from __future__ import annotations

from pydantic import BaseModel, Field
from typing import List, Optional


class LandmarkPoint(BaseModel):
    x: float
    y: float


class CropSubmitRequest(BaseModel):
    image: str = Field(..., description="Base64-encoded face image PNG/JPEG")
    landmarks: List[LandmarkPoint] = Field(
        default_factory=list,
        description="Optional facial landmarks (currently unused in v1).",
    )
    segmentation_map: Optional[str] = Field(
        default=None,
        description="Optional base64-encoded segmentation map image.",
    )


# --- New: mask contour + SVG response ---

class MaskContour(BaseModel):
    name: str = Field(..., description="Region name, e.g. 'right_cheek'")
    points: List[LandmarkPoint] = Field(
        ..., description="Polygon points in image pixel coordinates"
    )


class SVGResponse(BaseModel):
    svg: str = Field(..., description="SVG with highlighted facial regions")
    mask_contours: List[MaskContour] = Field(
        default_factory=list,
        description="List of region contours used to generate the SVG",
    )


# --- Existing job-style models ---

class JobResponse(BaseModel):
    id: str
    status: str  # "pending", "processing", "completed", "failed"


class JobStatusResponse(BaseModel):
    id: str
    status: str
    result: Optional[str] = None  # SVG string
    error: Optional[str] = None

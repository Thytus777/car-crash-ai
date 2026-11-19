import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.problems import problem_responses
from app.db.repository import save_estimate
from app.models.estimate import AssessmentReport, VehicleConfirmNeeded
from app.services.assessment import AssessmentRequest, assess
from app.services.image_proc import UPLOAD_ID_PATTERN

logger = logging.getLogger(__name__)

router = APIRouter()


class AnalyzeRequest(BaseModel):
    upload_id: str = Field(
        ...,
        pattern=UPLOAD_ID_PATTERN,
        description="Upload ID from /upload endpoint",
    )
    make: str | None = Field(default=None, description="Override: vehicle make")
    model: str | None = Field(default=None, description="Override: vehicle model")
    year: int | None = Field(default=None, description="Override: vehicle year")
    vin: str | None = Field(
        default=None, description="Optional VIN for precise identification"
    )
    use_consensus: bool = Field(
        default=False,
        description=(
            "Run both AI providers and merge results for higher confidence "
            "(slower, costs more)"
        ),
    )


@router.post(
    "/analyze",
    response_model=AssessmentReport | VehicleConfirmNeeded,
    summary="Run full damage analysis on uploaded images",
    responses=problem_responses(404, 422, 429, 500, 502, 503, 504),
    description=(
        "Screens the images (422 not-a-vehicle / unusable-images), identifies "
        "the vehicle, detects damage per zone, prices each part and reviews the "
        "result. Degraded stages are listed in `issues` with `status: partial`."
    ),
)
async def analyze_damage(
    request: AnalyzeRequest,
) -> AssessmentReport | VehicleConfirmNeeded:
    result = await assess(AssessmentRequest(**request.model_dump()))

    if isinstance(result, AssessmentReport):
        # Best-effort: a DB failure leaves estimate_id unset (see #1).
        result.estimate_id = await save_estimate(result, request.upload_id, request.vin)
    return result

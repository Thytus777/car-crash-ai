import asyncio
import logging
from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.problems import problem_responses
from app.core.config import settings
from app.core.errors import (
    AppError,
    NotAVehicleError,
    NotFoundError,
    UnusableImagesError,
)
from app.core.llm import record_llm_calls
from app.db.repository import save_estimate
from app.models.damage import DamageItem
from app.models.estimate import (
    AssessmentIssue,
    AssessmentMeta,
    AssessmentReport,
    CostEstimate,
    ReportTotals,
)
from app.models.vehicle import Vehicle
from app.services.cost_estimate import estimate_cost
from app.services.damage_detect import detect_damage
from app.services.image_proc import UPLOAD_ID_PATTERN
from app.services.image_triage import triage_images
from app.services.sanity_check import run_sanity_check
from app.services.vehicle_id import identify_vehicle, needs_user_input

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


class VehicleConfirmNeeded(BaseModel):
    status: str = "vehicle_confirmation_needed"
    vehicle_guess: Vehicle
    message: str
    meta: AssessmentMeta | None = None


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
    with record_llm_calls() as calls:
        result = await _run_pipeline(request)
    result.meta = AssessmentMeta.from_calls(settings.prompt_version, calls)

    if isinstance(result, AssessmentReport):
        # Best-effort: a DB failure leaves estimate_id unset (see #1).
        result.estimate_id = await save_estimate(result, request.upload_id, request.vin)
    return result


async def _triage(upload_id: str) -> AssessmentIssue | None:
    """Reject uploads that can't be assessed; flag (not fail) if triage is down."""
    try:
        triage = await triage_images(upload_id)
    except (NotAVehicleError, UnusableImagesError, NotFoundError):
        raise
    except AppError as exc:
        logger.warning("Image triage unavailable: %s", exc.detail)
        return AssessmentIssue(
            stage="image_triage",
            detail="The images could not be pre-screened; the assessment ran "
            "without confirming they show a usable vehicle.",
        )
    if not triage.shows_vehicle:
        raise NotAVehicleError(triage.reason)
    if not triage.usable:
        raise UnusableImagesError(triage.reason)
    return None


async def _run_pipeline(
    request: AnalyzeRequest,
) -> AssessmentReport | VehicleConfirmNeeded:
    triage_issue = await _triage(request.upload_id)

    # --- Vehicle identification ---
    if request.make and request.model and request.year:
        vehicle = Vehicle(
            make=request.make,
            model=request.model,
            year=request.year,
            confidence=1.0,
        )
    elif request.vin:
        from app.services.vin_decoder import VINDecodeError, decode_vin

        try:
            vehicle = await decode_vin(request.vin)
        except VINDecodeError:
            # VIN failed — fall through to vision ID
            vehicle = await identify_vehicle(request.upload_id)
    else:
        vehicle = await identify_vehicle(request.upload_id)

        if needs_user_input(vehicle):
            return VehicleConfirmNeeded(
                vehicle_guess=vehicle,
                message=(
                    f"Low confidence ({vehicle.confidence:.0%}) identifying vehicle as "
                    f"{vehicle.year} {vehicle.make} {vehicle.model}. "
                    "Please confirm or provide correct make, model, and year."
                ),
            )

    # --- Damage detection (zone-based, optionally with consensus) ---
    damage_assessment = await detect_damage(
        request.upload_id,
        use_consensus=request.use_consensus,
    )

    issues = [triage_issue] if triage_issue else []
    issues += [
        AssessmentIssue(
            stage="damage_detection",
            scope=zone,
            detail=f"The {zone} zone could not be assessed; its components "
            "are missing from this report.",
        )
        for zone in damage_assessment.failed_zones
    ]

    # --- Cost estimation ---
    limit = asyncio.Semaphore(settings.pricing_concurrency)

    async def price(item: DamageItem) -> CostEstimate:
        async with limit:
            return await estimate_cost(vehicle, item)

    cost_estimates = list(
        await asyncio.gather(*(price(d) for d in damage_assessment.damages))
    )

    unpriced = [c.component for c in cost_estimates if c.part_cost_avg is None]
    issues.extend(
        AssessmentIssue(
            stage="pricing",
            scope=component,
            detail=f"No part price could be found or estimated for {component}; "
            "it is excluded from parts_total.",
        )
        for component in unpriced
    )

    parts_total = sum(
        (c.part_cost_avg for c in cost_estimates if c.part_cost_avg is not None),
        Decimal("0.00"),
    ).quantize(Decimal("0.01"))
    labor_total = sum((c.labor_cost for c in cost_estimates), Decimal("0.00")).quantize(
        Decimal("0.01")
    )
    grand_total = (parts_total + labor_total).quantize(Decimal("0.01"))

    report = AssessmentReport(
        vehicle=vehicle,
        damage_assessment=damage_assessment,
        cost_estimates=cost_estimates,
        totals=ReportTotals(
            parts_total=parts_total,
            labor_total=labor_total,
            grand_total=grand_total,
            unpriced_components=unpriced,
        ),
    )

    # --- Sanity check (second-pass LLM review) ---
    warnings = await run_sanity_check(report)
    if warnings is None:
        issues.append(
            AssessmentIssue(
                stage="sanity_check",
                detail="The consistency review could not run; treat this "
                "estimate as unreviewed.",
            )
        )
    report.assessment_warnings = warnings or []
    report.issues = issues
    report.status = "partial" if issues else "complete"

    return report

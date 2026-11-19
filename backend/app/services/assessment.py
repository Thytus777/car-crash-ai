"""The assessment pipeline behind POST /api/v1/analyze.

Kept out of the HTTP layer so the API and the eval harness run exactly the
same code: triage -> vehicle ID -> damage detection -> pricing -> review.
"""

import asyncio
import logging
from dataclasses import dataclass

from app.core.config import settings
from app.core.errors import (
    AppError,
    NotAVehicleError,
    NotFoundError,
    UnusableImagesError,
)
from app.core.llm import record_llm_calls
from app.models.damage import DamageItem
from app.models.estimate import (
    AssessmentIssue,
    AssessmentMeta,
    AssessmentReport,
    CostEstimate,
    VehicleConfirmNeeded,
)
from app.models.vehicle import Vehicle
from app.services.cost_estimate import compute_totals, estimate_cost
from app.services.damage_detect import detect_damage
from app.services.image_triage import triage_images
from app.services.sanity_check import run_sanity_check
from app.services.vehicle_id import identify_vehicle, needs_user_input

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AssessmentRequest:
    upload_id: str
    make: str | None = None
    model: str | None = None
    year: int | None = None
    vin: str | None = None
    use_consensus: bool = False


async def assess(request: AssessmentRequest) -> AssessmentReport | VehicleConfirmNeeded:
    """Run the full pipeline and attach meta (prompt version, models, tokens).

    Raises typed AppErrors (not-a-vehicle, unusable-images, upstream ...).
    """
    with record_llm_calls() as calls:
        result = await _run_pipeline(request)
    result.meta = AssessmentMeta.from_calls(settings.prompt_version, calls)
    return result


def _confirm_message(vehicle: Vehicle) -> str:
    guess = f"{vehicle.year or 'unknown-year'} {vehicle.make} {vehicle.model}"
    if vehicle.year == 0:
        return (
            f"Couldn't determine the model year (best guess: {guess}). "
            "Please provide make, model and year."
        )
    return (
        f"Low confidence ({vehicle.confidence:.0%}) identifying vehicle as {guess}. "
        "Please confirm or provide correct make, model, and year."
    )


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
    request: AssessmentRequest,
) -> AssessmentReport | VehicleConfirmNeeded:
    triage_issue = await _triage(request.upload_id)

    # --- Vehicle identification ---
    from_vision = False
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
            from_vision = True
    else:
        vehicle = await identify_vehicle(request.upload_id)
        from_vision = True

    if from_vision and needs_user_input(vehicle):
        return VehicleConfirmNeeded(
            vehicle_guess=vehicle, message=_confirm_message(vehicle)
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

    report = AssessmentReport(
        vehicle=vehicle,
        damage_assessment=damage_assessment,
        cost_estimates=cost_estimates,
        totals=compute_totals(cost_estimates),
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
    report.assessment_warnings = damage_assessment.consensus_flags + (warnings or [])
    report.issues = issues
    report.status = "partial" if issues else "complete"

    return report

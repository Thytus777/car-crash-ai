import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import LLMRateLimitError
from app.db.models import EstimateRecord
from app.db.session import get_db

logger = logging.getLogger(__name__)
from app.models.damage import DamageAssessment
from app.models.estimate import AssessmentReport, CostEstimate, ReportTotals
from app.models.vehicle import Vehicle
from app.services.cost_estimate import estimate_cost
from app.services.damage_detect import detect_damage
from app.services.sanity_check import run_sanity_check
from app.services.vehicle_id import identify_vehicle, needs_user_input

router = APIRouter()


class AnalyzeRequest(BaseModel):
    upload_id: str = Field(..., description="Upload ID from /upload endpoint")
    make: str | None = Field(default=None, description="Override: vehicle make")
    model: str | None = Field(default=None, description="Override: vehicle model")
    year: int | None = Field(default=None, description="Override: vehicle year")
    vin: str | None = Field(default=None, description="Optional VIN for precise identification")
    use_consensus: bool = Field(
        default=False,
        description="Run both AI providers and merge results for higher confidence (slower, costs more)",
    )


class VehicleConfirmNeeded(BaseModel):
    status: str = "vehicle_confirmation_needed"
    vehicle_guess: Vehicle
    message: str


@router.post(
    "/analyze",
    response_model=AssessmentReport | VehicleConfirmNeeded,
    summary="Run full damage analysis on uploaded images",
)
async def analyze_damage(
    request: AnalyzeRequest,
    db: AsyncSession = Depends(get_db),
) -> AssessmentReport | VehicleConfirmNeeded:
    # --- Vehicle identification ---
    if request.make and request.model and request.year:
        vehicle = Vehicle(
            make=request.make,
            model=request.model,
            year=request.year,
            confidence=1.0,
        )
    elif request.vin:
        from app.services.vin_decoder import decode_vin, VINDecodeError
        try:
            vehicle = await decode_vin(request.vin)
        except VINDecodeError:
            # VIN failed — fall through to vision ID
            vehicle = None  # type: ignore[assignment]

        if vehicle is None:
            try:
                vehicle = await identify_vehicle(request.upload_id)
            except LLMRateLimitError as exc:
                raise HTTPException(status_code=429, detail=str(exc))
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"Vehicle identification failed: {exc}")
    else:
        try:
            vehicle = await identify_vehicle(request.upload_id)
        except LLMRateLimitError as exc:
            raise HTTPException(status_code=429, detail=str(exc))
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Vehicle identification failed: {exc}",
            )

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
    try:
        damage_assessment = await detect_damage(
            request.upload_id,
            use_consensus=request.use_consensus,
        )
    except LLMRateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Damage detection failed: {exc}",
        )

    # --- Cost estimation ---
    cost_estimates: list[CostEstimate] = []
    for damage_item in damage_assessment.damages:
        cost = await estimate_cost(vehicle, damage_item)
        cost_estimates.append(cost)

    parts_total = sum(
        (c.part_cost_avg for c in cost_estimates), Decimal("0.00")
    ).quantize(Decimal("0.01"))
    labor_total = sum(
        (c.labor_cost for c in cost_estimates), Decimal("0.00")
    ).quantize(Decimal("0.01"))
    grand_total = (parts_total + labor_total).quantize(Decimal("0.01"))

    report = AssessmentReport(
        vehicle=vehicle,
        damage_assessment=damage_assessment,
        cost_estimates=cost_estimates,
        totals=ReportTotals(
            parts_total=parts_total,
            labor_total=labor_total,
            grand_total=grand_total,
        ),
    )

    # --- Sanity check (second-pass LLM review) ---
    report.assessment_warnings = await run_sanity_check(report)

    # --- Persist to database ---
    try:
        record = EstimateRecord(
            upload_id=request.upload_id,
            vehicle_make=vehicle.make,
            vehicle_model=vehicle.model,
            vehicle_year=vehicle.year,
            vehicle_vin=request.vin,
            vehicle_confidence=vehicle.confidence,
            parts_total=float(parts_total),
            labor_total=float(labor_total),
            grand_total=float(grand_total),
            report_json=report.model_dump_json(),
        )
        db.add(record)
        await db.flush()
        logger.info("Saved estimate id=%d for upload=%s", record.id, request.upload_id)
    except Exception:
        logger.exception("Failed to persist estimate — returning result anyway")

    return report

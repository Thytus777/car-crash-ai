from decimal import Decimal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.models.damage import DamageAssessment
from app.models.estimate import AssessmentReport, CostEstimate, ReportTotals
from app.models.vehicle import Vehicle
from app.services.cost_estimate import estimate_cost
from app.services.damage_detect import detect_damage
from app.services.vehicle_id import identify_vehicle, needs_user_input

router = APIRouter()


class AnalyzeRequest(BaseModel):
    upload_id: str = Field(..., description="Upload ID from /upload endpoint")
    make: str | None = Field(default=None, description="Override: vehicle make")
    model: str | None = Field(default=None, description="Override: vehicle model")
    year: int | None = Field(default=None, description="Override: vehicle year")


class VehicleConfirmNeeded(BaseModel):
    status: str = "vehicle_confirmation_needed"
    vehicle_guess: Vehicle
    message: str


@router.post(
    "/analyze",
    response_model=AssessmentReport | VehicleConfirmNeeded,
    summary="Run full damage analysis on uploaded images",
)
async def analyze_damage(request: AnalyzeRequest) -> AssessmentReport | VehicleConfirmNeeded:
    if request.make and request.model and request.year:
        vehicle = Vehicle(
            make=request.make,
            model=request.model,
            year=request.year,
            confidence=1.0,
        )
    else:
        try:
            vehicle = await identify_vehicle(request.upload_id)
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

    try:
        damage_assessment = await detect_damage(request.upload_id)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Damage detection failed: {exc}",
        )

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

    return AssessmentReport(
        vehicle=vehicle,
        damage_assessment=damage_assessment,
        cost_estimates=cost_estimates,
        totals=ReportTotals(
            parts_total=parts_total,
            labor_total=labor_total,
            grand_total=grand_total,
        ),
    )

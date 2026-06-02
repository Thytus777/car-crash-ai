"""Estimate history endpoints — retrieve saved assessments."""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.models import EstimateRecord
from app.models.estimate import AssessmentReport

router = APIRouter()


@router.get(
    "/estimates/{estimate_id}",
    response_model=AssessmentReport,
    summary="Retrieve a saved assessment by ID",
)
async def get_estimate(
    estimate_id: int,
    db: AsyncSession = Depends(get_db),
) -> AssessmentReport:
    result = await db.execute(
        select(EstimateRecord).where(EstimateRecord.id == estimate_id)
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail=f"Estimate {estimate_id} not found")

    return AssessmentReport.model_validate(json.loads(record.report_json))


@router.get(
    "/estimates",
    summary="List recent saved assessments (last 50)",
)
async def list_estimates(
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    result = await db.execute(
        select(
            EstimateRecord.id,
            EstimateRecord.upload_id,
            EstimateRecord.created_at,
            EstimateRecord.vehicle_make,
            EstimateRecord.vehicle_model,
            EstimateRecord.vehicle_year,
            EstimateRecord.grand_total,
        )
        .order_by(EstimateRecord.created_at.desc())
        .limit(50)
    )
    rows = result.fetchall()
    return [
        {
            "id": r.id,
            "upload_id": r.upload_id,
            "created_at": r.created_at.isoformat(),
            "vehicle": f"{r.vehicle_year} {r.vehicle_make} {r.vehicle_model}",
            "grand_total": r.grand_total,
        }
        for r in rows
    ]

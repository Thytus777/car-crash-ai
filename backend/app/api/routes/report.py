"""PDF report endpoint — generate a printable report from a saved estimate."""

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EstimateRecord
from app.db.session import get_db
from app.models.estimate import AssessmentReport
from app.services.report_pdf import generate_pdf

router = APIRouter()


@router.get(
    "/report/{estimate_id}",
    summary="Download a PDF report for a saved estimate",
    response_class=Response,
)
async def download_report(
    estimate_id: int,
    db: AsyncSession = Depends(get_db),
) -> Response:
    result = await db.execute(
        select(EstimateRecord).where(EstimateRecord.id == estimate_id)
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail=f"Estimate {estimate_id} not found")

    report = AssessmentReport.model_validate(json.loads(record.report_json))
    pdf_bytes = generate_pdf(
        report,
        upload_id=record.upload_id,
        estimate_id=estimate_id,
    )

    # WeasyPrint returns PDF; fallback returns HTML
    is_pdf = pdf_bytes[:4] == b"%PDF"
    media_type = "application/pdf" if is_pdf else "text/html"
    filename = f"damage_report_{estimate_id}.{'pdf' if is_pdf else 'html'}"

    return Response(
        content=pdf_bytes,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

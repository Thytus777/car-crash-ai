"""Persistence for assessment results.

Saving is best-effort: the report has already been produced, so a database
problem is logged and reported as a missing ``estimate_id`` rather than
failing the request. Each save runs in its own session and transaction so a
failure can't leave a request-scoped session in a broken state.
"""

import logging

from sqlalchemy.exc import SQLAlchemyError

import app.db.session as db_session
from app.db.models import EstimateRecord, UploadSession
from app.models.estimate import AssessmentReport

logger = logging.getLogger(__name__)


async def save_estimate(
    report: AssessmentReport, upload_id: str, vin: str | None
) -> int | None:
    """Persist a report and return its estimate ID, or None if saving failed."""
    try:
        async with db_session.AsyncSessionLocal() as session, session.begin():
            # estimates.upload_id references upload_sessions.id; /upload doesn't
            # write to the database, so create the parent row on first save.
            if await session.get(UploadSession, upload_id) is None:
                session.add(UploadSession(id=upload_id))

            record = EstimateRecord(
                upload_id=upload_id,
                vehicle_make=report.vehicle.make,
                vehicle_model=report.vehicle.model,
                vehicle_year=report.vehicle.year,
                vehicle_vin=vin,
                vehicle_confidence=report.vehicle.confidence,
                parts_total=report.totals.parts_total,
                labor_total=report.totals.labor_total,
                grand_total=report.totals.grand_total,
                report_json=report.model_dump_json(),
            )
            session.add(record)
            await session.flush()
            estimate_id = record.id
    except (SQLAlchemyError, OSError):
        logger.exception("Failed to persist estimate for upload=%s", upload_id)
        return None

    logger.info("Saved estimate id=%d for upload=%s", estimate_id, upload_id)
    return estimate_id

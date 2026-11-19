"""Second-pass sanity check — asks the LLM to review the full assessment for coherence.

Catches hallucinations like a $15,000 estimate on a cosmetic scratch, or
structural damage on a vehicle that visually has none.
"""

import logging

from app.core.errors import AppError
from app.core.llm import generate
from app.core.tracing import traced
from app.models.estimate import AssessmentReport
from app.models.llm_outputs import SanityReview
from app.prompts import render

logger = logging.getLogger(__name__)


@traced("stage.sanity_check")
async def run_sanity_check(report: AssessmentReport) -> list[str] | None:
    """Run a second-pass LLM review of the full report.

    Returns warning strings (empty if everything looks fine), or None if the
    review itself failed, so callers can tell "no concerns" from "not checked".
    """
    if not report.damage_assessment.damages:
        return []

    damage_summary = "\n".join(
        f"  - {d.component}: {d.damage_type}, severity {d.severity:.2f}, "
        f"recommendation={d.recommendation}"
        for d in report.damage_assessment.damages
    )

    prompt = render(
        "sanity_check",
        year=report.vehicle.year,
        make=report.vehicle.make,
        model=report.vehicle.model,
        grand_total=report.totals.grand_total,
        damage_summary=damage_summary,
    )

    try:
        result = await generate(
            SanityReview,
            prompt,
            task="sanity_check",
            max_output_tokens=400,
            temperature=0.1,
        )
    except AppError as exc:
        logger.warning("Sanity check failed: %s", exc.detail)
        return None

    review = result.output
    warnings = [w for w in review.warnings if w]
    if not review.looks_reasonable and not warnings:
        warnings = [
            "AI flagged this assessment as potentially inconsistent — "
            "manual review recommended."
        ]
    logger.info(
        "Sanity check result: reasonable=%s, warnings=%d",
        review.looks_reasonable,
        len(warnings),
    )
    return warnings

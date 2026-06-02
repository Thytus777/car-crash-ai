"""Second-pass sanity check — asks the LLM to review the full assessment for coherence.

Catches hallucinations like a $15,000 estimate on a cosmetic scratch, or
structural damage on a vehicle that visually has none.
"""

import json
import logging

from app.core.llm import text_completion
from app.models.damage import DamageAssessment
from app.models.estimate import AssessmentReport
from app.models.vehicle import Vehicle

logger = logging.getLogger(__name__)

_SANITY_PROMPT = """\
You are a senior auto damage appraiser reviewing an AI-generated damage assessment.
Check this report for any inconsistencies or red flags.

Vehicle: {year} {make} {model}
Total estimated repair cost: ${grand_total}

Damage found:
{damage_summary}

Review this assessment and identify any of the following issues:
1. Cost seems unreasonably high or low for the damages described
2. Damage severity seems inconsistent with the damage type described
3. Unusual combination of damaged components that wouldn't make physical sense
4. Any component marked "replace" at very low severity (< 0.2) without justification
5. Grand total seems implausible for this type/year vehicle

Return ONLY valid JSON:
{{
  "looks_reasonable": true,
  "warnings": [
    "Brief description of each concern, or empty array if none"
  ]
}}
"""


async def run_sanity_check(report: AssessmentReport) -> list[str]:
    """Run a second-pass LLM review of the full report.

    Returns a list of warning strings (empty if everything looks fine).
    """
    if not report.damage_assessment.damages:
        return []

    damage_summary = "\n".join(
        f"  - {d.component}: {d.damage_type}, severity {d.severity:.2f}, "
        f"recommendation={d.recommendation}"
        for d in report.damage_assessment.damages
    )

    prompt = _SANITY_PROMPT.format(
        year=report.vehicle.year,
        make=report.vehicle.make,
        model=report.vehicle.model,
        grand_total=report.totals.grand_total,
        damage_summary=damage_summary,
    )

    try:
        raw = await text_completion(prompt=prompt, max_tokens=400, temperature=0.1)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
            cleaned = cleaned.rsplit("```", 1)[0].strip()

        data = json.loads(cleaned)
        warnings = data.get("warnings", [])
        if not data.get("looks_reasonable", True) and not warnings:
            warnings = ["AI flagged this assessment as potentially inconsistent — manual review recommended."]

        logger.info("Sanity check result: reasonable=%s, warnings=%d", data.get("looks_reasonable"), len(warnings))
        return [w for w in warnings if w]

    except Exception:
        logger.exception("Sanity check failed — skipping")
        return []

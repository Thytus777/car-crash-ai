from decimal import Decimal
from unittest.mock import AsyncMock, patch

from app.core.llm import LLMRateLimitError
from app.models.damage import DamageAssessment, DamageItem
from app.models.estimate import AssessmentReport, ReportTotals
from app.models.llm_outputs import SanityReview
from app.models.vehicle import Vehicle
from app.services.sanity_check import run_sanity_check
from tests.llm_fakes import llm_result


def _report() -> AssessmentReport:
    damage = DamageItem(
        component="hood",
        damage_type="dent",
        severity=0.4,
        description="Dented",
        recommendation="replace",
    )
    zero = Decimal("0.00")
    return AssessmentReport(
        vehicle=Vehicle(make="Toyota", model="Camry", year=2020),
        damage_assessment=DamageAssessment(damages=[damage]),
        totals=ReportTotals(parts_total=zero, labor_total=zero, grand_total=zero),
    )


async def test_sanity_warnings_are_returned() -> None:
    review = SanityReview(looks_reasonable=False, warnings=["Cost looks low"])
    with patch(
        "app.services.sanity_check.generate",
        new_callable=AsyncMock,
        return_value=llm_result(review),
    ):
        assert await run_sanity_check(_report()) == ["Cost looks low"]


async def test_unreasonable_without_reasons_gets_a_generic_warning() -> None:
    review = SanityReview(looks_reasonable=False, warnings=[])
    with patch(
        "app.services.sanity_check.generate",
        new_callable=AsyncMock,
        return_value=llm_result(review),
    ):
        warnings = await run_sanity_check(_report())

    assert warnings is not None and "manual review" in warnings[0]


async def test_failed_sanity_check_returns_none_not_an_empty_all_clear() -> None:
    """Regression for #3: a failed review used to look like 'no warnings'."""
    with patch(
        "app.services.sanity_check.generate",
        new_callable=AsyncMock,
        side_effect=LLMRateLimitError("quota"),
    ):
        assert await run_sanity_check(_report()) is None

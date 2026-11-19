"""Property-based tests (Hypothesis) for schema validation and cost maths."""

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from app.core.config import settings
from app.core.llm import backoff_delay
from app.models.damage import STANDARD_COMPONENTS
from app.models.estimate import CostEstimate
from app.models.llm_outputs import DamageFinding, PriceEstimate
from app.services.cost_estimate import compute_totals
from app.services.damage_detect import _get_threshold, to_damage_items

cents = st.decimals(
    min_value=Decimal("0"), max_value=Decimal("50000"), places=2, allow_nan=False
)
components = st.sampled_from(STANDARD_COMPONENTS)
damage_types = st.sampled_from(
    ["scratch", "dent", "crack", "shatter", "crush", "deformation", "missing"]
)


@st.composite
def cost_estimates(draw: st.DrawFn) -> CostEstimate:
    priced = draw(st.booleans())
    part = draw(cents) if priced else None
    labor = draw(cents)
    return CostEstimate(
        component=draw(components),
        recommendation=draw(st.sampled_from(["repair", "replace"])),
        part_cost_low=part,
        part_cost_avg=part,
        part_cost_high=part,
        pricing_method="static_reference" if priced else "unpriced",
        labor_hours=Decimal("1.00"),
        labor_rate=labor,
        labor_cost=labor,
        total_low=None if part is None else part + labor,
        total_avg=None if part is None else part + labor,
        total_high=None if part is None else part + labor,
    )


@given(st.lists(cost_estimates(), max_size=20))
def test_totals_add_up_exactly(estimates: list[CostEstimate]) -> None:
    totals = compute_totals(estimates)

    priced = [e.part_cost_avg for e in estimates if e.part_cost_avg is not None]
    assert totals.parts_total == sum(priced, Decimal("0"))
    assert totals.labor_total == sum((e.labor_cost for e in estimates), Decimal("0"))
    assert totals.grand_total == totals.parts_total + totals.labor_total
    assert totals.unpriced_components == [
        e.component for e in estimates if e.part_cost_avg is None
    ]
    for value in (totals.parts_total, totals.labor_total, totals.grand_total):
        assert value.as_tuple().exponent == -2  # always exactly 2 dp


@given(st.lists(cost_estimates(), max_size=20), st.randoms())
def test_totals_do_not_depend_on_order(
    estimates: list[CostEstimate], rng: object
) -> None:
    shuffled = list(estimates)
    rng.shuffle(shuffled)  # type: ignore[attr-defined]
    a, b = compute_totals(estimates), compute_totals(shuffled)
    assert (a.parts_total, a.labor_total, a.grand_total) == (
        b.parts_total,
        b.labor_total,
        b.grand_total,
    )


@given(components, damage_types, st.floats(min_value=0.0, max_value=1.0))
def test_in_range_findings_validate_and_get_threshold_based_advice(
    component: str, damage_type: str, severity: float
) -> None:
    finding = DamageFinding.model_validate(
        {
            "component": component,
            "damage_type": damage_type,
            "severity": severity,
            "description": "d",
        }
    )
    (item,) = to_damage_items([finding])
    expected = "replace" if severity > _get_threshold(component) else "repair"
    assert item.recommendation == expected


@given(
    st.one_of(
        st.floats(max_value=-1e-9, allow_nan=False),
        st.floats(min_value=1.0 + 1e-9, allow_nan=False, allow_infinity=False),
    )
)
def test_out_of_range_severity_is_rejected(severity: float) -> None:
    with pytest.raises(ValidationError):
        DamageFinding.model_validate(
            {
                "component": "hood",
                "damage_type": "dent",
                "severity": severity,
                "description": "d",
            }
        )


@given(st.text(min_size=1).filter(lambda s: s not in STANDARD_COMPONENTS))
def test_components_outside_the_taxonomy_are_rejected(component: str) -> None:
    with pytest.raises(ValidationError):
        DamageFinding.model_validate(
            {
                "component": component,
                "damage_type": "dent",
                "severity": 0.5,
                "description": "d",
            }
        )


@given(st.lists(st.floats(min_value=0, max_value=1e6), min_size=3, max_size=3))
def test_price_estimates_validate_iff_ordered(prices: list[float]) -> None:
    low, avg, high = prices
    data = {"price_low": low, "price_avg": avg, "price_high": high, "confidence": 0.5}
    if low <= avg <= high:
        PriceEstimate.model_validate(data)
    else:
        with pytest.raises(ValidationError):
            PriceEstimate.model_validate(data)


@given(st.integers(min_value=1, max_value=60), st.floats(min_value=0.0, max_value=1.0))
def test_backoff_stays_within_its_exponential_cap(failures: int, rand: float) -> None:
    delay = backoff_delay(failures, rand)
    ceiling = min(
        settings.llm_backoff_max_s, settings.llm_backoff_base_s * 2.0 ** (failures - 1)
    )
    assert 0.0 <= delay <= ceiling

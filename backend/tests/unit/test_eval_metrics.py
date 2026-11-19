"""Eval metrics against hand-computed expectations (#15). Synthetic records."""

from decimal import Decimal
from typing import Any

import pytest
from evals.pricing import ModelPrice, Pricing
from evals.records import CallRecord, CaseResult
from evals.schema import CostRange, ExpectedTriage

from evals import metrics

ASSESSABLE = ExpectedTriage(shows_vehicle=True, usable=True)
NOT_A_CAR = ExpectedTriage(shows_vehicle=False, usable=False)


def case(**fields: Any) -> CaseResult:
    defaults: dict[str, Any] = {
        "case_id": "c",
        "tags": [],
        "status": "assessed",
        "expected_triage": ASSESSABLE,
        "triage": "accepted",
        "expected_damages": {},
        "wall_s": 1.0,
    }
    defaults.update(fields)
    return CaseResult(**defaults)


def call(ok: bool = True, attempts: int = 1, invalid: int = 0, **kw: Any) -> CallRecord:
    fields: dict[str, Any] = {
        "task": "t",
        "provider": "gemini",
        "model": "m",
        "ok": ok,
        "attempts": attempts,
        "invalid_outputs": invalid,
        "input_tokens": 1000,
        "output_tokens": 100,
        "latency_s": 1.0,
        "cached": False,
    }
    fields.update(kw)
    return CallRecord(**fields)


def test_component_detection_micro_averages_over_cases() -> None:
    cases = [
        case(
            expected_damages={"hood": "moderate", "grille": "minor"},
            predicted_damages={"hood": 0.5, "front_bumper": 0.3},
        ),
        case(case_id="clean", expected_damages={}, predicted_damages={}),
        case(
            case_id="cat",
            expected_triage=NOT_A_CAR,
            status="rejected",
            triage="not_a_vehicle",
        ),
    ]

    d = metrics.detection(cases)

    assert (d.overall.tp, d.overall.fp, d.overall.fn) == (1, 1, 1)
    assert d.overall.precision == d.overall.recall == d.overall.f1 == 0.5
    assert d.per_component["grille"].recall == 0.0
    assert d.per_component["front_bumper"].precision == 0.0
    assert d.cases == 2  # the rejected non-vehicle isn't scored for detection


def test_detection_with_nothing_to_score_is_none_not_zero() -> None:
    assert metrics.detection([]).overall.f1 is None


def test_severity_compares_levels_on_true_positives_only() -> None:
    cases = [
        case(
            expected_damages={"hood": "moderate", "grille": "minor", "roof": "minor"},
            predicted_damages={"hood": 0.5, "grille": 0.7},  # grille: severe vs minor
        )
    ]

    s = metrics.severity(cases)

    assert s.n == 2
    assert s.exact == 0.5
    assert s.within_one == 0.5  # severe is two levels from minor


def test_triage_accuracy_recall_and_false_rejects() -> None:
    cases = [
        case(),  # assessable, accepted: correct
        case(expected_triage=NOT_A_CAR, status="rejected", triage="not_a_vehicle"),
        case(status="rejected", triage="unusable"),  # assessable but rejected
        case(triage="unchecked"),  # triage couldn't run: not scored
    ]

    t = metrics.triage(cases)

    assert t.n == 3
    assert t.accuracy == pytest.approx(2 / 3)
    assert t.reject_recall == 1.0
    assert t.false_reject_rate == 0.5
    assert t.unchecked == 1


def test_cost_uses_range_midpoint_and_skips_other_currencies() -> None:
    usd = CostRange(
        currency="USD", low=Decimal("400"), high=Decimal("600"), basis="repair_quote"
    )
    aud = CostRange(
        currency="AUD", low=Decimal("1"), high=Decimal("2"), basis="repair_quote"
    )
    cases = [
        case(expected_cost=usd, predicted_total=Decimal("700")),
        case(expected_cost=usd, predicted_total=Decimal("450")),
        case(expected_cost=aud, predicted_total=Decimal("1.5")),
    ]

    c = metrics.cost(cases)

    assert c.n == 2
    assert c.mae == pytest.approx((200 + 50) / 2)
    assert c.within_range == 0.5
    assert c.skipped_other_currency == 1
    assert c.by_basis["repair_quote"].n == 2


def test_reliability_rates_come_from_model_calls() -> None:
    cases = [
        case(calls=[call(), call(attempts=2, invalid=1), call(ok=False, attempts=3)]),
        case(status="error", triage=None, error="upstream-timeout"),
    ]

    r = metrics.reliability(cases)

    assert r.calls == 3
    assert r.schema_valid_first_attempt == pytest.approx(1 / 3)
    assert r.retry_rate == pytest.approx(2 / 3)
    assert r.call_failure_rate == pytest.approx(1 / 3)
    assert r.case_error_rate == 0.5


@pytest.mark.parametrize(
    ("values", "pct", "expected"),
    [
        ([1.0, 2.0, 3.0, 4.0], 50, 2.5),
        ([1.0, 2.0, 3.0, 4.0], 95, 3.85),
        ([7.0], 95, 7.0),
    ],
)
def test_percentile_interpolates(
    values: list[float], pct: float, expected: float
) -> None:
    assert metrics.percentile(values, pct) == pytest.approx(expected)


def test_latency_uses_model_time_so_cached_runs_still_report_it() -> None:
    cases = [
        case(
            calls=[call(latency_s=2.0, cached=True), call(latency_s=1.0, cached=True)]
        ),
        case(calls=[call(latency_s=5.0)]),
    ]

    lat = metrics.latency(cases)

    assert (lat.p50_s, lat.n) == (pytest.approx(4.0), 2)
    assert lat.cached_fraction == pytest.approx(2 / 3)


def test_spend_is_none_until_every_model_is_priced() -> None:
    cases = [case(calls=[call(), call(model="other")])]
    price = ModelPrice(
        input_usd_per_mtok=Decimal("1.00"),
        output_usd_per_mtok=Decimal("4.00"),
        source="https://example.test/pricing",
        checked="2026-11-19",  # type: ignore[arg-type]
    )

    partial = metrics.spend(cases, Pricing(models={"gemini/m": price}))
    full = metrics.spend(
        cases, Pricing(models={"gemini/m": price, "gemini/other": price})
    )

    assert partial.per_request_usd is None
    assert partial.unpriced_models == ["gemini/other"]
    # 2 calls x (1000 in x $1/M + 100 out x $4/M) = 2 x $0.0014
    assert full.per_request_usd == pytest.approx(0.0028)


def test_metrics_are_sliced_by_tag() -> None:
    cases = [
        case(tags=["night"], expected_damages={"hood": "minor"}, predicted_damages={}),
        case(
            tags=["night", "glare"],
            expected_damages={"hood": "minor"},
            predicted_damages={"hood": 0.2},
        ),
    ]

    tags = metrics.by_tag(cases)

    assert tags["night"].n == 2 and tags["night"].component_f1 == pytest.approx(2 / 3)
    assert tags["glare"].component_f1 == 1.0

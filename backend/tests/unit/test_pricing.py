"""Model price table and cost per call / request (#Phase 5)."""

import datetime as dt
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.llm import LLMCall, Usage
from app.core.pricing import ModelPrice, Pricing, load_pricing
from app.models.estimate import AssessmentMeta

PRICE = ModelPrice(
    input_usd_per_mtok=Decimal("0.50"),
    output_usd_per_mtok=Decimal("2.00"),
    source="https://example.test/pricing",
    checked=dt.date(2026, 11, 19),
)


def test_the_shipped_price_table_parses() -> None:
    assert isinstance(load_pricing(), Pricing)


def test_cost_is_tokens_times_rate_and_none_for_unpriced_models() -> None:
    table = Pricing(models={"gemini/flash": PRICE})

    # 2,000 in x $0.50/M + 500 out x $2.00/M = $0.001 + $0.001
    assert table.cost("gemini", "flash", 2_000, 500) == Decimal("0.002")
    assert table.cost("gemini", "other", 2_000, 500) is None


def test_prices_need_a_source_and_non_negative_rates() -> None:
    with pytest.raises(ValidationError):
        ModelPrice.model_validate(
            {
                "input_usd_per_mtok": -1,
                "output_usd_per_mtok": 1,
                "source": "x",
                "checked": "2026-11-19",
            }
        )
    with pytest.raises(ValidationError):
        ModelPrice.model_validate(
            {"input_usd_per_mtok": 1, "output_usd_per_mtok": 1, "checked": "2026-11-19"}
        )


def _call(cost: float | None) -> LLMCall:
    return LLMCall(
        task="t",
        provider="gemini",
        model="m",
        ok=True,
        attempts=1,
        invalid_outputs=0,
        usage=Usage(10, 5),
        latency_s=0.1,
        cost_usd=cost,
    )


def test_request_cost_is_the_sum_only_when_every_call_is_priced() -> None:
    assert AssessmentMeta.from_calls("v", [_call(0.25), _call(0.5)]).cost_usd == 0.75
    assert AssessmentMeta.from_calls("v", [_call(0.25), _call(None)]).cost_usd is None
    assert AssessmentMeta.from_calls("v", []).cost_usd == 0

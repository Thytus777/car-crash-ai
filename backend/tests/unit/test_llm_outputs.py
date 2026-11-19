from typing import get_args

import pytest
from pydantic import ValidationError

from app.models.damage import STANDARD_COMPONENTS
from app.models.llm_outputs import Component, DamageFindings, PriceEstimate


def test_component_literal_matches_standard_components() -> None:
    assert list(get_args(Component)) == STANDARD_COMPONENTS


def test_damage_findings_reject_unknown_components_and_out_of_range_severity() -> None:
    with pytest.raises(ValidationError):
        DamageFindings.model_validate_json(
            '{"damages": [{"component": "flux_capacitor", "damage_type": "dent",'
            ' "severity": 0.5, "description": "x"}]}'
        )
    with pytest.raises(ValidationError):
        DamageFindings.model_validate_json(
            '{"damages": [{"component": "hood", "damage_type": "dent",'
            ' "severity": 1.5, "description": "x"}]}'
        )


def test_damage_findings_reject_extra_fields() -> None:
    with pytest.raises(ValidationError):
        DamageFindings.model_validate_json('{"damages": [], "notes": "hi"}')


def test_price_estimate_requires_ordered_range() -> None:
    PriceEstimate(price_low=100, price_avg=150, price_high=200, confidence=0.5)
    with pytest.raises(ValidationError, match="price_low <= price_avg"):
        PriceEstimate(price_low=300, price_avg=150, price_high=200, confidence=0.5)

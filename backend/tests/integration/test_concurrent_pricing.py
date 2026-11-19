"""Components are priced concurrently, within a bound (#7)."""

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.models.damage import DamageAssessment, DamageItem
from app.models.estimate import CostEstimate
from app.models.vehicle import Vehicle
from tests.concurrency import PeakTracker

REQUEST = {
    "upload_id": "0123456789ab",
    "make": "Toyota",
    "model": "Camry",
    "year": 2020,
}
PARTS = ["hood", "grille", "front_bumper", "headlight_left", "headlight_right"]


def _cost(_vehicle: Vehicle, damage: DamageItem) -> CostEstimate:
    one = Decimal("1.00")
    return CostEstimate(
        component=damage.component,
        recommendation="repair",
        part_cost_low=one,
        part_cost_avg=one,
        part_cost_high=one,
        labor_hours=one,
        labor_rate=one,
        labor_cost=one,
        total_low=one,
        total_avg=one,
        total_high=one,
    )


async def test_components_are_priced_concurrently_up_to_the_limit(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "pricing_concurrency", 3)
    tracker = PeakTracker()
    damages = [
        DamageItem(
            component=c,
            damage_type="dent",
            severity=0.2,
            description="x",
            recommendation="repair",
        )
        for c in PARTS
    ]
    with (
        patch(
            "app.api.routes.analysis.detect_damage",
            new_callable=AsyncMock,
            return_value=DamageAssessment(damages=damages),
        ),
        patch("app.api.routes.analysis.estimate_cost", side_effect=tracker.wrap(_cost)),
        patch(
            "app.api.routes.analysis.run_sanity_check",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        body = (await client.post("/api/v1/analyze", json=REQUEST)).json()

    assert tracker.peak == 3
    assert [c["component"] for c in body["cost_estimates"]] == PARTS  # order kept

import json
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.models.damage import DamageAssessment, DamageItem
from app.models.vehicle import Vehicle


def _mock_vehicle(confidence: float = 0.95) -> Vehicle:
    return Vehicle(
        make="Toyota",
        model="Camry",
        year=2020,
        body_style="sedan",
        color="white",
        confidence=confidence,
    )


def _mock_damage() -> DamageAssessment:
    return DamageAssessment(
        damages=[
            DamageItem(
                component="front_bumper",
                damage_type="crush",
                severity=0.75,
                description="Crushed inward",
                recommendation="replace",
            ),
        ]
    )


@pytest.mark.asyncio
async def test_analyze_with_vehicle_override(client: AsyncClient) -> None:
    with (
        patch(
            "app.api.routes.analysis.detect_damage",
            new_callable=AsyncMock,
            return_value=_mock_damage(),
        ),
        patch(
            "app.api.routes.analysis.estimate_cost",
            new_callable=AsyncMock,
        ) as mock_cost,
    ):
        from app.models.estimate import CostEstimate

        mock_cost.return_value = CostEstimate(
            component="front_bumper",
            recommendation="replace",
            part_cost_low=Decimal("200.00"),
            part_cost_avg=Decimal("280.00"),
            part_cost_high=Decimal("400.00"),
            pricing_method="static_reference",
            labor_hours=Decimal("3.5"),
            labor_rate=Decimal("75.00"),
            labor_cost=Decimal("262.50"),
            total_low=Decimal("462.50"),
            total_avg=Decimal("542.50"),
            total_high=Decimal("662.50"),
        )

        response = await client.post(
            "/api/v1/analyze",
            json={
                "upload_id": "test123",
                "make": "Toyota",
                "model": "Camry",
                "year": 2020,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["vehicle"]["make"] == "Toyota"
    assert len(body["cost_estimates"]) == 1
    assert body["totals"]["grand_total"] == "542.50"
    assert "disclaimer" in body


@pytest.mark.asyncio
async def test_analyze_low_confidence_returns_confirmation(
    client: AsyncClient,
) -> None:
    with patch(
        "app.api.routes.analysis.identify_vehicle",
        new_callable=AsyncMock,
        return_value=_mock_vehicle(confidence=0.4),
    ):
        response = await client.post(
            "/api/v1/analyze",
            json={"upload_id": "test123"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "vehicle_confirmation_needed"
    assert "Low confidence" in body["message"]

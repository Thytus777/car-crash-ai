"""/analyze reports degraded stages explicitly instead of hiding them (#3)."""

from decimal import Decimal
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient

from app.core.llm import LLMUnavailableError
from app.models.damage import DamageAssessment, DamageItem
from app.models.estimate import CostEstimate
from app.models.vehicle import Vehicle

REQUEST = {
    "upload_id": "0123456789ab",
    "make": "Toyota",
    "model": "Camry",
    "year": 2020,
}


def _item(component: str) -> DamageItem:
    return DamageItem(
        component=component,
        damage_type="dent",
        severity=0.6,
        description="x",
        recommendation="replace",
    )


async def _cost(_vehicle: Vehicle, damage: DamageItem) -> CostEstimate:
    labor = Decimal("100.00")
    if damage.component == "hood":
        return CostEstimate(
            component="hood",
            recommendation="replace",
            part_cost_low=None,
            part_cost_avg=None,
            part_cost_high=None,
            pricing_method="unpriced",
            labor_hours=Decimal("2.5"),
            labor_rate=Decimal("40.00"),
            labor_cost=labor,
            total_low=None,
            total_avg=None,
            total_high=None,
        )
    part = Decimal("300.00")
    return CostEstimate(
        component=damage.component,
        recommendation="replace",
        part_cost_low=part,
        part_cost_avg=part,
        part_cost_high=part,
        pricing_method="static_reference",
        labor_hours=Decimal("2.5"),
        labor_rate=Decimal("40.00"),
        labor_cost=labor,
        total_low=part + labor,
        total_avg=part + labor,
        total_high=part + labor,
    )


async def test_degraded_stages_make_the_report_partial(client: AsyncClient) -> None:
    damage = DamageAssessment(
        damages=[_item("front_bumper"), _item("hood")], failed_zones=["side"]
    )
    with (
        patch(
            "app.api.routes.analysis.detect_damage",
            new_callable=AsyncMock,
            return_value=damage,
        ),
        patch("app.api.routes.analysis.estimate_cost", side_effect=_cost),
        patch(
            "app.api.routes.analysis.run_sanity_check",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        response = await client.post("/api/v1/analyze", json=REQUEST)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "partial"
    assert [(i["stage"], i["scope"]) for i in body["issues"]] == [
        ("damage_detection", "side"),
        ("pricing", "hood"),
        ("sanity_check", None),
    ]
    assert body["totals"]["parts_total"] == "300.00"  # hood excluded
    assert body["totals"]["labor_total"] == "200.00"  # labour known for both
    assert body["totals"]["unpriced_components"] == ["hood"]


async def test_clean_run_is_complete_with_no_issues(client: AsyncClient) -> None:
    damage = DamageAssessment(damages=[_item("front_bumper")])
    with (
        patch(
            "app.api.routes.analysis.detect_damage",
            new_callable=AsyncMock,
            return_value=damage,
        ),
        patch("app.api.routes.analysis.estimate_cost", side_effect=_cost),
        patch(
            "app.api.routes.analysis.run_sanity_check",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        body = (await client.post("/api/v1/analyze", json=REQUEST)).json()

    assert body["status"] == "complete" and body["issues"] == []


async def test_all_zones_failing_is_a_503_problem(client: AsyncClient) -> None:
    with (
        patch("app.services.damage_detect.load_images", return_value=[b"jpeg"]),
        patch(
            "app.services.damage_detect.generate",
            side_effect=LLMUnavailableError("gemini damage: unavailable"),
        ),
    ):
        response = await client.post("/api/v1/analyze", json=REQUEST)

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")

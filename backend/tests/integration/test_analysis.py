from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.db.session as db_session
from app.db.models import EstimateRecord, UploadSession
from app.models.damage import DamageAssessment, DamageItem
from app.models.estimate import CostEstimate
from app.models.vehicle import Vehicle

UPLOAD_ID = "0123456789ab"
OVERRIDE_REQUEST = {
    "upload_id": UPLOAD_ID,
    "make": "Toyota",
    "model": "Camry",
    "year": 2020,
}


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


def _mock_cost() -> CostEstimate:
    return CostEstimate(
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


@pytest.fixture
def pipeline_mocks() -> Iterator[None]:
    """Stub every LLM-backed stage after vehicle ID."""
    with (
        patch(
            "app.api.routes.analysis.detect_damage",
            new_callable=AsyncMock,
            return_value=_mock_damage(),
        ),
        patch(
            "app.api.routes.analysis.estimate_cost",
            new_callable=AsyncMock,
            return_value=_mock_cost(),
        ),
        patch(
            "app.api.routes.analysis.run_sanity_check",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        yield


@pytest.mark.usefixtures("pipeline_mocks")
async def test_analyze_with_vehicle_override(client: AsyncClient) -> None:
    response = await client.post("/api/v1/analyze", json=OVERRIDE_REQUEST)

    assert response.status_code == 200
    body = response.json()
    assert body["vehicle"]["make"] == "Toyota"
    assert len(body["cost_estimates"]) == 1
    assert body["totals"]["grand_total"] == "542.50"
    assert "disclaimer" in body


@pytest.mark.usefixtures("pipeline_mocks")
async def test_analyze_persists_estimate_and_returns_its_id(
    client: AsyncClient, test_db: async_sessionmaker[AsyncSession]
) -> None:
    """Regression for #1: no UploadSession row existed, so the FK failed."""
    response = await client.post("/api/v1/analyze", json=OVERRIDE_REQUEST)

    assert response.status_code == 200
    estimate_id = response.json()["estimate_id"]
    assert isinstance(estimate_id, int)

    async with test_db() as session:
        record = await session.get(EstimateRecord, estimate_id)
        assert record is not None
        assert record.upload_id == UPLOAD_ID
        assert record.grand_total == pytest.approx(542.50)
        upload = await session.scalar(
            select(UploadSession).where(UploadSession.id == UPLOAD_ID)
        )
        assert upload is not None


@pytest.mark.usefixtures("pipeline_mocks")
async def test_analyze_returns_report_when_database_is_unavailable(
    client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression for #1: a failed save must not turn the response into a 500."""
    unreachable = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'missing-dir' / 'db.sqlite'}"
    )
    monkeypatch.setattr(
        db_session, "AsyncSessionLocal", async_sessionmaker(unreachable)
    )

    response = await client.post("/api/v1/analyze", json=OVERRIDE_REQUEST)

    assert response.status_code == 200
    body = response.json()
    assert body["totals"]["grand_total"] == "542.50"
    assert body["estimate_id"] is None
    await unreachable.dispose()


async def test_analyze_low_confidence_returns_confirmation(
    client: AsyncClient,
) -> None:
    with patch(
        "app.api.routes.analysis.identify_vehicle",
        new_callable=AsyncMock,
        return_value=_mock_vehicle(confidence=0.4),
    ):
        response = await client.post("/api/v1/analyze", json={"upload_id": UPLOAD_ID})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "vehicle_confirmation_needed"
    assert "Low confidence" in body["message"]


@pytest.mark.usefixtures("pipeline_mocks")
async def test_saved_estimate_round_trips_through_history_endpoints(
    client: AsyncClient,
) -> None:
    created = (await client.post("/api/v1/analyze", json=OVERRIDE_REQUEST)).json()

    fetched = await client.get(f"/api/v1/estimates/{created['estimate_id']}")
    listing = await client.get("/api/v1/estimates")

    assert fetched.status_code == 200
    assert fetched.json()["estimate_id"] == created["estimate_id"]
    assert fetched.json()["totals"] == created["totals"]
    assert [e["id"] for e in listing.json()] == [created["estimate_id"]]
    assert (await client.get("/api/v1/estimates/999999")).status_code == 404


@pytest.mark.usefixtures("pipeline_mocks")
async def test_every_report_records_the_prompt_version(client: AsyncClient) -> None:
    body = (await client.post("/api/v1/analyze", json=OVERRIDE_REQUEST)).json()

    assert body["meta"]["prompt_version"] == "v1"
    assert body["meta"]["llm_calls"] == 0  # all model-backed stages are mocked


async def test_confirmation_response_also_records_the_prompt_version(
    client: AsyncClient,
) -> None:
    with patch(
        "app.api.routes.analysis.identify_vehicle",
        new_callable=AsyncMock,
        return_value=_mock_vehicle(confidence=0.4),
    ):
        body = (
            await client.post("/api/v1/analyze", json={"upload_id": UPLOAD_ID})
        ).json()

    assert body["status"] == "vehicle_confirmation_needed"
    assert body["meta"]["prompt_version"] == "v1"

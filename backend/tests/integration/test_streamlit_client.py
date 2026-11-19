"""The Streamlit demo's HTTP calls work against the real API (#4)."""

import sys
from collections.abc import Iterator
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.models.damage import DamageAssessment, DamageItem
from app.models.estimate import CostEstimate
from app.models.vehicle import Vehicle

sys.path.insert(0, str(Path(__file__).parents[3] / "frontend"))
import api_client  # noqa: E402


def _jpeg() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (800, 600), color="red").save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def http() -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client


@pytest.fixture
def pipeline() -> Iterator[None]:
    one = Decimal("120.00")
    cost = CostEstimate(
        component="hood",
        recommendation="replace",
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
    damage = DamageItem(
        component="hood",
        damage_type="dent",
        severity=0.5,
        description="x",
        recommendation="replace",
    )
    with (
        patch(
            "app.api.routes.analysis.detect_damage",
            new_callable=AsyncMock,
            return_value=DamageAssessment(damages=[damage]),
        ),
        patch(
            "app.api.routes.analysis.estimate_cost",
            new_callable=AsyncMock,
            return_value=cost,
        ),
        patch(
            "app.api.routes.analysis.run_sanity_check",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        yield


@pytest.mark.usefixtures("pipeline")
def test_upload_then_analyze_round_trip(http: TestClient) -> None:
    uploaded = api_client.upload(http, [("car.jpg", _jpeg(), "image/jpeg")])
    report = api_client.analyze(
        http, uploaded["upload_id"], make="Toyota", model="Camry", year=2020
    )

    assert report["status"] == "complete"
    assert report["cost_estimates"][0]["component"] == "hood"


def test_low_confidence_vehicle_asks_for_confirmation(http: TestClient) -> None:
    uploaded = api_client.upload(http, [("car.jpg", _jpeg(), "image/jpeg")])
    guess = Vehicle(make="Toyota", model="Camry", year=2020, confidence=0.3)
    with patch(
        "app.api.routes.analysis.identify_vehicle",
        new_callable=AsyncMock,
        return_value=guess,
    ):
        result = api_client.analyze(http, uploaded["upload_id"])

    assert result["status"] == "vehicle_confirmation_needed"
    assert result["vehicle_guess"]["make"] == "Toyota"


def test_errors_surface_the_problem_detail(http: TestClient) -> None:
    gif = BytesIO()
    Image.new("RGB", (800, 600)).save(gif, format="GIF")

    with pytest.raises(api_client.ApiError) as exc_info:
        api_client.upload(http, [("car.gif", gif.getvalue(), "image/gif")])

    assert exc_info.value.status == 415
    assert "JPEG, PNG or WebP" in exc_info.value.detail


def test_money_formats_prices_and_unpriced_parts() -> None:
    assert api_client.money("1234.60") == "$1,235"
    assert api_client.money(None) == "Unpriced"

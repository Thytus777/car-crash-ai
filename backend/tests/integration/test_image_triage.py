"""/analyze screens images before running the pipeline (#27)."""

from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.core.llm import LLMTimeoutError
from app.models.damage import DamageAssessment
from app.models.llm_outputs import ImageTriage

PROBLEM_BASE = "https://github.com/Thytus777/car-crash-ai/blob/main/docs/errors.md#"
REQUEST = {
    "upload_id": "0123456789ab",
    "make": "Toyota",
    "model": "Camry",
    "year": 2020,
}


@pytest.fixture
def pipeline() -> Iterator[AsyncMock]:
    """Stub the stages after triage; yields the damage-detection mock."""
    with (
        patch(
            "app.api.routes.analysis.detect_damage",
            new_callable=AsyncMock,
            return_value=DamageAssessment(),
        ) as detect,
        patch(
            "app.api.routes.analysis.run_sanity_check",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        yield detect


async def test_non_vehicle_upload_is_rejected_before_analysis(
    client: AsyncClient, triage: AsyncMock, pipeline: AsyncMock
) -> None:
    triage.return_value = ImageTriage(
        shows_vehicle=False, usable=False, reason="This is a photo of a cat."
    )

    response = await client.post("/api/v1/analyze", json=REQUEST)

    assert response.status_code == 422
    assert response.json()["type"] == PROBLEM_BASE + "not-a-vehicle"
    assert response.json()["detail"] == "This is a photo of a cat."
    pipeline.assert_not_awaited()


async def test_unusable_images_are_rejected_with_the_reason(
    client: AsyncClient, triage: AsyncMock, pipeline: AsyncMock
) -> None:
    triage.return_value = ImageTriage(
        shows_vehicle=True, usable=False, reason="Too dark; retake in daylight."
    )

    response = await client.post("/api/v1/analyze", json=REQUEST)

    assert response.status_code == 422
    assert response.json()["type"] == PROBLEM_BASE + "unusable-images"
    assert "retake in daylight" in response.json()["detail"]
    pipeline.assert_not_awaited()


async def test_triage_runs_even_when_the_vehicle_is_given(
    client: AsyncClient, triage: AsyncMock, pipeline: AsyncMock
) -> None:
    await client.post("/api/v1/analyze", json=REQUEST)

    triage.assert_awaited_once_with("0123456789ab")


async def test_triage_outage_continues_but_flags_the_report(
    client: AsyncClient, triage: AsyncMock, pipeline: AsyncMock
) -> None:
    triage.side_effect = LLMTimeoutError("gemini image_triage: timeout")

    response = await client.post("/api/v1/analyze", json=REQUEST)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "partial"
    assert [i["stage"] for i in body["issues"]] == ["image_triage"]

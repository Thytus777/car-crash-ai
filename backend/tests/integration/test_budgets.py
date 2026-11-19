"""Per-call cost and per-request budgets (Phase 5)."""

import datetime as dt
import logging
from collections.abc import Iterator
from decimal import Decimal
from io import BytesIO

import pytest
from httpx import AsyncClient
from PIL import Image
from prometheus_client import REGISTRY
from pydantic import SecretStr

import app.core.llm as llm
from app.core.config import settings
from app.core.pricing import ModelPrice, Pricing
from tests.llm_fakes import SchemaClient

pytestmark = pytest.mark.real_triage

# SchemaClient reports 500 input + 50 output tokens per call:
# 500 x $1/M + 50 x $10/M = $0.001 per call.
FAKE_PRICE = ModelPrice(
    input_usd_per_mtok=Decimal("1"),
    output_usd_per_mtok=Decimal("10"),
    source="https://example.test/pricing",
    checked=dt.date(2026, 11, 19),
)


def _metric(name: str, **labels: str) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


@pytest.fixture
def priced_fake(monkeypatch: pytest.MonkeyPatch) -> Iterator[SchemaClient]:
    fake = SchemaClient()
    monkeypatch.setattr(settings, "openai_api_key", SecretStr(""))
    monkeypatch.setattr(llm, "get_client", lambda _p: fake)
    monkeypatch.setattr(
        llm, "pricing", lambda: Pricing(models={"gemini/fake-model": FAKE_PRICE})
    )
    yield fake


async def _analyze(client: AsyncClient) -> dict[str, object]:
    buf = BytesIO()
    Image.new("RGB", (800, 600), color="red").save(buf, format="JPEG")
    upload = await client.post(
        "/api/v1/upload", files=[("images", ("car.jpg", buf.getvalue(), "image/jpeg"))]
    )
    response = await client.post(
        "/api/v1/analyze", json={"upload_id": upload.json()["upload_id"]}
    )
    assert response.status_code == 200
    meta: dict[str, object] = response.json()["meta"]
    return meta


async def test_cost_per_request_is_the_sum_of_priced_calls(
    client: AsyncClient, priced_fake: SchemaClient
) -> None:
    before = _metric("llm_cost_usd_total", provider="gemini", model="fake-model")

    meta = await _analyze(client)

    assert meta["cost_usd"] == pytest.approx(0.001 * meta["llm_calls"])  # type: ignore[operator]
    assert meta["budget_exceeded"] == []
    after = _metric("llm_cost_usd_total", provider="gemini", model="fake-model")
    assert after - before == pytest.approx(meta["cost_usd"])


async def test_cost_is_null_while_any_model_is_unpriced(
    client: AsyncClient, priced_fake: SchemaClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(llm, "pricing", Pricing)  # empty table

    meta = await _analyze(client)

    assert meta["cost_usd"] is None


async def test_requests_over_budget_are_flagged_logged_and_counted(
    client: AsyncClient,
    priced_fake: SchemaClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(settings, "request_cost_budget_usd", 0.0001)
    monkeypatch.setattr(settings, "request_latency_budget_s", 0.0)
    before = {
        b: _metric("budget_exceeded_total", budget=b) for b in ("cost", "latency")
    }
    caplog.set_level(logging.WARNING)

    meta = await _analyze(client)

    assert meta["budget_exceeded"] == ["cost", "latency"]
    for budget in ("cost", "latency"):
        assert _metric("budget_exceeded_total", budget=budget) == before[budget] + 1
    assert any("over budget" in r.getMessage() for r in caplog.records)

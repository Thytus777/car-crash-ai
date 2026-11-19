"""Prometheus metrics (#16)."""

import pytest
from httpx import AsyncClient
from prometheus_client import REGISTRY
from pydantic import SecretStr

import app.core.llm as llm
from app.core.config import settings
from app.core.llm import generate
from app.models.llm_outputs import SanityReview
from tests.llm_fakes import SchemaClient


def value(name: str, **labels: str) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


async def test_metrics_endpoint_serves_prometheus_text(client: AsyncClient) -> None:
    response = await client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "# TYPE http_requests_total counter" in response.text


async def test_requests_are_counted_by_route_template_not_raw_path(
    client: AsyncClient,
) -> None:
    labels = {
        "route": "/api/v1/estimates/{estimate_id}",
        "method": "GET",
        "status": "404",
    }
    before = value("http_requests_total", **labels)

    await client.get("/api/v1/estimates/1")
    await client.get("/api/v1/estimates/2")

    assert value("http_requests_total", **labels) == before + 2
    assert (
        value(
            "http_requests_total",
            route="/api/v1/estimates/1",
            method="GET",
            status="404",
        )
        == 0.0
    )
    assert (
        value(
            "http_request_duration_seconds_count",
            route="/api/v1/estimates/{estimate_id}",
            method="GET",
        )
        >= 2
    )


async def test_unknown_paths_share_one_label(client: AsyncClient) -> None:
    labels = {"route": "unmatched", "method": "GET", "status": "404"}
    before = value("http_requests_total", **labels)

    await client.get("/no/such/path/123")

    assert value("http_requests_total", **labels) == before + 1


async def test_model_calls_record_outcome_tokens_and_latency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = SchemaClient()
    monkeypatch.setattr(settings, "openai_api_key", SecretStr(""))
    monkeypatch.setattr(llm, "get_client", lambda _p: fake)
    calls = {
        "provider": "gemini",
        "model": "fake-model",
        "task": "sanity_check",
        "outcome": "ok",
        "cached": "false",
    }
    tokens = {"provider": "gemini", "model": "fake-model", "direction": "input"}
    before_calls, before_tokens = (
        value("llm_calls_total", **calls),
        value("llm_tokens_total", **tokens),
    )

    await generate(SanityReview, "q", task="sanity_check", max_output_tokens=10)

    assert value("llm_calls_total", **calls) == before_calls + 1
    assert value("llm_tokens_total", **tokens) == before_tokens + 500
    assert (
        value("llm_call_duration_seconds_count", provider="gemini", task="sanity_check")
        >= 1
    )

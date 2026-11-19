"""Request IDs, structured logs and health endpoints (#16)."""

import json
import logging
import re
from pathlib import Path

import pytest
from httpx import AsyncClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.db.session as db_session
from app.core.config import settings
from app.core.logging import JsonFormatter


async def test_every_response_carries_a_generated_request_id(
    client: AsyncClient,
) -> None:
    response = await client.get("/healthz")

    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["x-request-id"])


async def test_a_well_formed_incoming_request_id_is_kept(client: AsyncClient) -> None:
    response = await client.get("/healthz", headers={"X-Request-ID": "edge-abc.123"})

    assert response.headers["x-request-id"] == "edge-abc.123"


async def test_a_malformed_incoming_request_id_is_replaced(client: AsyncClient) -> None:
    response = await client.get("/healthz", headers={"X-Request-ID": "bad id\n" * 20})

    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["x-request-id"])


async def test_problem_bodies_include_the_request_id(client: AsyncClient) -> None:
    response = await client.get("/api/v1/estimates/999999")

    assert response.json()["request_id"] == response.headers["x-request-id"]


async def test_logs_during_a_request_carry_its_id_and_an_access_line(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)

    response = await client.get("/api/v1/estimates/999999")

    request_id = response.headers["x-request-id"]
    access = [r for r in caplog.records if r.name == "app.access"]
    assert len(access) == 1
    line = json.loads(JsonFormatter().format(access[0]))
    assert line["request_id"] == request_id
    assert line["method"] == "GET" and line["path"] == "/api/v1/estimates/999999"
    assert line["status"] == 404 and line["duration_ms"] >= 0


async def test_healthz_is_always_ok(client: AsyncClient) -> None:
    response = await client.get("/healthz")

    assert response.status_code == 200 and response.json() == {"status": "ok"}


async def test_readyz_reports_each_check(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr("AIza-test"))

    response = await client.get("/readyz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert {c: v["ok"] for c, v in body["checks"].items()} == {
        "prompts": True,
        "upload_dir": True,
        "llm_provider": True,
        "database": True,
    }


async def test_readyz_is_503_without_any_model_key(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    for key in ("gemini_api_key", "google_ai_gemini_api_key", "openai_api_key"):
        monkeypatch.setattr(settings, key, SecretStr(""))

    response = await client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["checks"]["llm_provider"]["ok"] is False


async def test_a_database_outage_degrades_but_does_not_unready(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr("AIza-test"))
    dead = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'no' / 'db.sqlite'}")
    monkeypatch.setattr(db_session, "AsyncSessionLocal", async_sessionmaker(dead))

    response = await client.get("/readyz")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["checks"]["database"]["ok"] is False
    await dead.dispose()

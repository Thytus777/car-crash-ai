"""Response cache for repeated assessments (#49)."""

import time
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from PIL import Image
from pydantic import SecretStr

import app.core.llm as llm
from app.core.config import settings
from app.services.result_cache import cache_key
from tests.llm_fakes import SchemaClient

pytestmark = pytest.mark.real_triage


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[SchemaClient]:
    client = SchemaClient()
    monkeypatch.setattr(settings, "openai_api_key", SecretStr(""))
    monkeypatch.setattr(llm, "get_client", lambda _p: client)
    monkeypatch.setattr(settings, "result_cache_enabled", True)
    monkeypatch.setattr(settings, "result_cache_dir", tmp_path / "result-cache")
    yield client


def _photo(colour: tuple[int, int, int] = (200, 20, 20)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (800, 600), color=colour).save(buf, format="JPEG")
    return buf.getvalue()


async def _assess(
    client: AsyncClient, photo: bytes | None = None, **body: Any
) -> dict[str, Any]:
    upload = await client.post(
        "/api/v1/upload",
        files=[("images", ("car.jpg", photo or _photo(), "image/jpeg"))],
    )
    response = await client.post(
        "/api/v1/analyze", json={"upload_id": upload.json()["upload_id"], **body}
    )
    assert response.status_code == 200
    result: dict[str, Any] = response.json()
    return result


async def test_identical_photos_are_served_from_cache_without_model_calls(
    client: AsyncClient, fake: SchemaClient
) -> None:
    first = await _assess(client)
    calls_after_first = fake.requests

    second = await _assess(client)  # a new upload of the same photo

    assert fake.requests == calls_after_first
    assert (first["meta"]["cached"], second["meta"]["cached"]) == (False, True)
    assert second["damage_assessment"] == first["damage_assessment"]
    assert second["totals"] == first["totals"]
    assert second["meta"]["prompt_version"] == first["meta"]["prompt_version"]


async def test_different_photos_or_options_miss(
    client: AsyncClient, fake: SchemaClient
) -> None:
    await _assess(client)
    other_photo = await _assess(client, photo=_photo((210, 25, 25)))
    with_vehicle = await _assess(client, make="Toyota", model="Camry", year=2020)

    assert other_photo["meta"]["cached"] is False
    assert with_vehicle["meta"]["cached"] is False


async def test_a_different_model_misses(
    client: AsyncClient, fake: SchemaClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _assess(client)
    monkeypatch.setattr(settings, "gemini_model", "another-model")

    assert (await _assess(client))["meta"]["cached"] is False


def test_key_covers_prompt_version_images_and_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = cache_key([b"a", b"b"], {"vin": None})

    assert cache_key([b"b", b"a"], {"vin": None}) == base  # order-independent
    assert cache_key([b"a"], {"vin": None}) != base
    assert cache_key([b"a", b"b"], {"vin": "1HGCM82633A004352"}) != base
    monkeypatch.setattr(settings, "prompt_version", "v-next")
    assert cache_key([b"a", b"b"], {"vin": None}) != base


async def test_entries_expire_after_the_ttl(
    client: AsyncClient, fake: SchemaClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _assess(client)
    later = time.time() + settings.result_cache_ttl_hours * 3600 + 1
    monkeypatch.setattr("app.services.result_cache.time.time", lambda: later)

    assert (await _assess(client))["meta"]["cached"] is False


async def test_partial_results_are_not_cached(
    client: AsyncClient, fake: SchemaClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def no_review(_report: object) -> None:
        return None  # sanity check "failed": the report is partial

    monkeypatch.setattr("app.services.assessment.run_sanity_check", no_review)
    first = await _assess(client)
    second = await _assess(client)

    assert first["status"] == "partial"
    assert second["meta"]["cached"] is False


async def test_cache_can_be_disabled(
    client: AsyncClient, fake: SchemaClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "result_cache_enabled", False)
    await _assess(client)

    assert (await _assess(client))["meta"]["cached"] is False

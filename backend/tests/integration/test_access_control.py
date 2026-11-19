"""API keys, rate limits, CORS and production guards (#9)."""

import logging
from collections.abc import Iterator

import pytest
from httpx import AsyncClient
from pydantic import SecretStr

from app.api import access
from app.core.config import Settings, settings

KEY = "ck_test_0123456789abcdef"


@pytest.fixture
def keys(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(settings, "api_keys", [SecretStr(KEY)])
    yield


async def test_without_configured_keys_the_api_is_open(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/estimates")).status_code == 200


@pytest.mark.usefixtures("keys")
@pytest.mark.parametrize(
    "headers",
    [{}, {"X-API-Key": "wrong"}, {"Authorization": "Bearer wrong"}, {"X-API-Key": ""}],
)
async def test_missing_or_wrong_keys_get_a_401_problem(
    client: AsyncClient, headers: dict[str, str]
) -> None:
    response = await client.get("/api/v1/estimates", headers=headers)

    assert response.status_code == 401
    assert response.json()["type"].endswith("#unauthorized")
    assert response.headers["www-authenticate"].startswith("Bearer")


@pytest.mark.usefixtures("keys")
@pytest.mark.parametrize(
    "headers", [{"X-API-Key": KEY}, {"Authorization": f"Bearer {KEY}"}]
)
async def test_a_valid_key_is_accepted_in_either_header(
    client: AsyncClient, headers: dict[str, str]
) -> None:
    assert (await client.get("/api/v1/estimates", headers=headers)).status_code == 200


@pytest.mark.usefixtures("keys")
async def test_probes_stay_open_and_metrics_need_a_key(client: AsyncClient) -> None:
    assert (await client.get("/healthz")).status_code == 200
    assert (await client.get("/readyz")).status_code in (200, 503)
    assert (await client.get("/metrics")).status_code == 401
    assert (await client.get("/metrics", headers={"X-API-Key": KEY})).status_code == 200


@pytest.mark.usefixtures("keys")
async def test_keys_never_appear_in_logs(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)

    await client.get("/api/v1/estimates", headers={"X-API-Key": KEY})
    await client.get("/api/v1/estimates", headers={"X-API-Key": KEY + "x"})

    assert KEY not in caplog.text


async def test_requests_over_the_limit_get_429_with_retry_after(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "rate_limit_per_minute", 2)
    access.reset_rate_limits()

    statuses = [(await client.get("/api/v1/estimates")).status_code for _ in range(3)]

    assert statuses == [200, 200, 429]
    limited = await client.get("/api/v1/estimates")
    assert limited.json()["type"].endswith("#rate-limited")
    assert int(limited.headers["retry-after"]) >= 1


async def test_analyze_has_its_own_tighter_bucket(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "rate_limit_per_minute", 100)
    monkeypatch.setattr(settings, "analyze_rate_limit_per_minute", 1)
    access.reset_rate_limits()
    body = {"upload_id": "fedcba987654"}  # unknown upload: 404, still counted

    first = await client.post("/api/v1/analyze", json=body)
    second = await client.post("/api/v1/analyze", json=body)

    assert first.status_code == 404 and second.status_code == 429
    assert (await client.get("/api/v1/estimates")).status_code == 200


async def test_each_key_has_its_own_bucket(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "api_keys", [SecretStr("key-a"), SecretStr("key-b")])
    monkeypatch.setattr(settings, "rate_limit_per_minute", 1)
    access.reset_rate_limits()

    a1 = await client.get("/api/v1/estimates", headers={"X-API-Key": "key-a"})
    a2 = await client.get("/api/v1/estimates", headers={"X-API-Key": "key-a"})
    b1 = await client.get("/api/v1/estimates", headers={"X-API-Key": "key-b"})

    assert (a1.status_code, a2.status_code, b1.status_code) == (200, 429, 200)


async def test_cors_allows_configured_origins_without_credentials(
    client: AsyncClient,
) -> None:
    preflight = await client.options(
        "/api/v1/estimates",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-api-key",
        },
    )
    other = await client.options(
        "/api/v1/estimates",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert preflight.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-credentials" not in preflight.headers
    assert "x-api-key" in preflight.headers["access-control-allow-headers"].lower()
    assert "access-control-allow-origin" not in other.headers


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"api_keys": []}, "API_KEYS"),
        ({"api_keys": ["k"], "cors_origins": ["*"]}, "CORS"),
        ({"api_keys": ["k"], "redaction_required": False}, "REDACTION_REQUIRED"),
    ],
)
def test_production_refuses_unsafe_settings(
    overrides: dict[str, object], message: str
) -> None:
    unsafe = Settings(
        _env_file=None,  # type: ignore[call-arg]
        app_env="production",
        **{
            "redaction_required": True,
            "cors_origins": ["https://app.example"],
            **overrides,
        },
    )

    with pytest.raises(RuntimeError, match=message):
        access.check_production_settings(unsafe)


def test_keys_can_be_given_as_a_comma_separated_env_value() -> None:
    parsed = Settings(_env_file=None, api_keys="k1, k2")  # type: ignore[call-arg, arg-type]

    assert [k.get_secret_value() for k in parsed.api_keys] == ["k1", "k2"]

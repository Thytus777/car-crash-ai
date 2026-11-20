"""The post-deploy smoke test passes against a healthy app (Phase 7)."""

import importlib.util
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import settings
from app.main import app

spec = importlib.util.spec_from_file_location(
    "smoke", Path(__file__).parents[2] / "scripts" / "smoke.py"
)
assert spec and spec.loader
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


@pytest.fixture
def http(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr("AIza-test"))
    with TestClient(app) as client:
        yield client


def test_smoke_passes_without_auth(
    http: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    assert smoke.run(http, None) is True
    assert "FAIL" not in capsys.readouterr().out


def test_smoke_checks_auth_when_given_a_key(
    http: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(settings, "api_keys", [SecretStr("smoke-key")])

    assert smoke.run(http, "smoke-key") is True
    assert "PASS  auth rejects missing key" in capsys.readouterr().out


def test_smoke_fails_when_the_service_is_not_ready(
    http: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for key in ("gemini_api_key", "openai_api_key", "google_ai_gemini_api_key"):
        monkeypatch.setattr(settings, key, SecretStr(""))

    assert smoke.run(http, None) is False
    assert "FAIL  readyz" in capsys.readouterr().out


class _CloudRunFrontEnd:
    """Cloud Run's front end answers /healthz itself with a 404 page."""

    def __init__(self, client: TestClient) -> None:
        self._client = client

    def get(self, path: str, **kwargs: object) -> object:
        if path == "/healthz":
            return type("Response", (), {"status_code": 404, "text": "Not Found"})()
        return self._client.get(path, **kwargs)  # type: ignore[arg-type]

    def post(self, path: str, **kwargs: object) -> object:
        return self._client.post(path, **kwargs)  # type: ignore[arg-type]


def test_smoke_passes_behind_cloud_run_which_reserves_healthz(
    http: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    assert smoke.run(_CloudRunFrontEnd(http), None) is True
    assert "FAIL" not in capsys.readouterr().out

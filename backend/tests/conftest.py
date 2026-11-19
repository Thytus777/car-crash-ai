"""Shared pytest config: tests are marked by the directory they live in."""

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.config import settings
from app.services.redaction import RedactionResult

_MARKERS_BY_DIR = {"unit": pytest.mark.unit, "integration": pytest.mark.integration}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        parent = Path(str(item.fspath)).parent.name
        marker = _MARKERS_BY_DIR.get(parent)
        if marker is not None:
            item.add_marker(marker)


@pytest.fixture(autouse=True)
def isolated_upload_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Path]:
    """Point uploads at a per-test temp dir so tests never touch ./uploads."""
    upload_dir = tmp_path / "uploads"
    monkeypatch.setattr(settings, "upload_dir", upload_dir)
    # Off unless a test opts in, so tests never share cached reports.
    monkeypatch.setattr(settings, "result_cache_enabled", False)
    monkeypatch.setattr(settings, "result_cache_dir", tmp_path / "result-cache")
    yield upload_dir


@pytest.fixture(autouse=True)
def no_redaction(request: pytest.FixtureRequest) -> Iterator[None]:
    """Uploads skip redaction unless a test is marked ``real_redaction``.

    The models live outside git, so whether they're installed must not change
    how ordinary tests behave.
    """
    if request.node.get_closest_marker("real_redaction"):
        yield
        return
    with patch("app.services.image_proc.redact", side_effect=RedactionResult):
        yield


@pytest.fixture(autouse=True)
def fresh_rate_limits() -> Iterator[None]:
    """Rate-limit buckets live in process memory; start each test empty."""
    from app.api.access import reset_rate_limits

    reset_rate_limits()
    yield
    reset_rate_limits()

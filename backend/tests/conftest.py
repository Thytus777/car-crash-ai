"""Shared pytest config: tests are marked by the directory they live in."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from app.core.config import settings

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
    yield upload_dir

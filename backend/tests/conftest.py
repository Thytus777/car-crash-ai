"""Shared pytest config: tests are marked by the directory they live in."""

from pathlib import Path

import pytest

_MARKERS_BY_DIR = {"unit": pytest.mark.unit, "integration": pytest.mark.integration}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        parent = Path(str(item.fspath)).parent.name
        marker = _MARKERS_BY_DIR.get(parent)
        if marker is not None:
            item.add_marker(marker)

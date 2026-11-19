"""Committed OpenAPI spec: current, versioned, covers every client call (#26)."""

import importlib.util
import re
import sys
import tomllib
from pathlib import Path

import pytest

from app import __version__

BACKEND = Path(__file__).parents[2]
REPO = BACKEND.parent
spec_module = importlib.util.spec_from_file_location(
    "openapi_script", BACKEND / "scripts" / "openapi.py"
)
assert spec_module and spec_module.loader
openapi = importlib.util.module_from_spec(spec_module)
spec_module.loader.exec_module(openapi)


def _spec_paths() -> list[str]:
    import json

    return list(json.loads(openapi.SPEC_PATH.read_text(encoding="utf-8"))["paths"])


def _matches(path: str, templates: list[str]) -> bool:
    return any(re.fullmatch(re.sub(r"\{[^}]+\}", "[^/]+", t), path) for t in templates)


def test_committed_spec_matches_the_code() -> None:
    assert openapi.main(["openapi.py", "check"]) == 0, "run `make openapi`"


def test_one_version_everywhere() -> None:
    pyproject = tomllib.loads((BACKEND / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["version"] == __version__
    assert openapi.generate()["info"]["version"] == __version__


def test_streamlit_client_only_calls_paths_in_the_spec() -> None:
    sys.path.insert(0, str(REPO / "frontend"))
    import api_client

    for path in (api_client.UPLOAD_PATH, api_client.ANALYZE_PATH):
        assert _matches(path, _spec_paths()), path


def test_next_client_only_calls_paths_in_the_spec() -> None:
    sources = [
        p
        for d in ("app", "components", "lib")
        for p in (REPO / "frontend-next" / d).rglob("*.ts*")
    ]
    calls = {
        re.sub(r"\$\{[^}]+\}", "1", m)
        for src in sources
        for m in re.findall(r"/api/v1/[A-Za-z0-9_/${}.-]*", src.read_text("utf-8"))
    }
    assert calls, "expected the Next.js client to call the API"
    for call in sorted(calls):
        assert _matches(call, _spec_paths()), call


@pytest.mark.parametrize(
    ("base_version", "change_contract", "expected"),
    [(__version__, False, 0), (__version__, True, 1), ("0.0.1", True, 0)],
)
def test_contract_changes_require_a_version_bump(
    tmp_path: Path, base_version: str, change_contract: bool, expected: int
) -> None:
    import json

    base = json.loads(openapi.SPEC_PATH.read_text(encoding="utf-8"))
    base["info"]["version"] = base_version
    if change_contract:
        base["paths"]["/api/v1/removed"] = {}
    base_file = tmp_path / "base.json"
    base_file.write_text(json.dumps(base), encoding="utf-8")

    assert openapi.main(["openapi.py", "check-version", str(base_file)]) == expected

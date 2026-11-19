"""Export or check the committed OpenAPI contract (backend/openapi.json).

python scripts/openapi.py export            # write openapi.json from the app
python scripts/openapi.py check             # fail if openapi.json is stale
python scripts/openapi.py check-version BASE.json
    # fail if the contract differs from BASE (e.g. main's) without an
    # info.version change
"""

import json
import sys
from pathlib import Path
from typing import Any

SPEC_PATH = Path(__file__).resolve().parents[1] / "openapi.json"


def generate() -> dict[str, Any]:
    sys.path.insert(0, str(SPEC_PATH.parent))  # make `app` importable
    from app.main import app

    spec: dict[str, Any] = app.openapi()
    return spec


def dump(spec: dict[str, Any]) -> str:
    return json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _contract(spec: dict[str, Any]) -> dict[str, Any]:
    """The spec without info.version, i.e. what clients actually depend on."""
    stripped = json.loads(json.dumps(spec))
    stripped.get("info", {}).pop("version", None)
    return stripped  # type: ignore[no-any-return]


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else ""
    if command == "export":
        SPEC_PATH.write_text(dump(generate()), encoding="utf-8")
        print(f"wrote {SPEC_PATH.name}")
        return 0
    if command == "check":
        committed = SPEC_PATH.read_text(encoding="utf-8") if SPEC_PATH.exists() else ""
        if committed != dump(generate()):
            print("openapi.json is out of date with the code; run `make openapi`.")
            return 1
        print("openapi.json matches the code.")
        return 0
    if command == "check-version" and len(argv) == 3:
        base = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
        head = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
        changed = _contract(base) != _contract(head)
        bumped = base["info"]["version"] != head["info"]["version"]
        if changed and not bumped:
            print(
                "The API contract changed but info.version is still "
                f"{head['info']['version']}. Bump app/__init__.py __version__."
            )
            return 1
        print(
            f"contract changed={changed}, version {base['info']['version']} -> "
            f"{head['info']['version']}"
        )
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))

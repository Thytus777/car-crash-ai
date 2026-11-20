"""Write shields.io endpoint badges (https://shields.io/badges/endpoint-badge).

python scripts/badge.py coverage 89.81 --out coverage.json
python scripts/badge.py eval evals/results/<run>.json --out eval.json
python scripts/badge.py eval none --out eval.json        # no run (no dataset yet)

The JSON is published to the `badges` branch by CI; the README points
shields.io at the raw files. Every number comes from a real run.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals import results  # noqa: E402


def _colour(value: float, good: float, ok: float) -> str:
    if value >= good:
        return "brightgreen"
    return "yellow" if value >= ok else "red"


def coverage_badge(percent: float) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "label": "coverage",
        "message": f"{percent:.0f}%",
        "color": _colour(percent, 85, 75),
    }


def eval_badge(run: results.EvalRun | None) -> dict[str, Any]:
    f1 = run.metrics.detection.overall.f1 if run else None
    if run is None or f1 is None:
        return {
            "schemaVersion": 1,
            "label": "eval",
            "message": "no labelled data yet",
            "color": "lightgrey",
        }
    return {
        "schemaVersion": 1,
        "label": f"eval ({run.run.subset}, n={run.run.dataset.cases_run})",
        "message": f"component F1 {f1:.2f}",
        "color": _colour(f1, 0.8, 0.6),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=["coverage", "eval"])
    parser.add_argument("value", help="coverage percent, or a result file / 'none'")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.kind == "coverage":
        badge = coverage_badge(float(args.value))
    else:
        run = None if args.value == "none" else results.load_run(Path(args.value))
        badge = eval_badge(run)
    args.out.write_text(json.dumps(badge), encoding="utf-8")
    print(json.dumps(badge))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""README badges are computed from real runs, and say so when there's none."""

import importlib.util
import json
from pathlib import Path

from evals.pricing import Pricing

from evals import metrics, results

spec = importlib.util.spec_from_file_location(
    "badge", Path(__file__).parents[2] / "scripts" / "badge.py"
)
assert spec and spec.loader
badge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(badge)


def test_coverage_badge_rounds_and_colours() -> None:
    assert badge.coverage_badge(89.81)["message"] == "90%"
    assert badge.coverage_badge(89.81)["color"] == "brightgreen"
    assert badge.coverage_badge(70)["color"] == "red"


def test_eval_badge_without_a_run_says_there_is_no_data() -> None:
    b = badge.eval_badge(None)

    assert b["message"] == "no labelled data yet" and b["color"] == "lightgrey"


def test_eval_badge_reports_f1_with_subset_and_case_count() -> None:
    run = results.EvalRun.model_construct(
        run=results.RunInfo.model_construct(
            subset="full",
            dataset=results.DatasetInfo.model_construct(cases_run=40),
        ),
        metrics=metrics.compute([], Pricing()),
        cases=[],
    )
    run.metrics.detection.overall.f1 = 0.74

    b = badge.eval_badge(run)

    assert b["label"] == "eval (full, n=40)"
    assert b["message"] == "component F1 0.74" and b["color"] == "yellow"


def test_cli_writes_endpoint_json(tmp_path: Path) -> None:
    out = tmp_path / "coverage.json"

    assert badge.main(["coverage", "86.2", "--out", str(out)]) == 0

    assert json.loads(out.read_text())["schemaVersion"] == 1

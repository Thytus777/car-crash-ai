"""End-to-end eval run on a synthetic dataset with a fake model (#15).

No network, no real labels: the fake answers by schema, and the dataset is
built in tmp_path.
"""

import hashlib
import json
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path

import pytest
from evals.__main__ import main as cli
from evals.pricing import Pricing
from PIL import Image
from pydantic import SecretStr

import app.core.llm as llm
from app.core.config import settings
from app.core.llm import CompletionCache
from app.models.llm_outputs import (
    VehicleIdentification,
)
from evals import dataset, metrics, results, runner
from tests.llm_fakes import FAKE_REPLIES, SchemaClient

pytestmark = pytest.mark.real_triage


def _jpeg(colour: str) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (800, 600), color=colour).save(buf, format="JPEG")
    return buf.getvalue()


def _write_case(
    root: Path, case_id: str, colour: str, label: dict[str, object]
) -> None:
    data = _jpeg(colour)
    images = root / case_id / "images"
    images.mkdir(parents=True)
    (images / "a.jpg").write_bytes(data)
    body = {
        "case_id": case_id,
        "images": [
            {
                "file": "a.jpg",
                "sha256": hashlib.sha256(data).hexdigest(),
                "source": "synthetic",
                "licence": "own",
                "redistributable": True,
            }
        ],
        "labeller": "test",
        "labelled_on": "2026-11-19",
        **label,
    }
    (root / case_id / "label.json").write_text(json.dumps(body))


@pytest.fixture
def synthetic_dataset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "dataset"
    root.mkdir()
    (root / "manifest.json").write_text(
        json.dumps({"version": "0.1.0", "smoke": ["car-01"]})
    )
    _write_case(
        root,
        "car-01",
        "red",
        {
            "triage": {"shows_vehicle": True, "usable": True},
            "vehicle": {"make": "Toyota", "model": "Camry", "year": 2020},
            "damages": [
                {"component": "hood", "severity": "moderate"},
                {"component": "grille", "severity": "minor"},
            ],
        },
    )
    _write_case(
        root,
        "not-a-car-01",
        "grey",
        {
            "triage": {"shows_vehicle": False, "usable": False},
            "damages": [],
            "tags": ["non_vehicle"],
        },
    )
    monkeypatch.setattr(dataset, "DATASET_ROOT", root)
    monkeypatch.setattr(dataset, "LOCAL_IMAGES_ROOT", tmp_path / "local")
    return root


@pytest.fixture
def fake_model(monkeypatch: pytest.MonkeyPatch) -> Iterator[SchemaClient]:
    client = SchemaClient()
    monkeypatch.setattr(settings, "openai_api_key", SecretStr(""))
    monkeypatch.setattr(llm, "get_client", lambda _p: client)
    yield client


async def test_run_scores_cases_end_to_end(
    synthetic_dataset: Path, fake_model: SchemaClient
) -> None:
    cases = dataset.load_cases(synthetic_dataset, dataset.LOCAL_IMAGES_ROOT)

    case_results = {r.case_id: r for r in await runner.run(cases, concurrency=2)}

    car, cat = case_results["car-01"], case_results["not-a-car-01"]
    assert car.status == "assessed" and car.triage == "accepted"
    assert car.predicted_damages == {"hood": 0.5}
    assert car.predicted_vehicle is not None and car.predicted_vehicle.make == "Toyota"
    assert {c.task for c in car.calls} >= {"image_triage", "vehicle_id", "damage_front"}
    assert cat.status == "rejected" and cat.triage == "not_a_vehicle"
    assert [c.task for c in cat.calls] == ["image_triage"]

    m = metrics.compute(list(case_results.values()), Pricing())
    assert m.detection.overall.precision == 1.0 and m.detection.overall.recall == 0.5
    assert m.severity.exact == 1.0  # 0.5 -> moderate
    assert m.triage.accuracy == 1.0
    assert m.vehicle.make_model_accuracy == 1.0
    assert m.spend.per_request_usd is None  # fake model isn't priced


async def test_cached_rerun_makes_no_model_calls(
    synthetic_dataset: Path, fake_model: SchemaClient, tmp_path: Path
) -> None:
    cases = dataset.load_cases(synthetic_dataset, dataset.LOCAL_IMAGES_ROOT)
    cache = CompletionCache(tmp_path / "cache")

    with llm.use_completion_cache(cache):
        first = await runner.run(cases)
    live_requests = fake_model.requests
    with llm.use_completion_cache(cache):
        second = await runner.run(cases)

    assert fake_model.requests == live_requests  # nothing new sent
    assert all(c.cached for r in second for c in r.calls)
    assert [r.predicted_damages for r in first] == [r.predicted_damages for r in second]


def test_cli_run_writes_results_and_compare_gates(
    synthetic_dataset: Path,
    fake_model: SchemaClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out = tmp_path / "results"
    monkeypatch.setattr("evals.__main__.CACHE_ROOT", tmp_path / "cache")

    assert cli(["run", "--smoke", "--output-dir", str(out)]) == 0

    (written,) = out.glob("*.json")
    run = results.load_run(written)
    assert run.run.subset == "smoke" and run.run.dataset.cases_run == 1
    assert run.run.dataset.version == "0.1.0"
    assert run.run.models == ["gemini/fake-model"]
    assert "| Component F1 |" in written.with_suffix(".md").read_text("utf-8")

    worse = run.model_copy(deep=True)
    worse.metrics.detection.overall.f1 = 0.1
    worse_path = tmp_path / "worse.json"
    worse_path.write_text(worse.model_dump_json())
    assert cli(["compare", str(written), str(written)]) == 0
    assert cli(["compare", str(written), str(worse_path)]) == 1


async def test_low_confidence_id_is_confirmed_with_the_labelled_vehicle(
    synthetic_dataset: Path, fake_model: SchemaClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    unsure = json.loads(FAKE_REPLIES[VehicleIdentification]) | {
        "make": "Lexus",
        "model": "ES",
        "confidence": 0.3,
    }
    monkeypatch.setitem(FAKE_REPLIES, VehicleIdentification, json.dumps(unsure))
    cases = dataset.load_cases(synthetic_dataset, dataset.LOCAL_IMAGES_ROOT)

    car = next(r for r in await runner.run(cases) if r.case_id == "car-01")

    assert car.needed_confirmation and car.status == "assessed"
    assert car.predicted_vehicle is not None and car.predicted_vehicle.make == "Lexus"
    assert car.predicted_damages == {"hood": 0.5}  # ran on with the label's vehicle
    assert metrics.vehicle([car]).make_model_accuracy == 0.0


async def test_runs_bypass_the_result_cache(
    synthetic_dataset: Path,
    fake_model: SchemaClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "result_cache_enabled", True)
    monkeypatch.setattr(settings, "result_cache_dir", tmp_path / "results-cache")
    cases = dataset.load_cases(synthetic_dataset, dataset.LOCAL_IMAGES_ROOT)

    await runner.run(cases)
    calls_first = fake_model.requests
    await runner.run(cases)

    assert fake_model.requests == 2 * calls_first  # second run called the model again
    assert settings.result_cache_enabled is True  # restored afterwards


# --- CI eval gate (python -m evals gate) ----------------------------------


@pytest.fixture
def gate_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    monkeypatch.setattr("evals.__main__.CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr("test-key"))
    return {
        "baseline": tmp_path / "baseline.json",
        "comment": tmp_path / "comment.md",
        "out": tmp_path / "results",
    }


def _gate(paths: dict[str, Path]) -> int:
    return cli(
        [
            "gate",
            "--baseline",
            str(paths["baseline"]),
            "--comment",
            str(paths["comment"]),
            "--output-dir",
            str(paths["out"]),
        ]
    )


def test_gate_skips_without_a_model_key(
    synthetic_dataset: Path,
    fake_model: SchemaClient,
    gate_paths: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr(""))

    assert _gate(gate_paths) == 0

    comment = gate_paths["comment"].read_text("utf-8")
    assert "<!-- eval-gate -->" in comment and "Skipped" in comment
    assert "no model API key" in comment
    assert fake_model.requests == 0


def test_gate_skips_without_runnable_smoke_cases(
    synthetic_dataset: Path, fake_model: SchemaClient, gate_paths: dict[str, Path]
) -> None:
    (synthetic_dataset / "manifest.json").write_text(
        json.dumps({"version": "0.1.0", "smoke": []})
    )

    assert _gate(gate_paths) == 0

    comment = gate_paths["comment"].read_text("utf-8")
    assert "Skipped" in comment and "no runnable smoke cases" in comment
    assert fake_model.requests == 0


def test_gate_without_a_baseline_reports_the_run_and_passes(
    synthetic_dataset: Path, fake_model: SchemaClient, gate_paths: dict[str, Path]
) -> None:
    assert _gate(gate_paths) == 0

    comment = gate_paths["comment"].read_text("utf-8")
    assert "No baseline" in comment and "| Component F1 |" in comment
    assert not gate_paths["baseline"].exists()  # never adopted silently


def test_gate_passes_against_an_equal_baseline_and_fails_on_regression(
    synthetic_dataset: Path, fake_model: SchemaClient, gate_paths: dict[str, Path]
) -> None:
    assert _gate(gate_paths) == 0
    (first,) = gate_paths["out"].glob("*.json")
    run = results.load_run(first)
    gate_paths["baseline"].write_text(run.model_dump_json())
    first.unlink()

    assert _gate(gate_paths) == 0
    assert "Passed" in gate_paths["comment"].read_text("utf-8")

    better = run.model_copy(deep=True)
    better.metrics.detection.overall.f1 = 1.0
    gate_paths["baseline"].write_text(better.model_dump_json())

    assert _gate(gate_paths) == 1
    comment = gate_paths["comment"].read_text("utf-8")
    assert "Regressed" in comment and "Component F1" in comment

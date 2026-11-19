"""End-to-end eval run on a synthetic dataset with a fake model (#15).

No network, no real labels: the fake answers by schema, and the dataset is
built in tmp_path.
"""

import hashlib
import json
from collections.abc import Iterator, Sequence
from io import BytesIO
from pathlib import Path

import pytest
from evals.__main__ import main as cli
from evals.pricing import Pricing
from PIL import Image
from pydantic import BaseModel, SecretStr

import app.core.llm as llm
from app.core.config import settings
from app.core.llm import Completion, CompletionCache, ImageDetail, Usage
from app.models.llm_outputs import (
    DamageFindings,
    ImageTriage,
    PriceEstimate,
    SanityReview,
    VehicleIdentification,
)
from evals import dataset, metrics, results, runner

pytestmark = pytest.mark.real_triage

FAKE_REPLIES: dict[type[BaseModel], str] = {
    VehicleIdentification: json.dumps(
        {
            "make": "Toyota",
            "model": "Camry",
            "year": 2020,
            "body_style": "sedan",
            "color": "grey",
            "confidence": 0.95,
        }
    ),
    SanityReview: json.dumps({"looks_reasonable": True, "warnings": []}),
    PriceEstimate: json.dumps(
        {"price_low": 100, "price_avg": 200, "price_high": 300, "confidence": 0.5}
    ),
}


class SchemaClient:
    """Fake provider: a fixed reply per schema; triage rejects grey-on-grey."""

    provider = "gemini"

    def __init__(self) -> None:
        self.requests = 0

    def model_for(self, *, vision: bool) -> str:
        return "fake-model"

    async def complete(
        self,
        *,
        schema: type[BaseModel],
        prompt: str,
        images: Sequence[bytes],
        max_output_tokens: int,
        temperature: float,
        image_detail: ImageDetail,
    ) -> Completion:
        self.requests += 1
        if schema is ImageTriage:
            is_car = all(_is_red(i) for i in images)
            text = json.dumps(
                {"shows_vehicle": is_car, "usable": is_car, "reason": "synthetic"}
            )
        elif schema is DamageFindings:
            damages = (
                [
                    {
                        "component": "hood",
                        "damage_type": "dent",
                        "severity": 0.5,
                        "description": "synthetic",
                    }
                ]
                if "FRONT ZONE" in prompt
                else []
            )
            text = json.dumps({"damages": damages})
        else:
            text = FAKE_REPLIES[schema]
        return Completion(text=text, usage=Usage(500, 50), model="fake-model")


def _is_red(jpeg: bytes) -> bool:
    r, g, _ = Image.open(BytesIO(jpeg)).convert("RGB").getpixel((10, 10))  # type: ignore[misc]
    return bool(r > 150 and g < 100)


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

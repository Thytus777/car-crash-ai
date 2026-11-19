"""Dataset format and validator (#15). Synthetic fixtures only; not eval data."""

import hashlib
import json
from io import BytesIO
from pathlib import Path
from typing import Any, get_args

import pytest
import yaml
from evals.schema import CaseLabel, Tag, severity_level
from PIL import Image
from pydantic import ValidationError

from app.models.damage import STANDARD_COMPONENTS, DamageType
from evals import dataset

TAXONOMY = dataset.EVALS_ROOT / "taxonomy.yaml"


def _jpeg(size: tuple[int, int] = (800, 600)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, color="grey").save(buf, format="JPEG")
    return buf.getvalue()


def _label(
    case_id: str, images: list[dict[str, Any]], **overrides: Any
) -> dict[str, Any]:
    label: dict[str, Any] = {
        "case_id": case_id,
        "images": images,
        "triage": {"shows_vehicle": True, "usable": True},
        "damages": [{"component": "hood", "severity": "moderate"}],
        "labeller": "test",
        "labelled_on": "2026-11-19",
    }
    label.update(overrides)
    return label


def _image_ref(name: str, data: bytes, redistributable: bool = True) -> dict[str, Any]:
    return {
        "file": name,
        "sha256": hashlib.sha256(data).hexdigest(),
        "source": "synthetic test fixture",
        "licence": "own" if redistributable else "unknown",
        "redistributable": redistributable,
    }


class Fixture:
    def __init__(self, tmp_path: Path) -> None:
        self.root = tmp_path / "dataset"
        self.local = tmp_path / "local_images"
        self.root.mkdir()
        self.manifest()

    def manifest(self, smoke: list[str] | None = None) -> None:
        manifest = {"version": "0.1.0", "smoke": smoke or []}
        (self.root / "manifest.json").write_text(json.dumps(manifest))

    def case(
        self,
        case_id: str,
        committed: dict[str, bytes] | None = None,
        local: dict[str, bytes] | None = None,
        label: dict[str, Any] | None = None,
    ) -> Path:
        directory = self.root / case_id
        (directory / "images").mkdir(parents=True)
        refs = []
        for name, data in (committed or {}).items():
            (directory / "images" / name).write_bytes(data)
            refs.append(_image_ref(name, data))
        for name, data in (local or {}).items():
            (self.local / case_id).mkdir(parents=True, exist_ok=True)
            (self.local / case_id / name).write_bytes(data)
            refs.append(_image_ref(name, data, redistributable=False))
        body = label or _label(case_id, refs)
        (directory / "label.json").write_text(json.dumps(body))
        return directory

    def validate(self) -> dataset.ValidationReport:
        return dataset.validate(self.root, self.local)


@pytest.fixture
def fx(tmp_path: Path) -> Fixture:
    return Fixture(tmp_path)


def test_a_well_formed_dataset_validates(fx: Fixture) -> None:
    fx.case("front-01", committed={"a.jpg": _jpeg()}, local={"b.jpg": _jpeg()})

    report = fx.validate()

    assert report.ok, report.errors
    assert [c.available() for c in dataset.load_cases(fx.root, fx.local)] == [True]


def test_hash_mismatch_is_an_error(fx: Fixture) -> None:
    d = fx.case("front-01", committed={"a.jpg": _jpeg()})
    (d / "images" / "a.jpg").write_bytes(_jpeg((801, 600)))

    assert any("sha256 mismatch" in e for e in fx.validate().errors)


def test_oversized_committed_images_are_errors(fx: Fixture) -> None:
    fx.case("big-01", committed={"a.jpg": _jpeg((2400, 1600))})

    assert any("long edge must be <= 1600px" in e for e in fx.validate().errors)


def test_non_redistributable_image_must_not_be_committed(fx: Fixture) -> None:
    data = _jpeg()
    d = fx.case("scraped-01", local={"a.jpg": data})
    (d / "images" / "a.jpg").write_bytes(data)

    assert any("not a redistributable image" in e for e in fx.validate().errors)


def test_missing_local_image_is_only_a_warning(fx: Fixture) -> None:
    fx.case("scraped-01", local={"a.jpg": _jpeg()})
    (fx.local / "scraped-01" / "a.jpg").unlink()

    report = fx.validate()

    assert report.ok
    assert any("not present locally" in w for w in report.warnings)


def test_smoke_cases_must_be_redistributable_and_exist(fx: Fixture) -> None:
    fx.case("scraped-01", local={"a.jpg": _jpeg()})
    fx.manifest(smoke=["scraped-01", "ghost"])

    errors = fx.validate().errors

    assert any("scraped-01 has non-redistributable" in e for e in errors)
    assert any("unknown case 'ghost'" in e for e in errors)


def test_folder_name_must_match_case_id(fx: Fixture) -> None:
    data = _jpeg()
    fx.case("front-01", label=_label("other-id", [_image_ref("a.jpg", data)]))
    (fx.root / "front-01" / "images" / "a.jpg").write_bytes(data)

    assert any("!= folder name" in e for e in fx.validate().errors)


NOT_ASSESSABLE = {"shows_vehicle": False, "usable": False}
BAD_COST = {
    "currency": "AUD",
    "low": "900.00",
    "high": "500.00",
    "basis": "repair_quote",
}


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"damages": [], "tags": []}, "tag 'undamaged'"),
        ({"tags": ["undamaged"]}, "tag 'undamaged'"),
        ({"triage": NOT_ASSESSABLE, "tags": ["non_vehicle"]}, "carry no damages"),
        ({"damages": [{"component": "hood", "severity": "minor"}] * 2}, "at most once"),
        ({"cost": BAD_COST}, "cost.low must be <= cost.high"),
        (
            {"damages": [{"component": "flux_capacitor", "severity": "minor"}]},
            "component",
        ),
    ],
)
def test_label_consistency_rules(overrides: dict[str, Any], message: str) -> None:
    ref = _image_ref("a.jpg", b"x")
    with pytest.raises(ValidationError, match=message):
        CaseLabel.model_validate(_label("case-01", [ref], **overrides))


@pytest.mark.parametrize(
    ("score", "level"),
    [
        (0.0, "cosmetic"),
        (0.1, "cosmetic"),
        (0.11, "minor"),
        (0.45, "moderate"),
        (0.6, "moderate"),
        (0.75, "severe"),
        (0.95, "destroyed"),
        (1.0, "destroyed"),
    ],
)
def test_model_scores_map_onto_label_levels(score: float, level: str) -> None:
    assert severity_level(score) == level


def test_taxonomy_file_matches_the_code() -> None:
    taxonomy = yaml.safe_load(TAXONOMY.read_text(encoding="utf-8"))

    assert [c["name"] for c in taxonomy["components"]] == STANDARD_COMPONENTS
    assert taxonomy["damage_types"] == list(get_args(DamageType))
    assert taxonomy["tags"] == list(get_args(Tag))


def test_the_committed_dataset_is_valid() -> None:
    assert dataset.validate().ok

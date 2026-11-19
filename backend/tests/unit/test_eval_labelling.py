"""Labelling-tool image preparation and saving (#15). Synthetic images only."""

import datetime as dt
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from evals.labelling import PreparedImage, blur_regions, prepare_image, save_case
from evals.schema import CaseLabel, ExpectedTriage, ImageRef, LabelledDamage
from PIL import Image

from evals import dataset, labelling


def _encode(img: Image.Image, **save: object) -> bytes:
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=95, **save)
    return buf.getvalue()


def _noise(width: int, height: int) -> Image.Image:
    rng = np.random.default_rng(0)
    return Image.fromarray(rng.integers(0, 256, (height, width, 3), dtype=np.uint8))


def _checkerboard(size: int = 400, cell: int = 4) -> Image.Image:
    grid = (np.indices((size, size)).sum(axis=0) // cell % 2 * 255).astype(np.uint8)
    return Image.fromarray(np.stack([grid] * 3, axis=-1))


def test_large_photos_are_resized_and_compressed_under_the_limits() -> None:
    prepared = prepare_image(_encode(_noise(3000, 2000)))

    assert max(prepared.size) == dataset.MAX_EDGE_PX
    assert len(prepared.jpeg) <= dataset.MAX_BYTES
    assert Image.open(BytesIO(prepared.jpeg)).format == "JPEG"


def test_exif_rotation_is_applied() -> None:
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90° clockwise on display
    prepared = prepare_image(_encode(_noise(800, 600), exif=exif))

    assert prepared.size == (600, 800)


def test_blur_destroys_detail_inside_the_box_only() -> None:
    img = _checkerboard()
    blurred = np.asarray(blur_regions(img, [(100, 100, 100, 100)], pad=0)).astype(float)

    inside = blurred[110:190, 110:190].std()
    outside = blurred[300:380, 300:380].std()
    assert inside < outside / 10


def test_detected_and_manual_regions_are_both_blurred(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        labelling,
        "detect_sensitive_regions",
        lambda _img: {"face": [(10, 10, 50, 50)], "plate": []},
    )

    prepared = prepare_image(_encode(_checkerboard()), extra_boxes=[(200, 200, 80, 40)])

    assert prepared.blurred == [(10, 10, 50, 50), (200, 200, 80, 40)]
    assert prepared.detected["face"] == [(10, 10, 50, 50)]


def test_detection_runs_on_a_real_image_without_error() -> None:
    found = labelling.detect_sensitive_regions(_noise(640, 480))

    assert set(found) == {"face", "plate"}


def _label(case_id: str, images: dict[str, tuple[PreparedImage, bool]]) -> CaseLabel:
    return CaseLabel(
        case_id=case_id,
        images=[
            ImageRef(
                file=name,
                sha256=prepared.sha256,
                source="synthetic test fixture",
                licence="own" if redistributable else "unknown",
                redistributable=redistributable,
            )
            for name, (prepared, redistributable) in images.items()
        ],
        triage=ExpectedTriage(shows_vehicle=True, usable=True),
        damages=[LabelledDamage(component="hood", severity="minor")],
        labeller="test",
        labelled_on=dt.date(2026, 11, 19),
    )


def test_saved_cases_pass_validation_with_images_stored_by_licence(
    tmp_path: Path,
) -> None:
    root, local = tmp_path / "dataset", tmp_path / "local"
    root.mkdir()
    (root / "manifest.json").write_text('{"version": "0.1.0", "smoke": []}')
    own, scraped = (
        prepare_image(_encode(_noise(800, 600))),
        prepare_image(_encode(_checkerboard())),
    )
    label = _label("hood-01", {"own.jpg": (own, True), "web.jpg": (scraped, False)})

    save_case(
        label,
        {"own.jpg": own.jpeg, "web.jpg": scraped.jpeg},
        root=root,
        local_root=local,
    )

    assert (root / "hood-01" / "images" / "own.jpg").is_file()
    assert not (root / "hood-01" / "images" / "web.jpg").exists()
    assert (local / "hood-01" / "web.jpg").is_file()
    report = dataset.validate(root, local)
    assert report.ok and not report.warnings, (report.errors, report.warnings)


def test_save_refuses_mismatched_images_and_existing_cases(tmp_path: Path) -> None:
    prepared = prepare_image(_encode(_noise(800, 600)))
    label = _label("hood-01", {"a.jpg": (prepared, True)})

    with pytest.raises(ValueError, match="sha256"):
        save_case(label, {"a.jpg": b"other"}, root=tmp_path, local_root=tmp_path)
    save_case(label, {"a.jpg": prepared.jpeg}, root=tmp_path, local_root=tmp_path)
    with pytest.raises(FileExistsError):
        save_case(label, {"a.jpg": prepared.jpeg}, root=tmp_path, local_root=tmp_path)

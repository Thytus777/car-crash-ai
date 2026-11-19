"""Face and number-plate redaction (#10)."""

import os
import time
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.core.config import settings
from app.core.errors import RedactionUnavailableError
from app.services import redaction
from app.services.image_proc import purge_expired_uploads
from app.services.redaction import blur, get_redactor, redact

REPO = Path(__file__).parents[3]
MODELS = Path(settings.redaction_models_dir)
models_installed = pytest.mark.skipif(
    not (MODELS / redaction.PLATE_MODEL).is_file(),
    reason="redaction models not installed (make models)",
)


@pytest.fixture(autouse=True)
def fresh_redactor() -> Iterator[None]:
    get_redactor.cache_clear()
    yield
    get_redactor.cache_clear()


def _checkerboard() -> Image.Image:
    grid = (np.indices((300, 300)).sum(axis=0) // 3 % 2 * 255).astype(np.uint8)
    return Image.fromarray(np.stack([grid] * 3, axis=-1))


def test_blur_destroys_detail_inside_boxes_only() -> None:
    img = _checkerboard()
    out = np.asarray(blur(img, [(100, 100, 60, 40)], pad=0)).astype(float)

    assert out[105:135, 105:155].std() < np.asarray(img).astype(float).std() / 10
    assert np.array_equal(out[200:, 200:], np.asarray(img)[200:, 200:])


def test_missing_models_refuse_uploads_when_required(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(settings, "redaction_models_dir", tmp_path)
    monkeypatch.setattr(settings, "redaction_required", True)

    with pytest.raises(RedactionUnavailableError) as exc_info:
        redact(_checkerboard())
    assert exc_info.value.status == 503


def test_missing_models_pass_images_through_when_optional(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(settings, "redaction_models_dir", tmp_path)
    monkeypatch.setattr(settings, "redaction_required", False)
    img = _checkerboard()

    result = redact(img)

    assert result.image is img and result.regions == 0


@models_installed
def test_real_models_find_the_plate_in_a_committed_photo() -> None:
    redactor = get_redactor()
    assert redactor is not None
    img = Image.open(REPO / "test_images" / "holden.webp").convert("RGB")

    plates, faces = redactor.detect(img)

    assert len(plates) >= 1
    for x, y, w, h in plates:
        assert 0 <= x and 0 <= y and x + w <= img.width and y + h <= img.height


@models_installed
def test_real_models_find_nothing_in_a_blank_image() -> None:
    redactor = get_redactor()
    assert redactor is not None

    assert redactor.detect(Image.new("RGB", (640, 480), "grey")) == ([], [])


def test_expired_uploads_are_purged_and_others_kept(
    isolated_upload_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "upload_retention_hours", 24)
    old, new, other = (
        isolated_upload_dir / "0123456789ab",
        isolated_upload_dir / "fedcba987654",
        isolated_upload_dir / "not-an-upload",
    )
    for folder in (old, new, other):
        folder.mkdir(parents=True)
    two_days_ago = time.time() - 48 * 3600
    os.utime(old, (two_days_ago, two_days_ago))
    os.utime(other, (two_days_ago, two_days_ago))

    assert purge_expired_uploads() == 1
    assert not old.exists() and new.exists() and other.exists()

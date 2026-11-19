"""Image preprocessing for model input (#50). Synthetic images."""

from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.core.config import settings
from app.services.image_proc import load_images, prepare_for_model, process_upload


def _noise_jpeg(width: int, height: int) -> bytes:
    rng = np.random.default_rng(1)
    pixels = rng.integers(0, 256, (height, width, 3), dtype=np.uint8)
    buf = BytesIO()
    Image.fromarray(pixels).save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def _size(jpeg: bytes) -> tuple[int, int]:
    return Image.open(BytesIO(jpeg)).size


async def test_uploads_are_stored_at_up_to_the_storage_edge(
    isolated_upload_dir: Path,
) -> None:
    upload_id, processed, _ = await process_upload(
        [("a.jpg", _noise_jpeg(3000, 2000), "")]
    )

    assert (
        max(processed[0].width, processed[0].height) == settings.stored_image_max_edge
    )


async def test_model_input_defaults_to_1024px(isolated_upload_dir: Path) -> None:
    upload_id, _, _ = await process_upload([("a.jpg", _noise_jpeg(3000, 2000), "")])

    (sent,) = load_images(upload_id)

    assert max(_size(sent)) == 1024


@pytest.mark.parametrize("edge", [512, 768])
async def test_model_input_edge_is_configurable(
    isolated_upload_dir: Path, monkeypatch: pytest.MonkeyPatch, edge: int
) -> None:
    upload_id, _, _ = await process_upload([("a.jpg", _noise_jpeg(3000, 2000), "")])
    monkeypatch.setattr(settings, "model_image_max_edge", edge)

    (sent,) = load_images(upload_id)

    assert max(_size(sent)) == edge


def test_small_images_at_the_stored_quality_pass_through_unchanged() -> None:
    small = _noise_jpeg(800, 600)

    assert prepare_for_model(small, max_edge=1024, quality=None) is small


def test_lower_quality_means_fewer_bytes() -> None:
    image = _noise_jpeg(1600, 1200)

    high = prepare_for_model(image, max_edge=1024, quality=90)
    low = prepare_for_model(image, max_edge=1024, quality=60)

    assert _size(high) == _size(low) == (1024, 768)
    assert len(low) < len(high)

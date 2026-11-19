"""Uploads are redacted before storage (#10)."""

from collections.abc import Iterator
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from httpx import AsyncClient
from PIL import Image

from app.core.config import settings
from app.services import redaction
from app.services.redaction import RedactionResult, blur

pytestmark = pytest.mark.real_redaction

PLATE, FACE = (100, 300, 120, 40), (500, 100, 60, 60)


class FakeRedactor:
    def redact(self, img: Image.Image) -> RedactionResult:
        return RedactionResult(blur(img, [PLATE, FACE]), [PLATE], [FACE])


@pytest.fixture
def fake_redactor(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(redaction, "get_redactor", lambda: FakeRedactor())
    yield


def _noise_jpeg() -> bytes:
    pixels = np.random.default_rng(0).integers(0, 256, (600, 800, 3), dtype=np.uint8)
    buf = BytesIO()
    Image.fromarray(pixels).save(buf, format="JPEG", quality=95)
    return buf.getvalue()


@pytest.mark.usefixtures("fake_redactor")
async def test_stored_images_are_blurred_where_detected(
    client: AsyncClient, isolated_upload_dir: Path
) -> None:
    response = await client.post(
        "/api/v1/upload", files=[("images", ("car.jpg", _noise_jpeg(), "image/jpeg"))]
    )

    assert response.status_code == 200
    body = response.json()
    assert body["images"][0]["redacted_regions"] == 2
    (stored,) = (isolated_upload_dir / body["upload_id"]).glob("*.jpg")
    pixels = np.asarray(Image.open(stored)).astype(float)
    x, y, w, h = PLATE
    assert pixels[y + 5 : y + h - 5, x + 5 : x + w - 5].std() < pixels.std() / 5


async def test_uploads_are_refused_when_redaction_is_required_but_missing(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(redaction, "get_redactor", lambda: None)
    monkeypatch.setattr(settings, "redaction_required", True)

    response = await client.post(
        "/api/v1/upload", files=[("images", ("car.jpg", _noise_jpeg(), "image/jpeg"))]
    )

    assert response.status_code == 503
    assert response.json()["type"].endswith("#redaction-unavailable")


async def test_readiness_fails_without_required_redaction(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(redaction, "get_redactor", lambda: None)
    monkeypatch.setattr(settings, "redaction_required", True)

    response = await client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["checks"]["redaction"]["ok"] is False

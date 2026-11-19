"""Upload limits and format sniffing (#27)."""

import os
from io import BytesIO

import pytest
from httpx import AsyncClient
from PIL import Image

from app.core.config import settings

PROBLEM_BASE = "https://github.com/Thytus777/car-crash-ai/blob/main/docs/errors.md#"


def _image(fmt: str, size: tuple[int, int] = (800, 600)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, color="blue").save(buf, format=fmt)
    return buf.getvalue()


def _files(*blobs: tuple[str, bytes]) -> list[tuple[str, tuple[str, bytes, str]]]:
    return [("images", (name, data, "image/jpeg")) for name, data in blobs]


async def test_webp_is_accepted(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/upload", files=_files(("car.webp", _image("WEBP")))
    )
    assert response.status_code == 200


@pytest.mark.parametrize("fmt", ["GIF", "BMP", "TIFF"])
async def test_other_image_formats_are_415(client: AsyncClient, fmt: str) -> None:
    # The client claims image/jpeg; the bytes decide.
    response = await client.post(
        "/api/v1/upload", files=_files((f"car.{fmt.lower()}", _image(fmt)))
    )
    assert response.status_code == 415
    assert response.json()["type"] == PROBLEM_BASE + "unsupported-media-type"
    assert "JPEG, PNG or WebP" in response.json()["detail"]


async def test_too_many_images_is_413(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "max_images_per_request", 2)
    jpeg = _image("JPEG")
    response = await client.post(
        "/api/v1/upload",
        files=_files(("a.jpg", jpeg), ("b.jpg", jpeg), ("c.jpg", jpeg)),
    )
    assert response.status_code == 413
    assert response.json()["type"] == PROBLEM_BASE + "payload-too-large"


async def test_oversized_file_is_413(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    jpeg = _image("JPEG")
    monkeypatch.setattr(settings, "max_upload_size_mb", len(jpeg) / 2 / 1024 / 1024)
    response = await client.post("/api/v1/upload", files=_files(("a.jpg", jpeg)))
    assert response.status_code == 413
    assert "a.jpg" in response.json()["detail"]


async def test_total_size_over_limit_is_413(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    jpeg = _image("JPEG")
    monkeypatch.setattr(settings, "max_upload_total_mb", len(jpeg) * 1.5 / 1024 / 1024)
    response = await client.post(
        "/api/v1/upload", files=_files(("a.jpg", jpeg), ("b.jpg", jpeg))
    )
    assert response.status_code == 413
    assert "total" in response.json()["detail"].lower()


async def test_oversized_request_body_is_rejected_before_parsing(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "max_upload_total_mb", 0.5)
    # 2 MB clears the limit plus the 1 MB multipart allowance.
    big = os.urandom(2 * 1024 * 1024)
    response = await client.post("/api/v1/upload", files=_files(("a.jpg", big)))
    assert response.status_code == 413
    assert "request body" in response.json()["detail"]

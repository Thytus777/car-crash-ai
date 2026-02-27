import shutil
from io import BytesIO
from pathlib import Path

import pytest
from httpx import AsyncClient
from PIL import Image

from app.core.config import settings


def _make_test_image(width: int = 800, height: int = 600, fmt: str = "JPEG") -> bytes:
    img = Image.new("RGB", (width, height), color="red")
    buf = BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _clean_uploads():
    """Clean up any uploaded files after each test."""
    yield
    if settings.upload_dir.exists():
        shutil.rmtree(settings.upload_dir)


@pytest.mark.asyncio
async def test_upload_single_image(client: AsyncClient) -> None:
    data = _make_test_image()
    response = await client.post(
        "/api/v1/upload",
        files=[("images", ("test.jpg", data, "image/jpeg"))],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["image_count"] == 1
    assert len(body["images"]) == 1
    assert body["upload_id"]
    assert body["images"][0]["original_filename"] == "test.jpg"


@pytest.mark.asyncio
async def test_upload_multiple_images(client: AsyncClient) -> None:
    files = [
        ("images", (f"img{i}.jpg", _make_test_image(), "image/jpeg"))
        for i in range(3)
    ]
    response = await client.post("/api/v1/upload", files=files)
    assert response.status_code == 200
    assert response.json()["image_count"] == 3


@pytest.mark.asyncio
async def test_upload_no_images(client: AsyncClient) -> None:
    response = await client.post("/api/v1/upload", files=[])
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_upload_image_too_small(client: AsyncClient) -> None:
    data = _make_test_image(width=100, height=100)
    response = await client.post(
        "/api/v1/upload",
        files=[("images", ("tiny.jpg", data, "image/jpeg"))],
    )
    assert response.status_code == 400
    assert "resolution" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_upload_invalid_file(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/upload",
        files=[("images", ("fake.jpg", b"not an image", "image/jpeg"))],
    )
    assert response.status_code == 400
    assert "not a valid image" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_upload_png(client: AsyncClient) -> None:
    data = _make_test_image(fmt="PNG")
    response = await client.post(
        "/api/v1/upload",
        files=[("images", ("test.png", data, "image/png"))],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["image_count"] == 1


@pytest.mark.asyncio
async def test_uploaded_images_saved_to_disk(client: AsyncClient) -> None:
    data = _make_test_image()
    response = await client.post(
        "/api/v1/upload",
        files=[("images", ("test.jpg", data, "image/jpeg"))],
    )
    upload_id = response.json()["upload_id"]
    upload_dir = settings.upload_dir / upload_id
    assert upload_dir.exists()
    saved_files = list(upload_dir.glob("*.jpg"))
    assert len(saved_files) == 1

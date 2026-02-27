"""Image preprocessing service — validates, resizes, and stores uploaded images."""

import base64
import uuid
from io import BytesIO
from pathlib import Path

from PIL import Image

from app.core.config import settings

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/heic", "image/heif"}
TARGET_SIZE = (1024, 1024)


class ImageValidationError(Exception):
    pass


class ProcessedImage:
    def __init__(
        self,
        image_id: str,
        original_filename: str,
        saved_path: Path,
        width: int,
        height: int,
        file_size_bytes: int,
    ) -> None:
        self.image_id = image_id
        self.original_filename = original_filename
        self.saved_path = saved_path
        self.width = width
        self.height = height
        self.file_size_bytes = file_size_bytes


def _validate_image(data: bytes, filename: str) -> Image.Image:
    file_size_mb = len(data) / (1024 * 1024)
    if file_size_mb > settings.max_upload_size_mb:
        raise ImageValidationError(
            f"{filename}: file size {file_size_mb:.1f}MB exceeds "
            f"limit of {settings.max_upload_size_mb}MB"
        )

    try:
        img = Image.open(BytesIO(data))
        img.verify()
        img = Image.open(BytesIO(data))
    except Exception as exc:
        raise ImageValidationError(
            f"{filename}: not a valid image file"
        ) from exc

    width, height = img.size
    if width < settings.min_image_width or height < settings.min_image_height:
        raise ImageValidationError(
            f"{filename}: resolution {width}x{height} is below "
            f"minimum {settings.min_image_width}x{settings.min_image_height}"
        )

    return img


def _resize_image(img: Image.Image) -> Image.Image:
    img.thumbnail(TARGET_SIZE, Image.Resampling.LANCZOS)
    return img


def _ensure_upload_dir(upload_id: str) -> Path:
    upload_dir = settings.upload_dir / upload_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


async def process_upload(
    files: list[tuple[str, bytes, str]],
) -> tuple[str, list[ProcessedImage]]:
    """Process uploaded image files.

    Args:
        files: list of (filename, file_bytes, content_type) tuples.

    Returns:
        (upload_id, list of ProcessedImage).
    """
    if len(files) > settings.max_images_per_request:
        raise ImageValidationError(
            f"Too many images: {len(files)}, max is {settings.max_images_per_request}"
        )

    if not files:
        raise ImageValidationError("No images provided")

    upload_id = uuid.uuid4().hex[:12]
    upload_dir = _ensure_upload_dir(upload_id)
    results: list[ProcessedImage] = []

    for filename, data, content_type in files:
        img = _validate_image(data, filename)

        if img.mode == "RGBA":
            img = img.convert("RGB")

        img = _resize_image(img)

        image_id = uuid.uuid4().hex[:8]
        save_name = f"{image_id}.jpg"
        save_path = upload_dir / save_name
        img.save(save_path, format="JPEG", quality=90)

        results.append(
            ProcessedImage(
                image_id=image_id,
                original_filename=filename,
                saved_path=save_path,
                width=img.size[0],
                height=img.size[1],
                file_size_bytes=save_path.stat().st_size,
            )
        )

    return upload_id, results


def load_images_as_base64(upload_id: str) -> list[str]:
    """Load all processed images for an upload as base64 strings for LLM API."""
    upload_dir = settings.upload_dir / upload_id
    if not upload_dir.exists():
        raise FileNotFoundError(f"Upload {upload_id} not found")

    images_b64: list[str] = []
    for img_path in sorted(upload_dir.glob("*.jpg")):
        with open(img_path, "rb") as f:
            images_b64.append(base64.b64encode(f.read()).decode("utf-8"))

    return images_b64

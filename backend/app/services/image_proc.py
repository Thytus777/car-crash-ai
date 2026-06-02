"""Image preprocessing service — validates, resizes, stores, and quality-checks uploaded images."""

import base64
import statistics
import uuid
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageFilter, ImageStat

from app.core.config import settings
from app.models.damage import AngleGuidance, ImageQualityWarning

# Quality thresholds
_BLUR_THRESHOLD = 80.0       # Laplacian variance below this → blurry
_DARK_THRESHOLD = 50.0       # Mean brightness below this (0–255) → too dark
_OVEREXPOSED_THRESHOLD = 220.0  # Mean brightness above this → overexposed

# Angle labels we ask users to provide (order matters for guidance message)
EXPECTED_ANGLES = ["front", "rear", "driver side", "passenger side"]

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
) -> tuple[str, list[ProcessedImage], list[ImageQualityWarning]]:
    """Process uploaded image files.

    Args:
        files: list of (filename, file_bytes, content_type) tuples.

    Returns:
        (upload_id, list of ProcessedImage, list of ImageQualityWarning).
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
    all_warnings: list[ImageQualityWarning] = []

    for filename, data, content_type in files:
        img = _validate_image(data, filename)
        all_warnings.extend(check_image_quality(img, filename))

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

    return upload_id, results, all_warnings


def check_image_quality(
    img: Image.Image,
    filename: str,
) -> list[ImageQualityWarning]:
    """Return quality warnings for a single image (blur, brightness)."""
    warnings: list[ImageQualityWarning] = []
    rgb = img.convert("RGB")

    # Blur detection: compute variance of the Laplacian approximation via PIL.
    # High variance = sharp; low variance = blurry.
    gray = rgb.convert("L")
    edges = gray.filter(ImageFilter.FIND_EDGES)
    stat = ImageStat.Stat(edges)
    blur_score = stat.var[0]  # variance of edge magnitudes

    if blur_score < _BLUR_THRESHOLD:
        warnings.append(
            ImageQualityWarning(
                image_filename=filename,
                warning_type="blurry",
                message=(
                    f"{filename} appears blurry (score {blur_score:.0f}). "
                    "Retake with the camera steady and subject in focus."
                ),
            )
        )

    # Brightness detection
    stat_rgb = ImageStat.Stat(rgb)
    mean_brightness = statistics.mean(stat_rgb.mean[:3])

    if mean_brightness < _DARK_THRESHOLD:
        warnings.append(
            ImageQualityWarning(
                image_filename=filename,
                warning_type="dark",
                message=(
                    f"{filename} is too dark (brightness {mean_brightness:.0f}/255). "
                    "Ensure good lighting or retake outdoors in daylight."
                ),
            )
        )
    elif mean_brightness > _OVEREXPOSED_THRESHOLD:
        warnings.append(
            ImageQualityWarning(
                image_filename=filename,
                warning_type="overexposed",
                message=(
                    f"{filename} is overexposed (brightness {mean_brightness:.0f}/255). "
                    "Avoid direct sunlight on the lens or shade the vehicle."
                ),
            )
        )

    return warnings


def assess_angle_coverage(image_count: int) -> AngleGuidance:
    """
    Heuristic: if fewer than 4 images were uploaded we assume some angles
    are missing. Without per-image angle classification (needs YOLO) we
    can only guess based on count.
    """
    if image_count >= 4:
        return AngleGuidance(
            angles_detected=EXPECTED_ANGLES,
            angles_missing=[],
            suggestion="",
        )

    detected = EXPECTED_ANGLES[:image_count]
    missing = EXPECTED_ANGLES[image_count:]
    return AngleGuidance(
        angles_detected=detected,
        angles_missing=missing,
        suggestion=(
            f"Upload at least 4 photos ({', '.join(EXPECTED_ANGLES)}) "
            f"for the most accurate assessment. Missing: {', '.join(missing)}."
        ),
    )


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

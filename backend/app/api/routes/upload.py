from fastapi import APIRouter, UploadFile
from pydantic import BaseModel, Field

from app.api.problems import problem_responses
from app.models.damage import ImageQualityWarning
from app.services.image_proc import (
    check_file_size,
    check_image_count,
    check_total_size,
    process_upload,
)

router = APIRouter()


class ImageInfo(BaseModel):
    image_id: str
    original_filename: str
    width: int
    height: int
    file_size_bytes: int
    redacted_regions: int = Field(
        0, description="Faces and number plates blurred before storage"
    )


class UploadResponse(BaseModel):
    upload_id: str
    images: list[ImageInfo]
    image_count: int
    quality_warnings: list[ImageQualityWarning] = []


_CHUNK = 64 * 1024


async def _read_bounded(upload: UploadFile, name: str) -> bytes:
    """Read an upload in chunks, stopping as soon as it passes the size limit."""
    chunks: list[bytes] = []
    size = 0
    while chunk := await upload.read(_CHUNK):
        size += len(chunk)
        check_file_size(name, size)
        chunks.append(chunk)
    return b"".join(chunks)


@router.post(
    "/upload",
    response_model=UploadResponse,
    summary="Upload vehicle images for damage assessment",
    responses=problem_responses(400, 413, 415, 422, 503),
)
async def upload_images(images: list[UploadFile]) -> UploadResponse:
    check_image_count(len(images))
    files: list[tuple[str, bytes, str]] = []
    total = 0
    for img_file in images:
        name = img_file.filename or "unknown"
        data = await _read_bounded(img_file, name)
        total += len(data)
        check_total_size(total)
        files.append((name, data, img_file.content_type or ""))

    upload_id, processed, quality_warnings = await process_upload(files)

    return UploadResponse(
        upload_id=upload_id,
        images=[
            ImageInfo(
                image_id=p.image_id,
                original_filename=p.original_filename,
                width=p.width,
                height=p.height,
                file_size_bytes=p.file_size_bytes,
                redacted_regions=p.redacted_regions,
            )
            for p in processed
        ],
        image_count=len(processed),
        quality_warnings=quality_warnings,
    )

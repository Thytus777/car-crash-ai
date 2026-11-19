from fastapi import APIRouter, UploadFile
from pydantic import BaseModel

from app.api.problems import problem_responses
from app.models.damage import ImageQualityWarning
from app.services.image_proc import process_upload

router = APIRouter()


class ImageInfo(BaseModel):
    image_id: str
    original_filename: str
    width: int
    height: int
    file_size_bytes: int


class UploadResponse(BaseModel):
    upload_id: str
    images: list[ImageInfo]
    image_count: int
    quality_warnings: list[ImageQualityWarning] = []


@router.post(
    "/upload",
    response_model=UploadResponse,
    summary="Upload vehicle images for damage assessment",
    responses=problem_responses(400, 422),
)
async def upload_images(images: list[UploadFile]) -> UploadResponse:
    files: list[tuple[str, bytes, str]] = []
    for img_file in images:
        data = await img_file.read()
        files.append(
            (img_file.filename or "unknown", data, img_file.content_type or "")
        )

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
            )
            for p in processed
        ],
        image_count=len(processed),
        quality_warnings=quality_warnings,
    )

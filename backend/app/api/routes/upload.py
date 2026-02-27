from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel

from app.services.image_proc import ImageValidationError, process_upload

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


@router.post(
    "/upload",
    response_model=UploadResponse,
    summary="Upload vehicle images for damage assessment",
)
async def upload_images(images: list[UploadFile]) -> UploadResponse:
    files: list[tuple[str, bytes, str]] = []
    for img_file in images:
        data = await img_file.read()
        files.append((img_file.filename or "unknown", data, img_file.content_type or ""))

    try:
        upload_id, processed = await process_upload(files)
    except ImageValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

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
    )

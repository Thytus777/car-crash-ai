from fastapi import APIRouter

router = APIRouter()


@router.post("/upload", summary="Upload vehicle images for damage assessment")
async def upload_images() -> dict[str, str]:
    raise NotImplementedError("Image upload not yet implemented")

from fastapi import APIRouter

router = APIRouter()


@router.post("/analyze", summary="Run full damage analysis on uploaded images")
async def analyze_damage() -> dict[str, str]:
    raise NotImplementedError("Damage analysis not yet implemented")

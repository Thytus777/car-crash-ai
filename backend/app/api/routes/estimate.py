from fastapi import APIRouter

router = APIRouter()


@router.get(
    "/estimate/{assessment_id}",
    summary="Get cost estimate for a completed assessment",
)
async def get_estimate(assessment_id: str) -> dict[str, str]:
    raise NotImplementedError("Cost estimation not yet implemented")

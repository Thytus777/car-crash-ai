"""Upload quality warnings reach the final report (#11)."""

from io import BytesIO
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
from PIL import Image

from app.models.llm_outputs import DamageFindings
from tests.llm_fakes import llm_result


async def test_dark_photo_warning_is_carried_into_the_report(
    client: AsyncClient,
) -> None:
    buf = BytesIO()
    Image.new("RGB", (800, 600), color=(5, 5, 5)).save(buf, format="JPEG")
    uploaded = await client.post(
        "/api/v1/upload",
        files=[("images", ("night.jpg", buf.getvalue(), "image/jpeg"))],
    )
    upload_warnings = uploaded.json()["quality_warnings"]
    assert [w["warning_type"] for w in upload_warnings] == ["blurry", "dark"]

    with (
        patch(
            "app.services.damage_detect.generate",
            new_callable=AsyncMock,
            return_value=llm_result(DamageFindings(damages=[])),
        ),
        patch(
            "app.services.assessment.run_sanity_check",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        report = (
            await client.post(
                "/api/v1/analyze",
                json={
                    "upload_id": uploaded.json()["upload_id"],
                    "make": "Toyota",
                    "model": "Camry",
                    "year": 2020,
                },
            )
        ).json()

    assert report["damage_assessment"]["image_quality_warnings"] == upload_warnings

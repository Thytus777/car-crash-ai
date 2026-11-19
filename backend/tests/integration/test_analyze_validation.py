"""Regression tests for #2: /analyze rejects malformed upload IDs up front."""

import pytest
from httpx import AsyncClient


@pytest.mark.parametrize(
    "upload_id", ["../outside", "../../etc", "0123456789ab/..", "ABCDEF012345", ""]
)
async def test_analyze_rejects_malformed_upload_id(
    client: AsyncClient, upload_id: str
) -> None:
    response = await client.post("/api/v1/analyze", json={"upload_id": upload_id})

    assert response.status_code == 422

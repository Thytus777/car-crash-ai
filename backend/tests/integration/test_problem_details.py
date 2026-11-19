"""Every error response is an RFC 9457 problem document (#24)."""

from collections.abc import AsyncIterator
from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient, Response

from app.core.llm import LLMRateLimitError
from app.main import app

PROBLEM_JSON = "application/problem+json"
UPLOAD_ID = "0123456789ab"


def assert_problem(response: Response, status: int) -> dict[str, object]:
    assert response.status_code == status
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    body: dict[str, object] = response.json()
    assert body["status"] == status
    assert isinstance(body["type"], str) and body["type"]
    assert isinstance(body["title"], str) and body["title"]
    assert isinstance(body["detail"], str)
    assert body["instance"] == response.request.url.path
    return body


@pytest.fixture
async def lenient_client() -> AsyncIterator[AsyncClient]:
    """Client that returns 500 responses instead of re-raising app errors."""
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_unknown_route_is_a_404_problem(client: AsyncClient) -> None:
    assert_problem(await client.get("/api/v1/nope"), 404)


async def test_missing_estimate_is_a_404_problem(client: AsyncClient) -> None:
    body = assert_problem(await client.get("/api/v1/estimates/999999"), 404)
    assert body["detail"] == "Estimate 999999 not found"
    assert str(body["type"]).endswith("#not-found")


async def test_request_validation_error_is_a_422_problem_with_field_errors(
    client: AsyncClient,
) -> None:
    response = await client.post("/api/v1/analyze", json={"upload_id": "../x"})

    body = assert_problem(response, 422)
    errors = body["errors"]
    assert isinstance(errors, list) and errors
    assert errors[0]["loc"] == ["body", "upload_id"]


async def test_invalid_image_is_a_400_problem(client: AsyncClient) -> None:
    files = [("images", ("fake.jpg", BytesIO(b"not an image"), "image/jpeg"))]

    body = assert_problem(await client.post("/api/v1/upload", files=files), 400)
    assert "not a valid image" in str(body["detail"])


async def test_llm_rate_limit_is_a_429_problem(client: AsyncClient) -> None:
    with patch(
        "app.api.routes.analysis.identify_vehicle",
        new_callable=AsyncMock,
        side_effect=LLMRateLimitError("All AI providers are rate-limited."),
    ):
        response = await client.post("/api/v1/analyze", json={"upload_id": UPLOAD_ID})

    body = assert_problem(response, 429)
    assert "rate-limited" in str(body["detail"])


async def test_unexpected_error_is_a_generic_500_without_internals(
    lenient_client: AsyncClient,
) -> None:
    with patch(
        "app.api.routes.analysis.identify_vehicle",
        new_callable=AsyncMock,
        side_effect=RuntimeError("db password is hunter2"),
    ):
        response = await lenient_client.post(
            "/api/v1/analyze", json={"upload_id": UPLOAD_ID}
        )

    body = assert_problem(response, 500)
    assert "hunter2" not in response.text
    assert "RuntimeError" not in response.text
    assert body["title"] == "Internal server error"


async def test_unknown_upload_is_a_404_problem(client: AsyncClient) -> None:
    response = await client.post("/api/v1/analyze", json={"upload_id": "fedcba987654"})

    body = assert_problem(response, 404)
    assert body["detail"] == "Upload fedcba987654 not found"


async def test_unimplemented_estimate_route_is_gone(client: AsyncClient) -> None:
    """Regression for #11: /estimate/{id} always raised NotImplementedError (500)."""
    assert_problem(await client.get("/api/v1/estimate/abc"), 404)

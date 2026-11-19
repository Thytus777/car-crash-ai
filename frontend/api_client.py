"""HTTP calls the Streamlit demo makes, kept free of Streamlit for testing.

Every function takes an httpx-compatible client (configure base_url and
timeouts on it), so tests can pass FastAPI's ``TestClient`` and exercise the
real backend contract.
"""

from typing import Any

import httpx

API_PREFIX = "/api/v1"
UPLOAD_PATH = f"{API_PREFIX}/upload"
ANALYZE_PATH = f"{API_PREFIX}/analyze"


class ApiError(Exception):
    """A non-2xx response, carrying the problem document's human message."""

    def __init__(self, status: int, title: str, detail: str) -> None:
        super().__init__(f"{title}: {detail}")
        self.status = status
        self.title = title
        self.detail = detail


def _raise_for_problem(response: httpx.Response) -> None:
    if response.is_success:
        return
    try:
        body = response.json()
    except ValueError:
        body = {}
    raise ApiError(
        response.status_code,
        str(body.get("title", response.reason_phrase)),
        str(body.get("detail", response.text)),
    )


def upload(client: httpx.Client, files: list[tuple[str, bytes, str]]) -> dict[str, Any]:
    """POST images; returns the upload response (upload_id, warnings, ...)."""
    response = client.post(
        UPLOAD_PATH,
        files=[("images", (name, data, mime)) for name, data, mime in files],
    )
    _raise_for_problem(response)
    result: dict[str, Any] = response.json()
    return result


def analyze(
    client: httpx.Client,
    upload_id: str,
    *,
    make: str | None = None,
    model: str | None = None,
    year: int | None = None,
) -> dict[str, Any]:
    """Run the full assessment. May return status 'vehicle_confirmation_needed'."""
    payload: dict[str, Any] = {"upload_id": upload_id}
    if make and model and year:
        payload.update(make=make, model=model, year=year)
    response = client.post(ANALYZE_PATH, json=payload)
    _raise_for_problem(response)
    result: dict[str, Any] = response.json()
    return result


def money(value: str | None) -> str:
    """Format a decimal string from the API; null means the part is unpriced."""
    return "Unpriced" if value is None else f"${float(value):,.0f}"

"""Reject oversized request bodies before Starlette parses them."""

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from app.api.problems import problem_response_for
from app.core.config import settings
from app.core.errors import PayloadTooLargeError

# Multipart framing and form fields on top of the image bytes themselves.
_MULTIPART_OVERHEAD_BYTES = 1024 * 1024


def install_body_size_limit(app: FastAPI) -> None:
    @app.middleware("http")
    async def limit_body_size(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        declared = request.headers.get("content-length")
        limit = settings.max_upload_total_mb * 1024 * 1024 + _MULTIPART_OVERHEAD_BYTES
        if declared is not None and declared.isdigit() and int(declared) > limit:
            return problem_response_for(
                request,
                PayloadTooLargeError(
                    f"The request body ({int(declared) / 1024 / 1024:.1f} MB) "
                    f"exceeds the {settings.max_upload_total_mb:g} MB upload limit"
                ),
            )
        return await call_next(request)

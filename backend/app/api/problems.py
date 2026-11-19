"""RFC 9457 problem-details responses for every error the API returns."""

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import AppError

logger = logging.getLogger(__name__)

PROBLEM_MEDIA_TYPE = "application/problem+json"
PROBLEM_TYPE_BASE = (
    "https://github.com/Thytus777/car-crash-ai/blob/main/docs/errors.md#"
)

_SLUG_BY_STATUS = {
    400: "invalid-input",
    404: "not-found",
    405: "method-not-allowed",
    422: "validation-error",
    500: "internal-error",
}


class Problem(BaseModel):
    """RFC 9457 problem document. Extra members carry problem-specific data."""

    model_config = ConfigDict(extra="allow")

    type: str = Field(description="URI identifying the problem type")
    title: str = Field(description="Short, human-readable summary of the type")
    status: int = Field(description="HTTP status code")
    detail: str = Field(description="Explanation specific to this occurrence")
    instance: str = Field(description="Request path that produced the problem")


def _problem_response(
    request: Request,
    status: int,
    slug: str,
    title: str,
    detail: str,
    **extensions: Any,
) -> JSONResponse:
    problem = Problem(
        type=PROBLEM_TYPE_BASE + slug,
        title=title,
        status=status,
        detail=detail,
        instance=request.url.path,
        **extensions,
    )
    return JSONResponse(
        problem.model_dump(mode="json"),
        status_code=status,
        media_type=PROBLEM_MEDIA_TYPE,
    )


async def _app_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    if exc.status >= 500:
        logger.warning("%s: %s", exc.slug, exc.detail)
    return _problem_response(
        request, exc.status, exc.slug, exc.title, exc.detail, **exc.extensions
    )


async def _http_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    phrase = HTTPStatus(exc.status_code).phrase
    detail = exc.detail if isinstance(exc.detail, str) else phrase
    slug = _SLUG_BY_STATUS.get(exc.status_code, f"http-{exc.status_code}")
    return _problem_response(request, exc.status_code, slug, phrase, detail)


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    errors = [
        {"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]}
        for e in exc.errors()
    ]
    return _problem_response(
        request,
        422,
        "validation-error",
        "Request validation failed",
        f"{len(errors)} field(s) failed validation",
        errors=errors,
    )


async def _unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s", request.url.path, exc_info=exc)
    return _problem_response(
        request,
        500,
        "internal-error",
        "Internal server error",
        "An unexpected error occurred. It has been logged.",
    )


def install_problem_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _unhandled_error)


def problem_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI ``responses=`` entries documenting problem bodies."""
    return {
        status: {
            "model": Problem,
            "description": HTTPStatus(status).phrase,
            "content": {PROBLEM_MEDIA_TYPE: {}},
        }
        for status in statuses
    }

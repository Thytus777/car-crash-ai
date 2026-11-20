"""Request IDs, access logs, and liveness/readiness endpoints."""

import asyncio
import functools
import logging
import re
import tempfile
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel
from sqlalchemy import text

import app.db.session as db_session
from app.core.config import settings
from app.core.llm import _api_key
from app.core.logging import request_id_var
from app.core.metrics import HTTP_DURATION, HTTP_REQUESTS
from app.prompts import validate_prompts

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")
_access_log = logging.getLogger("app.access")

router = APIRouter(tags=["health"])


_EXTRA_ROUTES = ("/metrics",)  # served but not in the OpenAPI schema


@functools.cache
def _route_patterns(app: FastAPI) -> tuple[tuple[re.Pattern[str], str], ...]:
    """Path templates from the app's own OpenAPI document, most specific first."""
    templates = [*app.openapi()["paths"], *_EXTRA_ROUTES]
    return tuple(
        (re.compile(re.sub(r"\{[^}]+\}", "[^/]+", t) + "$"), t)
        for t in sorted(templates, key=lambda t: (t.count("{"), -len(t)))
    )


def _route_template(request: Request) -> str:
    """Metric label for a request: its route template, or 'unmatched'."""
    for pattern, template in _route_patterns(request.app):
        if pattern.match(request.url.path):
            return template
    return "unmatched"


def install_request_context(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = (
            incoming if _VALID_REQUEST_ID.fullmatch(incoming) else uuid.uuid4().hex
        )
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            duration = time.perf_counter() - started
            # Route template, not the raw path, keeps label cardinality bounded.
            route = _route_template(request)
            HTTP_REQUESTS.labels(route, request.method, str(status)).inc()
            HTTP_DURATION.labels(route, request.method).observe(duration)
            _access_log.info(
                "%s %s %d",
                request.method,
                request.url.path,
                status,
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": status,
                    "duration_ms": round(duration * 1000, 1),
                },
            )
            request_id_var.reset(token)


class Check(BaseModel):
    ok: bool
    detail: str = ""


class Readiness(BaseModel):
    status: str  # ready | degraded | not_ready
    checks: dict[str, Check]


@router.get("/metrics", include_in_schema=False)
async def metrics() -> PlainTextResponse:
    """Prometheus exposition. Not part of the public API contract."""
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get("/healthz", summary="Liveness: the process is up")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


# Cloud Run reserves /healthz (its front end answers it), so deployed probes
# and the smoke test use /health. Both stay: /healthz is the local convention.
@router.get("/health", summary="Liveness: the process is up (use this on Cloud Run)")
async def health() -> dict[str, str]:
    return {"status": "ok"}


async def _database() -> Check:
    try:
        async with asyncio.timeout(2.0), db_session.AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return Check(ok=True)
    except Exception as exc:  # any failure means "not reachable"
        return Check(ok=False, detail=type(exc).__name__)


def _upload_dir() -> Check:
    try:
        settings.upload_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=settings.upload_dir):
            pass
        return Check(ok=True)
    except OSError as exc:
        return Check(ok=False, detail=type(exc).__name__)


def _prompts() -> Check:
    try:
        validate_prompts()
        return Check(ok=True, detail=settings.prompt_version)
    except RuntimeError as exc:
        return Check(ok=False, detail=str(exc))


def _redaction() -> Check:
    from app.services.redaction import get_redactor

    if get_redactor() is not None:
        return Check(ok=True, detail="faces + plates")
    if settings.redaction_required:
        return Check(ok=False, detail="models missing; run `make models`")
    return Check(ok=True, detail="DISABLED: models missing (dev only)")


def _llm_provider() -> Check:
    configured = [p for p in ("gemini", "openai") if _api_key(p)]
    if settings.ai_provider not in configured and not configured:
        return Check(ok=False, detail="no model API key configured")
    return Check(ok=True, detail=", ".join(configured))


@router.get(
    "/readyz",
    summary="Readiness: can serve assessments",
    responses={503: {"model": Readiness, "description": "Not ready"}},
)
async def readyz() -> JSONResponse:
    checks = {
        "prompts": _prompts(),
        "upload_dir": _upload_dir(),
        "llm_provider": _llm_provider(),
        "redaction": _redaction(),
        # Saving results is best-effort (see #1), so the DB only degrades.
        "database": await _database(),
    }
    required = ("prompts", "upload_dir", "llm_provider", "redaction")
    if not all(checks[name].ok for name in required):
        status, code = "not_ready", 503
    elif not checks["database"].ok:
        status, code = "degraded", 200
    else:
        status, code = "ready", 200
    body = Readiness(status=status, checks=checks)
    return JSONResponse(body.model_dump(), status_code=code)

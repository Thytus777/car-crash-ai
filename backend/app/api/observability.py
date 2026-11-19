"""Request IDs, access logs, and liveness/readiness endpoints."""

import asyncio
import logging
import re
import tempfile
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

import app.db.session as db_session
from app.core.config import settings
from app.core.llm import _api_key
from app.core.logging import request_id_var
from app.prompts import validate_prompts

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")
_access_log = logging.getLogger("app.access")

router = APIRouter(tags=["health"])


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
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
            request_id_var.reset(token)


class Check(BaseModel):
    ok: bool
    detail: str = ""


class Readiness(BaseModel):
    status: str  # ready | degraded | not_ready
    checks: dict[str, Check]


@router.get("/healthz", summary="Liveness: the process is up")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health", summary="Alias of /healthz", deprecated=True)
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
        # Saving results is best-effort (see #1), so the DB only degrades.
        "database": await _database(),
    }
    required = ("prompts", "upload_dir", "llm_provider")
    if not all(checks[name].ok for name in required):
        status, code = "not_ready", 503
    elif not checks["database"].ok:
        status, code = "degraded", 200
    else:
        status, code = "ready", 200
    body = Readiness(status=status, checks=checks)
    return JSONResponse(body.model_dump(), status_code=code)

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import observability
from app.api.access import check_production_settings, install_access_control
from app.api.limits import install_body_size_limit
from app.api.problems import install_problem_handlers, problem_responses
from app.api.routes import analysis, estimates, report, upload
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.tracing import configure_tracing
from app.prompts import validate_prompts
from app.services.image_proc import purge_expired_uploads

configure_logging()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    task = asyncio.create_task(_purge_uploads_periodically())
    try:
        yield
    finally:
        task.cancel()


async def _purge_uploads_periodically() -> None:
    while True:
        removed = await asyncio.to_thread(purge_expired_uploads)
        if removed:
            logging.getLogger("app.retention").info(
                "Deleted %d expired upload(s)", removed, extra={"removed": removed}
            )
        await asyncio.sleep(3600)


app = FastAPI(
    lifespan=lifespan,
    title="Car Crash AI",
    description="AI-powered vehicle damage detection and cost estimation",
    version=__version__,
)

check_production_settings(settings)  # refuse to start unsafe
validate_prompts()  # fail at startup, not on the first request
install_problem_handlers(app)
install_body_size_limit(app)
install_access_control(app)
# Added last, so it runs outermost: IDs and access logs cover every response.
observability.install_request_context(app)

# Keys travel in headers, never cookies, so credentials stay off.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key", "Authorization", "X-Request-ID"],
    expose_headers=["X-Request-ID", "Retry-After"],
)

_API = {"prefix": "/api/v1", "responses": problem_responses(401, 429)}

app.include_router(upload.router, tags=["upload"], **_API)  # type: ignore[arg-type]
app.include_router(analysis.router, tags=["analysis"], **_API)  # type: ignore[arg-type]
app.include_router(estimates.router, tags=["history"], **_API)  # type: ignore[arg-type]
app.include_router(report.router, tags=["report"], **_API)  # type: ignore[arg-type]

app.include_router(observability.router)
configure_tracing(app)

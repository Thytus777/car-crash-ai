from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import observability
from app.api.limits import install_body_size_limit
from app.api.problems import install_problem_handlers
from app.api.routes import analysis, estimates, report, upload
from app.core.config import settings
from app.core.logging import configure_logging
from app.prompts import validate_prompts

configure_logging()

app = FastAPI(
    title="Car Crash AI",
    description="AI-powered vehicle damage detection and cost estimation",
    version=__version__,
)

validate_prompts()  # fail at startup, not on the first request
install_problem_handlers(app)
install_body_size_limit(app)
# Added last, so it runs outermost: IDs and access logs cover every response.
observability.install_request_context(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload.router, prefix="/api/v1", tags=["upload"])
app.include_router(analysis.router, prefix="/api/v1", tags=["analysis"])
app.include_router(estimates.router, prefix="/api/v1", tags=["history"])
app.include_router(report.router, prefix="/api/v1", tags=["report"])

app.include_router(observability.router)

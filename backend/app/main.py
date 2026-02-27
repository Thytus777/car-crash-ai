from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import analysis, estimate, upload
from app.core.config import settings

app = FastAPI(
    title="Car Crash AI",
    description="AI-powered vehicle damage detection and cost estimation",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload.router, prefix="/api/v1", tags=["upload"])
app.include_router(analysis.router, prefix="/api/v1", tags=["analysis"])
app.include_router(estimate.router, prefix="/api/v1", tags=["estimate"])


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}

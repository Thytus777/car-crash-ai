"""The real app with a simulated model provider, for load testing.

    uvicorn loadtest.fake_app:app --port 8765

The whole HTTP and pipeline stack is real: validation, triage, vehicle ID,
zone passes, pricing, sanity check, persistence (SQLite). Only provider calls
are replaced, by a fake that sleeps LOADTEST_MODEL_LATENCY_S (+/-
LOADTEST_JITTER_S, uniform) and returns schema-valid output. Results measure
this service's overhead and concurrency under model latency, not real models.
"""

import asyncio
import os
import random
import tempfile
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel, SecretStr
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.llm_fakes import SchemaClient

import app.core.llm as llm
import app.db.session as db_session
from app.core.config import settings
from app.core.llm import Completion, ImageDetail
from app.db.models import Base
from app.main import app

LATENCY_S = float(os.environ.get("LOADTEST_MODEL_LATENCY_S", "1.5"))
JITTER_S = float(os.environ.get("LOADTEST_JITTER_S", "0.5"))


class SlowSchemaClient(SchemaClient):
    async def complete(
        self,
        *,
        schema: type[BaseModel],
        prompt: str,
        images: Sequence[bytes],
        max_output_tokens: int,
        temperature: float,
        image_detail: ImageDetail,
    ) -> Completion:
        delay = random.uniform(LATENCY_S - JITTER_S, LATENCY_S + JITTER_S)
        await asyncio.sleep(max(0.0, delay))
        return await super().complete(
            schema=schema,
            prompt=prompt,
            images=images,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            image_detail=image_detail,
        )


_client = SlowSchemaClient()
settings.gemini_api_key = SecretStr("loadtest")
settings.openai_api_key = SecretStr("")
settings.serpapi_key = SecretStr("")  # no live price search
llm.get_client = lambda _provider: _client  # type: ignore[assignment]

_tmp = Path(tempfile.mkdtemp(prefix="car-crash-loadtest-"))
settings.upload_dir = _tmp / "uploads"
_engine = create_async_engine(f"sqlite+aiosqlite:///{_tmp / 'loadtest.db'}")
db_session.AsyncSessionLocal = async_sessionmaker(_engine, expire_on_commit=False)

_inner_lifespan = app.router.lifespan_context


@asynccontextmanager
async def _lifespan(application: FastAPI) -> AsyncIterator[None]:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with _inner_lifespan(application):
        yield


app.router.lifespan_context = _lifespan

__all__ = ["app"]

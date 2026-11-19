from collections.abc import AsyncIterator, Iterator
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

import app.db.session as db_session
from app.db.models import Base
from app.main import app
from app.models.llm_outputs import ImageTriage


def _enable_sqlite_foreign_keys(dbapi_conn: DBAPIConnection, _record: object) -> None:
    # SQLite ignores FOREIGN KEY constraints unless asked, Postgres doesn't.
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@pytest.fixture
async def db_engine() -> AsyncIterator[AsyncEngine]:
    """In-memory SQLite with FK enforcement, schema from the ORM models."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    event.listen(engine.sync_engine, "connect", _enable_sqlite_foreign_keys)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture(autouse=True)
def test_db(
    db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> async_sessionmaker[AsyncSession]:
    """Route every app DB session to the in-memory database."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr(db_session, "AsyncSessionLocal", factory)
    return factory


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.fixture(autouse=True)
def triage(request: pytest.FixtureRequest) -> Iterator[AsyncMock]:
    """Image triage passes by default; tests set .return_value/.side_effect."""
    ok = ImageTriage(shows_vehicle=True, usable=True, reason="A clear photo of a car.")
    with patch(
        "app.api.routes.analysis.triage_images",
        new_callable=AsyncMock,
        return_value=ok,
    ) as mock:
        yield mock

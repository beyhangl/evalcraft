"""Test fixtures for the dashboard backend."""

from __future__ import annotations

import asyncio
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.config import get_settings, Settings
import app.models  # noqa: F401 — register all models

# Use SQLite for tests
TEST_DB_URL = "sqlite+aiosqlite://"

# Patch PostgreSQL-specific types for SQLite compatibility
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.ext.compiler import compiles


@compiles(PG_UUID, "sqlite")
def _compile_uuid_sqlite(type_, compiler, **kw):
    return "VARCHAR(36)"


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def _test_settings() -> Settings:
    return Settings(
        database_url=TEST_DB_URL,
        redis_url="redis://localhost:6379/0",
        secret_key="test-secret-key-for-tests",
        cors_origins=["http://localhost:3000"],
        debug=False,
    )


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_engine):
    """Async HTTP test client with overridden DB and settings."""
    from app.main import app
    from app.config import get_settings as orig_get_settings

    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    async def _override_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[orig_get_settings] = _test_settings

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    """Sign up a test user and return auth headers."""
    unique = uuid.uuid4().hex[:8]
    resp = await client.post("/api/v1/auth/signup", json={
        "email": f"test-{unique}@example.com",
        "password": "testpass123",
        "full_name": "Test User",
        "team_name": f"Team-{unique}",
    })
    assert resp.status_code == 201
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def test_project(client: AsyncClient, auth_headers: dict) -> str:
    """Create a test project and return its ID."""
    resp = await client.post(
        "/api/v1/projects",
        json={"name": "Test Project", "description": "For testing"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


SAMPLE_CASSETTE = {
    "name": "test-cassette",
    "agent_name": "test-agent",
    "framework": "test",
    "spans": [],
    "metadata": {"input": "hello", "output": "world"},
}

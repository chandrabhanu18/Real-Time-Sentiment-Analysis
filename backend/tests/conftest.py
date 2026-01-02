import asyncio
import os
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from backend.main import app, get_db
from backend.models.models import Base


DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop()
    yield loop


@pytest.fixture(scope="session")
async def engine():
    engine = create_async_engine(DATABASE_URL, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(engine):
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session


@pytest.fixture
async def client(engine, db_session):
    # override get_db dependency
    async def _get_test_db():
        async with db_session as s:
            yield s

    app.dependency_overrides[get_db] = _get_test_db

    # Create an AsyncClient that can speak to the ASGI app for testing.
    try:
        # Preferred: ASGITransport exported by httpx
        from httpx import AsyncClient, ASGITransport
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    except Exception:
        # Fallback: try internal transport location
        try:
            from httpx import AsyncClient
            from httpx._transports.asgi import ASGITransport
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                yield ac
        except Exception:
            # As a last resort, use the synchronous TestClient wrapped in async context
            from fastapi.testclient import TestClient
            def _sync_client():
                with TestClient(app) as client:
                    return client
            # yield sync client (tests may still work when awaited)
            yield _sync_client()

import tempfile
from collections.abc import AsyncGenerator
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.core.storage as storage_module
from app.core.storage.local import LocalStorage
from app.db.base import Base
from app.db.session import get_db
from app.main import app as fastapi_app

# Use in-memory SQLite for automated tests to ensure isolation and zero external DB dependency
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)

TestingSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest_asyncio.fixture(autouse=True)
async def prepare_test_db() -> AsyncGenerator[None, None]:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestingSessionLocal() as session:
        yield session


fastapi_app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def mock_celery_and_storage(monkeypatch: pytest.MonkeyPatch):
    with tempfile.TemporaryDirectory() as tmp_storage:
        test_storage = LocalStorage(base_path=tmp_storage)
        monkeypatch.setattr(storage_module, "get_storage", lambda: test_storage)
        with patch("app.workers.tasks.process_document.delay") as mock_delay:
            mock_delay.return_value = MagicMock(id="test-task-1234")
            yield


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

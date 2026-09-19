import tempfile
from collections.abc import AsyncGenerator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

import app.core.storage as storage_module
import app.db.session as session_module
from app.db.base import Base
from app.db.session import get_db
from app.main import app as fastapi_app

# Temporary file-backed SQLite database shared between async API and sync worker tasks
temp_db_dir = tempfile.mkdtemp()
test_db_file = Path(temp_db_dir) / "test.db"
test_db_path = str(test_db_file)

SYNC_TEST_DB_URL = f"sqlite:///{test_db_path}"
ASYNC_TEST_DB_URL = f"sqlite+aiosqlite:///{test_db_path}"

sync_test_engine = create_engine(
    SYNC_TEST_DB_URL,
    connect_args={"check_same_thread": False},
)
SyncTestingSessionLocal = sessionmaker(
    bind=sync_test_engine,
    class_=Session,
    expire_on_commit=False,
)

async_test_engine = create_async_engine(
    ASYNC_TEST_DB_URL,
    connect_args={"check_same_thread": False},
)
AsyncTestingSessionLocal = async_sessionmaker(
    bind=async_test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest_asyncio.fixture(autouse=True)
async def prepare_test_db() -> AsyncGenerator[None, None]:
    async with async_test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with async_test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncTestingSessionLocal() as session:
        yield session


fastapi_app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def mock_celery_and_storage(monkeypatch: pytest.MonkeyPatch):
    with tempfile.TemporaryDirectory() as tmp_storage:
        from app.config import get_settings

        settings = get_settings()
        old_storage_path = settings.storage_path
        settings.storage_path = tmp_storage
        storage_module.get_storage.cache_clear()

        import app.workers.tasks as tasks_module

        monkeypatch.setattr(session_module, "get_sync_db", lambda: SyncTestingSessionLocal())
        monkeypatch.setattr(tasks_module, "get_sync_db", lambda: SyncTestingSessionLocal())
        with patch("app.workers.tasks.process_document.delay") as mock_delay:
            mock_delay.return_value = MagicMock(id="test-task-1234")
            with patch("app.workers.tasks.process_page.delay") as mock_page_delay:
                mock_page_delay.return_value = MagicMock(id="test-page-1234")
                with patch("app.workers.tasks.finalize_document.delay") as mock_fin_delay:
                    mock_fin_delay.return_value = MagicMock(id="test-fin-1234")
                    try:
                        yield
                    finally:
                        settings.storage_path = old_storage_path
                        storage_module.get_storage.cache_clear()


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

"""Local Standalone Server for Document Intelligence Service & Interactive Web Dashboard.

Runs the complete frontend and backend on http://localhost:8000 without requiring
external PostgreSQL, Redis, or Docker services.

Provides:
- Interactive Web Dashboard at http://localhost:8000/
- Interactive Swagger UI at http://localhost:8000/docs
- Local SQLite database & local storage backend
- In-process asynchronous task runner for background document ingestion & extraction
- Pre-seeded sample papers and demo evaluator account
"""

import sys
import threading
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Ensure repo root is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

# ruff: noqa: E402
import uvicorn
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

import app.core.storage as storage_module
import app.db.session as session_module
import app.workers.tasks as tasks_module
from app.api.v1.schemas.document import DocumentUploadResponse
from app.config import get_settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.models.document import Document
from app.db.models.user import User
from app.deps import get_current_user
from app.main import app as fastapi_app
from scripts.generate_samples import INPUT_DIR, generate_all_samples

DATA_DIR = ROOT_DIR / "data"
STORAGE_DIR = DATA_DIR / "storage"
DB_PATH = DATA_DIR / "local_service.db"


def run_pipeline_sync(doc_id_str: str) -> None:
    """Executes document processing pipeline in a background worker thread."""
    try:
        # 1. Ingest
        ingest_res = tasks_module.process_document(doc_id_str)
        page_count = ingest_res.get("page_count", 1)

        # 2. Process all pages
        for p_no in range(1, page_count + 1):
            tasks_module.process_page(doc_id_str, p_no)

        # 3. Finalize
        tasks_module.finalize_document(doc_id_str)
    except Exception as exc:
        print(f"[Worker Thread Error] Failed processing document {doc_id_str}: {exc}")


def async_task_launcher(task_func: Any, doc_id_str: str) -> Any:
    """Launches pipeline execution in a separate daemon thread."""
    thread = threading.Thread(target=run_pipeline_sync, args=(doc_id_str,), daemon=True)
    thread.start()
    return thread


demo_router = APIRouter(prefix="/api/v1/demo", tags=["demo"])


@demo_router.post(
    "/sample-upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Quick upload preset sample paper",
)
async def sample_upload(
    filename: str = Query(..., description="Filename in samples/input/"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(session_module.get_db),
) -> DocumentUploadResponse:
    sample_file = INPUT_DIR / filename
    if not sample_file.exists():
        generate_all_samples()
        if not sample_file.exists():
            raise HTTPException(status_code=404, detail=f"Sample file {filename} not found")

    file_bytes = sample_file.read_bytes()
    doc_id = uuid.uuid4()
    storage = storage_module.get_storage()
    ext = filename.split(".")[-1]
    storage_key = f"{user.id}/{doc_id}.{ext}"
    storage.save_sync(storage_key, file_bytes)

    import hashlib
    sha256 = hashlib.sha256(file_bytes).hexdigest()

    doc = Document(
        id=doc_id,
        owner_id=user.id,
        original_filename=filename,
        storage_key=storage_key,
        mime_type="application/pdf" if filename.endswith(".pdf") else "image/png",
        size_bytes=len(file_bytes),
        sha256=sha256,
        status="queued",
        stage="queued",
        progress_pct=0,
        pages_done=0,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    # Launch background thread
    async_task_launcher(tasks_module.process_document, str(doc_id))

    return DocumentUploadResponse(
        id=doc.id,
        status=doc.status,
        links={"status": f"/api/v1/documents/{doc.id}/status", "self": f"/api/v1/documents/{doc.id}"},
    )


def setup_standalone_environment() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    # Generate synthetic samples if missing
    generate_all_samples()

    # Configure SQLite database
    sync_db_url = f"sqlite:///{DB_PATH}"
    async_db_url = f"sqlite+aiosqlite:///{DB_PATH}"

    sync_engine = create_engine(sync_db_url, connect_args={"check_same_thread": False})
    async_engine = create_async_engine(async_db_url, connect_args={"check_same_thread": False})

    SyncSession = sessionmaker(bind=sync_engine, class_=Session, expire_on_commit=False)
    AsyncSessionLocal = async_sessionmaker(
        bind=async_engine, class_=AsyncSession, expire_on_commit=False
    )

    Base.metadata.create_all(sync_engine)

    # Override dependencies
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with AsyncSessionLocal() as session:
            yield session

    fastapi_app.dependency_overrides[session_module.get_db] = override_get_db
    session_module.get_sync_db = lambda: SyncSession()
    tasks_module.get_sync_db = lambda: SyncSession()

    settings = get_settings()
    settings.storage_path = str(STORAGE_DIR)
    settings.extractor = "rules"
    storage_module.get_storage.cache_clear()

    import app.services.upload_service as upload_module
    from app.workers.celery_app import celery

    celery.conf.broker_url = "memory://"
    celery.conf.result_backend = "cache+memory://"
    celery.conf.task_always_eager = True
    celery.conf.task_eager_propagates = True

    # Override Celery delay hooks with in-process background runner
    upload_module.process_document.delay = lambda doc_id: async_task_launcher(
        tasks_module.process_document, doc_id
    )
    tasks_module.process_document.delay = lambda doc_id: async_task_launcher(
        tasks_module.process_document, doc_id
    )
    tasks_module.process_page.delay = lambda *args, **kwargs: None
    tasks_module.finalize_document.delay = lambda *args, **kwargs: None

    # Seed demo user
    with SyncSession() as session:
        user = session.execute(
            select(User).where(User.email == "demo_evaluator@example.com")
        ).scalar_one_or_none()
        if not user:
            demo_user = User(
                id=uuid.uuid4(),
                email="demo_evaluator@example.com",
                password_hash=hash_password("SecurePassword123!"),
                role="user",
                is_active=True,
                created_at=datetime.now(UTC),
            )
            session.add(demo_user)
            session.commit()

    # Include demo router
    fastapi_app.include_router(demo_router)

    # Serve static UI at root
    static_file = ROOT_DIR / "app" / "static" / "index.html"

    @fastapi_app.get("/", response_class=HTMLResponse, include_in_schema=False)
    @fastapi_app.get("/ui", response_class=HTMLResponse, include_in_schema=False)
    async def serve_ui() -> HTMLResponse:
        return HTMLResponse(content=static_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    setup_standalone_environment()
    print("=" * 75)
    print("DOCINTEL SERVICE -- FULL LOCAL STACK RUNNING")
    print("=" * 75)
    print("  * Interactive Web UI:     http://localhost:8000/")
    print("  * Interactive Swagger UI:  http://localhost:8000/docs")
    print("  * Demo Login:              demo_evaluator@example.com / SecurePassword123!")
    print("=" * 75)
    uvicorn.run(fastapi_app, host="127.0.0.1", port=8000, log_level="info")

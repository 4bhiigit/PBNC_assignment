import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.db.models.document import Document
from app.db.models.processing_event import ProcessingEvent
from app.db.session import get_sync_db
from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.tasks.process_document", bind=True, acks_late=True)
def process_document(self: Any, document_id_str: str) -> dict[str, str]:
    """Phase 2 stub task: transitions document from queued -> processing -> completed.
    Full multi-page fan-out and OCR extraction is implemented in Phase 3.
    """
    doc_uuid = uuid.UUID(document_id_str)
    session = get_sync_db()

    try:
        query = select(Document).where(Document.id == doc_uuid)
        doc = session.execute(query).scalar_one_or_none()
        if not doc:
            logger.error("Document %s not found for processing", document_id_str)
            return {"status": "not_found"}

        # 1. Update status to processing
        doc.status = "processing"
        doc.stage = "ingest"
        doc.progress_pct = 25
        event_start = ProcessingEvent(
            document_id=doc.id,
            stage="ingest",
            status="started",
            attempt=self.request.retries + 1,
            started_at=datetime.now(UTC),
            meta={"task_id": self.request.id},
        )
        session.add(event_start)
        session.commit()

        # 2. Simulate progress for the lifecycle stub
        doc.stage = "pages"
        doc.progress_pct = 75
        doc.pages_done = doc.page_count
        session.commit()

        # 3. Mark completed
        doc.status = "completed"
        doc.stage = "finalize"
        doc.progress_pct = 100
        doc.completed_at = datetime.now(UTC)

        event_finish = ProcessingEvent(
            document_id=doc.id,
            stage="finalize",
            status="completed",
            attempt=self.request.retries + 1,
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            meta={"task_id": self.request.id},
        )
        session.add(event_finish)
        session.commit()

        logger.info("Document %s processing completed", document_id_str)
        return {"status": "completed"}
    except Exception as exc:
        session.rollback()
        logger.exception("Error processing document %s: %s", document_id_str, exc)
        try:
            doc = session.execute(
                select(Document).where(Document.id == doc_uuid)
            ).scalar_one_or_none()
            if doc:
                doc.status = "failed"
                doc.error_code = "PROCESSING_ERROR"
                doc.error_message = str(exc)[:500]
                session.commit()
        except Exception:
            session.rollback()
        raise
    finally:
        session.close()


@celery.task(name="app.workers.tasks.process_page", bind=True, acks_late=True)
def process_page(self: Any, document_id_str: str, page_no: int) -> dict[str, str]:
    """Stub page processing task for queue registration."""
    return {"status": "pending_phase3"}


@celery.task(name="app.workers.tasks.finalize_document", bind=True, acks_late=True)
def finalize_document(self: Any, document_id_str: str) -> dict[str, str]:
    """Stub finalize task for queue registration."""
    return {"status": "pending_phase3"}

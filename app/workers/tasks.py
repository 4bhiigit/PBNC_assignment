import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select, update

from app.config import get_settings
from app.core.storage import get_storage
from app.db.models.document import Document
from app.db.models.page import Page
from app.db.models.processing_event import ProcessingEvent
from app.db.models.question import Question
from app.db.session import get_sync_db
from app.pipeline.extractors.mock import MockExtractor
from app.pipeline.extractors.rules import RulesExtractor
from app.pipeline.extractors.schemas import PageContext
from app.pipeline.headers_footers import clean_page_lines, find_repeated_header_footers
from app.pipeline.ingest import ingest_document
from app.pipeline.ocr import run_ocr
from app.pipeline.preprocess import preprocess_page_image
from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.tasks.process_document", bind=True, acks_late=True)
def process_document(self: Any, document_id_str: str) -> dict[str, Any]:
    """Ingests document file, creates page entries, and fans out per-page tasks."""
    doc_uuid = uuid.UUID(document_id_str)
    session = get_sync_db()
    settings = get_settings()
    storage = get_storage()

    try:
        doc = session.execute(select(Document).where(Document.id == doc_uuid)).scalar_one_or_none()
        if not doc:
            logger.error("Document %s not found for processing", document_id_str)
            return {"status": "not_found"}

        # 1. Update status to processing
        doc.status = "processing"
        doc.stage = "ingest"
        doc.progress_pct = 10
        session.add(
            ProcessingEvent(
                document_id=doc.id,
                stage="ingest",
                status="started",
                attempt=self.request.retries + 1,
                started_at=datetime.now(UTC),
                meta={"task_id": self.request.id},
            )
        )
        session.commit()

        # 2. Ingest document and rasterize pages
        file_bytes = storage.get_bytes_sync(doc.storage_key)
        ingest_result = ingest_document(
            file_bytes=file_bytes,
            mime_type=doc.mime_type,
            owner_id=doc.owner_id,
            doc_id=doc.id,
            storage=storage,
            render_dpi=settings.render_dpi,
            min_chars=settings.text_layer_min_chars,
        )

        doc.page_count = ingest_result.page_count
        doc.pages_done = 0

        # Remove previous pages if re-running
        session.execute(delete(Page).where(Page.document_id == doc_uuid))

        # Create page records
        for p_info in ingest_result.pages:
            page = Page(
                document_id=doc.id,
                page_no=p_info.page_no,
                status="queued",
                has_text_layer=(p_info.decision in ("text_layer", "mixed")),
                text_source=p_info.decision,
                image_key=p_info.image_key,
                raw_text=p_info.text if p_info.decision in ("text_layer", "mixed") else None,
            )
            session.add(page)

        doc.stage = "pages"
        doc.progress_pct = 20
        session.commit()

        # 3. Fan out processing for each page
        for p_info in ingest_result.pages:
            process_page.delay(document_id_str, p_info.page_no)

        logger.info(
            "Document %s ingested: %d pages enqueued",
            document_id_str,
            ingest_result.page_count,
        )
        return {"status": "pages_enqueued", "page_count": ingest_result.page_count}
    except Exception as exc:
        session.rollback()
        logger.exception("Error during document ingest %s: %s", document_id_str, exc)
        try:
            doc = session.execute(
                select(Document).where(Document.id == doc_uuid)
            ).scalar_one_or_none()
            if doc:
                doc.status = "failed"
                doc.error_code = "INGEST_ERROR"
                doc.error_message = str(exc)[:500]
                session.commit()
        except Exception:
            session.rollback()
        raise
    finally:
        session.close()


@celery.task(name="app.workers.tasks.process_page", bind=True, acks_late=True)
def process_page(self: Any, document_id_str: str, page_no: int) -> dict[str, Any]:
    """Processes a single page: runs OCR/analysis, extracts questions, and updates progress."""
    doc_uuid = uuid.UUID(document_id_str)
    session = get_sync_db()
    settings = get_settings()
    storage = get_storage()

    try:
        page = session.execute(
            select(Page).where(Page.document_id == doc_uuid, Page.page_no == page_no)
        ).scalar_one_or_none()
        doc = session.execute(select(Document).where(Document.id == doc_uuid)).scalar_one_or_none()

        if not page or not doc:
            logger.error("Page %d for doc %s not found", page_no, document_id_str)
            return {"status": "not_found"}

        page.status = "processing"
        session.commit()

        image_bytes = storage.get_bytes_sync(page.image_key) if page.image_key else b""

        # Preprocessing & OCR decision
        if (
            page.has_text_layer
            and page.raw_text
            and len(page.raw_text.strip()) >= settings.text_layer_min_chars
        ):
            page_text = page.raw_text
            ocr_conf = 1.0
            text_source = "text_layer"
        else:
            prep_res = preprocess_page_image(image_bytes)
            page.rotation_applied = prep_res.rotation_applied
            page.deskew_angle = prep_res.deskew_angle
            page.blur_score = prep_res.blur_score
            page.effective_dpi = prep_res.effective_dpi
            for f in prep_res.flags:
                page.quality_flags.append({"code": f, "severity": "warning"})

            ocr_res = run_ocr(prep_res.processed_image, langs=settings.tesseract_langs)
            page_text = ocr_res.text
            ocr_conf = ocr_res.mean_confidence
            text_source = "ocr"
            page.ocr_used = True
            page.ocr_mean_conf = ocr_conf
            page.raw_text = page_text

        ctx = PageContext(
            document_id=doc_uuid,
            page_no=page_no,
            total_pages=doc.page_count,
            text=page_text,
            text_source=text_source,
            image_bytes=image_bytes,
            ocr_confidence=ocr_conf,
        )

        extractor = MockExtractor() if settings.extractor == "mock" else RulesExtractor()
        extraction = extractor.extract_page(ctx)

        page.extraction = extraction.model_dump()
        page.page_type = extraction.page_type
        page.section_heading = extraction.section_heading
        page.status = "completed"

        doc.pages_done += 1
        doc.progress_pct = 20 + int(70 * (doc.pages_done / max(doc.page_count, 1)))
        session.commit()

        # Check if all pages are done
        remaining = session.execute(
            select(func.count(Page.id)).where(
                Page.document_id == doc_uuid,
                Page.status.not_in(["completed", "failed"]),
            )
        ).scalar_one()

        if remaining == 0:
            # Atomic conditional update: flip finalize_enqueued once
            res = session.execute(
                update(Document)
                .where(Document.id == doc_uuid, Document.finalize_enqueued.is_(False))
                .values(finalize_enqueued=True)
            )
            session.commit()
            if res.rowcount > 0:
                finalize_document.delay(document_id_str)

        return {"status": "completed", "page_no": page_no}
    except Exception as exc:
        session.rollback()
        logger.exception("Error processing page %d for doc %s: %s", page_no, document_id_str, exc)
        try:
            p = session.execute(
                select(Page).where(Page.document_id == doc_uuid, Page.page_no == page_no)
            ).scalar_one_or_none()
            if p:
                p.status = "failed"
                p.error = str(exc)[:500]
                session.commit()

            # Still check if all pages are now terminal
            rem = session.execute(
                select(func.count(Page.id)).where(
                    Page.document_id == doc_uuid,
                    Page.status.not_in(["completed", "failed"]),
                )
            ).scalar_one()
            if rem == 0:
                res = session.execute(
                    update(Document)
                    .where(Document.id == doc_uuid, Document.finalize_enqueued.is_(False))
                    .values(finalize_enqueued=True)
                )
                session.commit()
                if res.rowcount > 0:
                    finalize_document.delay(document_id_str)
        except Exception:
            session.rollback()
        raise
    finally:
        session.close()


@celery.task(name="app.workers.tasks.finalize_document", bind=True, acks_late=True)
def finalize_document(self: Any, document_id_str: str) -> dict[str, Any]:
    """Builds question records, cleans headers/footers, and marks document completed."""
    doc_uuid = uuid.UUID(document_id_str)
    session = get_sync_db()
    settings = get_settings()

    try:
        doc = session.execute(select(Document).where(Document.id == doc_uuid)).scalar_one_or_none()
        if not doc:
            return {"status": "not_found"}

        doc.stage = "finalize"
        doc.progress_pct = 90
        session.commit()

        pages = (
            session.execute(
                select(Page).where(Page.document_id == doc_uuid).order_by(Page.page_no.asc())
            )
            .scalars()
            .all()
        )

        pages_lines = [p.raw_text.splitlines() if p.raw_text else [] for p in pages]
        repeated_headers = find_repeated_header_footers(pages_lines)

        # Idempotently recreate questions
        session.execute(delete(Question).where(Question.document_id == doc_uuid))

        sequence_counter = 1
        for p in pages:
            if not p.extraction or "items" not in p.extraction:
                continue

            for item in p.extraction["items"]:
                cleaned_text = "\n".join(
                    clean_page_lines(item["text"].splitlines(), repeated_headers)
                ).strip()
                if not cleaned_text:
                    continue

                q = Question(
                    document_id=doc.id,
                    sequence=sequence_counter,
                    number_raw=item.get("number_raw"),
                    number_norm=item.get("number_norm"),
                    number_inferred=False,
                    section=p.section_heading,
                    type=item.get("question_type", "unknown"),
                    text=cleaned_text,
                    options=item.get("options", []),
                    source_pages=[p.page_no],
                    extraction_method=settings.extractor,
                    ocr_confidence=p.ocr_mean_conf,
                    confidence=item.get("self_confidence", 0.90),
                    status="extracted",
                    flags=[],
                )

                if item.get("inline_answer_raw"):
                    q.answer_status = "matched"
                    q.answer_raw = item["inline_answer_raw"]
                    q.answer_value = [item["inline_answer_raw"].upper()]
                    q.answer_source = {
                        "kind": "inline",
                        "page": p.page_no,
                        "document_id": str(doc.id),
                    }

                session.add(q)
                sequence_counter += 1

        doc.status = "completed"
        doc.stage = "finalize"
        doc.progress_pct = 100
        doc.completed_at = datetime.now(UTC)

        session.add(
            ProcessingEvent(
                document_id=doc.id,
                stage="finalize",
                status="completed",
                attempt=self.request.retries + 1,
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
                meta={"task_id": self.request.id, "questions_count": sequence_counter - 1},
            )
        )
        session.commit()

        logger.info(
            "Document %s finalized: %d questions extracted",
            document_id_str,
            sequence_counter - 1,
        )
        return {"status": "completed", "questions_count": sequence_counter - 1}
    except Exception as exc:
        session.rollback()
        logger.exception("Error finalizing document %s: %s", document_id_str, exc)
        try:
            doc = session.execute(
                select(Document).where(Document.id == doc_uuid)
            ).scalar_one_or_none()
            if doc:
                doc.status = "failed"
                doc.error_code = "FINALIZE_ERROR"
                doc.error_message = str(exc)[:500]
                session.commit()
        except Exception:
            session.rollback()
        raise
    finally:
        session.close()

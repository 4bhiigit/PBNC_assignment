import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select, update

from app.config import get_settings
from app.core.storage import get_storage
from app.db.models.answer_key import AnswerKeyEntry
from app.db.models.document import Document
from app.db.models.document_link import DocumentLink
from app.db.models.page import Page
from app.db.models.processing_event import ProcessingEvent
from app.db.models.question import Question
from app.db.models.question_asset import QuestionAsset
from app.db.models.warning import Warning
from app.db.session import get_sync_db
from app.pipeline.answer_key.detect import detect_document_role, is_answer_key_page
from app.pipeline.answer_key.match import match_question_answers
from app.pipeline.answer_key.parse import (
    merge_llm_answer_key_entries,
    parse_answer_key_text,
)
from app.pipeline.extractors.base import Extractor
from app.pipeline.extractors.gemini import GeminiExtractor
from app.pipeline.extractors.mock import MockExtractor
from app.pipeline.extractors.rules import RulesExtractor
from app.pipeline.extractors.schemas import PageContext, PageExtraction
from app.pipeline.figures import process_question_figures
from app.pipeline.grounding import check_count_mismatch, verify_item_grounding
from app.pipeline.headers_footers import clean_page_lines, find_repeated_header_footers
from app.pipeline.ingest import ingest_document
from app.pipeline.ocr import run_ocr
from app.pipeline.preprocess import preprocess_page_image
from app.pipeline.stitcher import PageExtractionInput, stitch_document_extractions
from app.pipeline.validation import get_flag_severity
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
            if not page_text.strip() and page.raw_text and page.raw_text.strip():
                page_text = page.raw_text
                text_source = "text_layer"
            page.raw_text = page_text

        # Fetch previous page text for continuity context
        prev_page = session.execute(
            select(Page).where(Page.document_id == doc_uuid, Page.page_no == page_no - 1)
        ).scalar_one_or_none()
        prev_text = prev_page.raw_text if prev_page else None

        ctx = PageContext(
            document_id=doc_uuid,
            page_no=page_no,
            total_pages=doc.page_count,
            text=page_text,
            text_source=text_source,
            image_bytes=image_bytes,
            ocr_confidence=ocr_conf,
            prev_page_context=prev_text,
        )

        extractor: Extractor
        if settings.extractor == "mock":
            extractor = MockExtractor()
        elif settings.extractor == "rules":
            extractor = RulesExtractor()
        else:
            extractor = GeminiExtractor()

        extraction = extractor.extract_page(ctx)

        # Grounding check for each item
        for item in extraction.items:
            verify_item_grounding(item, source_text=page_text)

        # Count cross-check if using LLM/hybrid
        if settings.extractor in ("hybrid", "llm"):
            try:
                rules_extraction = RulesExtractor().extract_page(ctx)
                if check_count_mismatch(len(extraction.items), len(rules_extraction.items)):
                    if "COUNT_MISMATCH" not in extraction.flags:
                        extraction.flags.append("COUNT_MISMATCH")
                    page.quality_flags.append(
                        {
                            "code": "COUNT_MISMATCH",
                            "severity": "warning",
                            "message": (
                                f"LLM items: {len(extraction.items)}, "
                                f"rules items: {len(rules_extraction.items)}"
                            ),
                        }
                    )
            except Exception as e:
                logger.debug("Count cross-check skipped due to error: %s", e)

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

        # Prepare input for stitcher
        pages_input: list[PageExtractionInput] = []
        for p in pages:
            if p.extraction:
                p_ext = PageExtraction.model_validate(p.extraction)
                for item in p_ext.items:
                    cleaned_lines = clean_page_lines(item.text.splitlines(), repeated_headers)
                    item.text = "\n".join(cleaned_lines).strip()
                pages_input.append(
                    PageExtractionInput(
                        page_no=p.page_no,
                        page_type=p.page_type or "questions",
                        section_heading=p.section_heading,
                        ocr_confidence=p.ocr_mean_conf,
                        text_source=p.text_source or "text_layer",
                        extraction=p_ext,
                    )
                )

        stitched_questions = stitch_document_extractions(pages_input)

        # 1. Extract and persist answer key entries from detected answer key pages
        session.execute(delete(AnswerKeyEntry).where(AnswerKeyEntry.document_id == doc_uuid))
        parsed_entries = []
        for p in pages:
            if (
                is_answer_key_page(p.page_type, p.raw_text or "", p.section_heading)
                or doc.role_hint == "answer_key"
            ):
                det_entries = parse_answer_key_text(
                    p.raw_text or "",
                    page_no=p.page_no,
                    initial_section=p.section_heading,
                )
                llm_raw_entries = []
                if p.extraction and isinstance(p.extraction, dict):
                    llm_raw_entries = p.extraction.get("answer_key_entries", [])
                merged_entries = merge_llm_answer_key_entries(
                    det_entries, llm_raw_entries, page_no=p.page_no
                )
                parsed_entries.extend(merged_entries)

        # 2. Detect and update document role
        doc.detected_role = detect_document_role(
            page_types=[p.page_type for p in pages],
            questions_count=len(stitched_questions),
            answer_keys_count=len(parsed_entries),
            role_hint=doc.role_hint,
        )

        saved_entries: list[AnswerKeyEntry] = []
        for pe in parsed_entries:
            ake = AnswerKeyEntry(
                id=uuid.uuid4(),
                document_id=doc_uuid,
                page_no=pe.page_no,
                section=pe.section,
                number_raw=pe.number_raw,
                number_norm=pe.number_norm,
                answer_raw=pe.answer_raw,
                answer_value=pe.answer_value,
                parse_confidence=pe.parse_confidence,
                match_status="unmatched",
            )
            session.add(ake)
            saved_entries.append(ake)
        session.flush()

        # 3. Load linked answer key entries if linked document exists
        links = (
            session.execute(
                select(DocumentLink).where(
                    (DocumentLink.from_document_id == doc_uuid)
                    | (DocumentLink.to_document_id == doc_uuid)
                )
            )
            .scalars()
            .all()
        )
        linked_key_doc_ids: set[uuid.UUID] = set()
        for lnk in links:
            if lnk.relation == "answer_key_for":
                if lnk.to_document_id == doc_uuid:
                    linked_key_doc_ids.add(lnk.from_document_id)
                elif lnk.from_document_id == doc_uuid:
                    linked_key_doc_ids.add(lnk.to_document_id)

        linked_entries: list[AnswerKeyEntry] = []
        if linked_key_doc_ids:
            linked_entries = list(
                session.execute(
                    select(AnswerKeyEntry).where(AnswerKeyEntry.document_id.in_(linked_key_doc_ids))
                )
                .scalars()
                .all()
            )

        # 4. Prepare question payloads for matching
        q_ids = [uuid.uuid4() for _ in stitched_questions]
        questions_payload = [
            {
                "id": q_ids[idx],
                "number_norm": q_data.number_norm,
                "section": q_data.section,
                "options": [opt.model_dump() for opt in q_data.options],
                "inline_answer_raw": q_data.inline_answer_raw,
                "source_pages": q_data.source_pages,
            }
            for idx, q_data in enumerate(stitched_questions)
        ]
        same_doc_payload = [
            {
                "id": e.id,
                "document_id": e.document_id,
                "page_no": e.page_no,
                "section": e.section,
                "number_norm": e.number_norm,
                "answer_raw": e.answer_raw,
                "answer_value": e.answer_value,
                "parse_confidence": e.parse_confidence,
            }
            for e in saved_entries
        ]
        linked_doc_payload = [
            {
                "id": e.id,
                "document_id": e.document_id,
                "page_no": e.page_no,
                "section": e.section,
                "number_norm": e.number_norm,
                "answer_raw": e.answer_raw,
                "answer_value": e.answer_value,
                "parse_confidence": e.parse_confidence,
            }
            for e in linked_entries
        ]

        match_results, entry_statuses = match_question_answers(
            questions=questions_payload,
            document_id=doc_uuid,
            same_doc_entries=same_doc_payload,
            linked_doc_entries=linked_doc_payload,
        )
        match_map = {r.question_id: r for r in match_results}

        # Preserve existing reviewed questions if reprocessing
        existing_reviewed_qs = (
            session.execute(
                select(Question).where(
                    Question.document_id == doc_uuid,
                    (Question.edited.is_(True))
                    | (Question.review_state.in_(["approved", "corrected"])),
                )
            )
            .scalars()
            .all()
        )
        reviewed_by_seq = {q.sequence: q for q in existing_reviewed_qs}

        # Idempotently delete previous warnings and questions
        session.execute(delete(Warning).where(Warning.document_id == doc_uuid))
        session.execute(delete(Question).where(Question.document_id == doc_uuid))

        # Add page-level warnings
        for p in pages:
            if p.status == "failed":
                session.add(
                    Warning(
                        document_id=doc.id,
                        page_no=p.page_no,
                        code="PAGE_FAILED",
                        severity="critical",
                        message=f"Page {p.page_no} processing failed: {p.error}",
                        details={"error": p.error},
                    )
                )
            for qf in p.quality_flags or []:
                code = qf.get("code", "UNKNOWN")
                sev = get_flag_severity(code)
                session.add(
                    Warning(
                        document_id=doc.id,
                        page_no=p.page_no,
                        code=code,
                        severity=sev,
                        message=qf.get("message", f"Page {p.page_no} quality flag: {code}"),
                        details=qf,
                    )
                )

        storage = get_storage()
        saved_questions = []
        for idx, q_data in enumerate(stitched_questions):
            q_id = q_ids[idx]
            match_res = match_map.get(q_id)
            if match_res:
                for flg in match_res.flags_to_add:
                    if flg not in q_data.flags:
                        q_data.flags.append(flg)

            first_page = q_data.source_pages[0] if q_data.source_pages else 1
            page_rec = next((p for p in pages if p.page_no == first_page), None)
            page_img = (
                storage.get_bytes_sync(page_rec.image_key)
                if (page_rec and page_rec.image_key)
                else None
            )

            assets_data, fig_flags = process_question_figures(
                question_id=q_id,
                owner_id=doc.owner_id,
                page_no=first_page,
                figures=q_data.figures,
                table_markdown=q_data.table_markdown,
                page_image_bytes=page_img,
                storage=storage,
            )
            for ff in fig_flags:
                if ff not in q_data.flags:
                    q_data.flags.append(ff)

            # Format structured flags for Question.flags and create Warning rows
            formatted_flags = []
            for flag_code in q_data.flags:
                sev = get_flag_severity(flag_code)
                formatted_flags.append(
                    {
                        "code": flag_code,
                        "severity": sev,
                        "message": f"Quality flag: {flag_code}",
                    }
                )

                session.add(
                    Warning(
                        document_id=doc.id,
                        question_id=q_id,
                        page_no=first_page,
                        code=flag_code,
                        severity=sev,
                        message=f"Quality flag {flag_code} detected on question {q_data.sequence}",
                        details={"sequence": q_data.sequence, "number": q_data.number_raw},
                    )
                )

            for asset in assets_data:
                session.add(
                    QuestionAsset(
                        id=asset["id"],
                        question_id=q_id,
                        kind=asset["kind"],
                        page_no=asset["page_no"],
                        bbox=asset["bbox"],
                        storage_key=asset["storage_key"],
                        table_markdown=asset["table_markdown"],
                        caption=asset["caption"],
                    )
                )

            # Check if this question was previously reviewed
            reviewed_prev = reviewed_by_seq.get(q_data.sequence)

            q = Question(
                id=q_id,
                document_id=doc.id,
                sequence=q_data.sequence,
                number_raw=reviewed_prev.number_raw if reviewed_prev else q_data.number_raw,
                number_norm=reviewed_prev.number_norm if reviewed_prev else q_data.number_norm,
                number_inferred=q_data.number_inferred,
                section=reviewed_prev.section if reviewed_prev else q_data.section,
                type=reviewed_prev.type if reviewed_prev else q_data.type,
                text=reviewed_prev.text if reviewed_prev else q_data.text,
                options=(
                    reviewed_prev.options
                    if reviewed_prev
                    else [opt.model_dump() for opt in q_data.options]
                ),
                source_pages=q_data.source_pages,
                source_bboxes=q_data.source_bboxes,
                extraction_method=settings.extractor,
                ocr_confidence=q_data.ocr_confidence,
                grounding_score=q_data.grounding_score,
                llm_self_confidence=q_data.llm_self_confidence,
                confidence=q_data.confidence,
                status="extracted" if reviewed_prev else q_data.status,
                flags=formatted_flags,
                answer_status=(
                    reviewed_prev.answer_status
                    if reviewed_prev
                    else (match_res.answer_status if match_res else "not_found")
                ),
                answer_value=(
                    reviewed_prev.answer_value
                    if reviewed_prev
                    else (match_res.answer_value if match_res else [])
                ),
                answer_raw=(
                    reviewed_prev.answer_raw
                    if reviewed_prev
                    else (match_res.answer_raw if match_res else None)
                ),
                answer_source=(
                    reviewed_prev.answer_source
                    if reviewed_prev
                    else (match_res.answer_source if match_res else {})
                ),
                answer_confidence=(
                    reviewed_prev.answer_confidence
                    if reviewed_prev
                    else (match_res.answer_confidence if match_res else None)
                ),
                review_state=reviewed_prev.review_state if reviewed_prev else "none",
                reviewed_by=reviewed_prev.reviewed_by if reviewed_prev else None,
                reviewed_at=reviewed_prev.reviewed_at if reviewed_prev else None,
                edited=reviewed_prev.edited if reviewed_prev else False,
            )

            session.add(q)
            saved_questions.append(q)

        # Update entry statuses and matched question links
        for e in saved_entries:
            if e.id in entry_statuses:
                e.match_status = entry_statuses[e.id]
        for e in linked_entries:
            if e.id in entry_statuses:
                e.match_status = entry_statuses[e.id]

        # Determine final status
        has_failed_pages = any(p.status == "failed" for p in pages)
        has_warnings = (
            any(
                q.status == "needs_review"
                or any(f.get("severity") in ("warning", "critical") for f in (q.flags or []))
                for q in saved_questions
            )
            or has_failed_pages
            or any((p.quality_flags or []) for p in pages)
        )

        if (
            len(stitched_questions) == 0
            and has_failed_pages
            and all(p.status == "failed" for p in pages)
        ):
            doc.status = "failed"
        elif has_warnings:
            doc.status = "completed_with_warnings"
        else:
            doc.status = "completed"

        doc.stage = "finalize"
        doc.progress_pct = 100
        doc.completed_at = datetime.now(UTC)

        q_count = len(stitched_questions)
        session.add(
            ProcessingEvent(
                document_id=doc.id,
                stage="finalize",
                status="completed",
                attempt=self.request.retries + 1,
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
                meta={"task_id": self.request.id, "questions_count": q_count},
            )
        )
        session.commit()

        # Check if this document is linked as an answer_key for other documents
        for lnk in links:
            if lnk.relation == "answer_key_for":
                target_doc_id = (
                    lnk.to_document_id if lnk.from_document_id == doc_uuid else lnk.from_document_id
                )
                reconcile_document_task.delay(str(target_doc_id))

        logger.info(
            "Document %s finalized: %d questions extracted, role: %s",
            document_id_str,
            q_count,
            doc.detected_role,
        )
        return {"status": "completed", "questions_count": q_count}
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


@celery.task(name="app.workers.tasks.reconcile_document_task", acks_late=True)
def reconcile_document_task(document_id_str: str) -> dict[str, Any]:
    """Sync celery task for running reconcile on a question document with linked answer keys."""
    doc_uuid = uuid.UUID(document_id_str)
    session = get_sync_db()

    try:
        doc = session.execute(select(Document).where(Document.id == doc_uuid)).scalar_one_or_none()
        if not doc:
            return {"status": "not_found", "document_id": document_id_str}

        links = (
            session.execute(
                select(DocumentLink).where(
                    (DocumentLink.from_document_id == doc_uuid)
                    | (DocumentLink.to_document_id == doc_uuid)
                )
            )
            .scalars()
            .all()
        )
        linked_key_doc_ids: set[uuid.UUID] = set()
        for lnk in links:
            if lnk.relation == "answer_key_for":
                if lnk.to_document_id == doc_uuid:
                    linked_key_doc_ids.add(lnk.from_document_id)
                elif lnk.from_document_id == doc_uuid:
                    linked_key_doc_ids.add(lnk.to_document_id)

        linked_entries: list[AnswerKeyEntry] = []
        if linked_key_doc_ids:
            linked_entries = list(
                session.execute(
                    select(AnswerKeyEntry).where(AnswerKeyEntry.document_id.in_(linked_key_doc_ids))
                )
                .scalars()
                .all()
            )

        same_doc_entries = list(
            session.execute(select(AnswerKeyEntry).where(AnswerKeyEntry.document_id == doc_uuid))
            .scalars()
            .all()
        )

        questions = list(
            session.execute(
                select(Question)
                .where(Question.document_id == doc_uuid)
                .order_by(Question.sequence.asc())
            )
            .scalars()
            .all()
        )

        questions_payload = [
            {
                "id": q.id,
                "number_norm": q.number_norm,
                "section": q.section,
                "options": q.options,
                "inline_answer_raw": (
                    q.answer_raw
                    if (q.answer_source and q.answer_source.get("kind") == "inline")
                    else None
                ),
                "source_pages": q.source_pages,
            }
            for q in questions
        ]
        same_doc_payload = [
            {
                "id": e.id,
                "document_id": e.document_id,
                "page_no": e.page_no,
                "section": e.section,
                "number_norm": e.number_norm,
                "answer_raw": e.answer_raw,
                "answer_value": e.answer_value,
                "parse_confidence": e.parse_confidence,
            }
            for e in same_doc_entries
        ]
        linked_doc_payload = [
            {
                "id": e.id,
                "document_id": e.document_id,
                "page_no": e.page_no,
                "section": e.section,
                "number_norm": e.number_norm,
                "answer_raw": e.answer_raw,
                "answer_value": e.answer_value,
                "parse_confidence": e.parse_confidence,
            }
            for e in linked_entries
        ]

        match_results, entry_statuses = match_question_answers(
            questions=questions_payload,
            document_id=doc_uuid,
            same_doc_entries=same_doc_payload,
            linked_doc_entries=linked_doc_payload,
        )
        match_map = {r.question_id: r for r in match_results}
        matched_count = 0

        for q in questions:
            res = match_map.get(q.id)
            if not res:
                continue

            q.answer_status = res.answer_status
            q.answer_value = res.answer_value
            q.answer_raw = res.answer_raw
            q.answer_source = res.answer_source
            q.answer_confidence = res.answer_confidence

            if res.answer_status == "matched":
                matched_count += 1

            existing_codes = {f.get("code") for f in (q.flags or []) if isinstance(f, dict)}
            for flg in res.flags_to_add:
                if flg not in existing_codes:
                    sev = "critical" if flg == "ANSWER_OUT_OF_RANGE" else "warning"
                    q.flags.append({"code": flg, "severity": sev, "message": f"Answer flag: {flg}"})

        for e in list(same_doc_entries) + list(linked_entries):
            if e.id in entry_statuses:
                e.match_status = entry_statuses[e.id]

        session.commit()
        logger.info(
            "Document %s reconciled: %d/%d questions matched",
            document_id_str,
            matched_count,
            len(questions),
        )
        return {
            "status": "reconciled",
            "document_id": document_id_str,
            "questions_matched": matched_count,
            "questions_total": len(questions),
        }
    finally:
        session.close()

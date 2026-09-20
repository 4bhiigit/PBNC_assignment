import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.answer_key import AnswerKeyEntryResponse
from app.api.v1.schemas.document import (
    DocumentExportResponse,
    PageQualityResponse,
)
from app.api.v1.schemas.question import (
    QuestionAnswerSchema,
    QuestionAssetSchema,
    QuestionExtractionSchema,
    QuestionFlagSchema,
    QuestionNumberSchema,
    QuestionOptionSchema,
    QuestionPatchRequest,
    QuestionResponse,
    QuestionReviewActionRequest,
    QuestionReviewSchema,
    QuestionSourceSchema,
    ReviewQueueItemResponse,
    ReviewQueueResponse,
)
from app.api.v1.schemas.warning import WarningItemResponse, WarningListResponse
from app.db.models.document import Document
from app.db.models.question import Question
from app.db.repositories.answer_key_repository import get_entries_by_document
from app.db.repositories.page_repo import list_pages_for_document
from app.db.repositories.question_repo import (
    create_question_revision,
    get_question_by_id,
    list_questions_for_document,
    list_review_queue_for_document,
    list_warnings_for_document,
)
from app.errors import NotFoundException
from app.pipeline.confidence import compute_item_confidence_and_status
from app.services.document_service import build_document_detail_response


def build_spec_question_response(q: Question) -> QuestionResponse:
    """Constructs a SPEC §14 compliant question response."""
    options = [
        QuestionOptionSchema(
            label=opt.get("label", ""),
            raw_label=opt.get("raw_label", ""),
            text=opt.get("text", ""),
        )
        for opt in (q.options or [])
    ]

    answer = QuestionAnswerSchema(
        status=q.answer_status or "not_found",
        value=q.answer_value or [],
        raw=q.answer_raw,
        source=q.answer_source or {},
        confidence=q.answer_confidence,
        candidates=[],
    )

    assets = [
        QuestionAssetSchema(
            id=asset.id,
            kind=asset.kind,
            page=asset.page_no,
            bbox=asset.bbox,
            url=f"/api/v1/assets/{asset.id}",
            table_markdown=asset.table_markdown,
            caption=asset.caption,
        )
        for asset in (getattr(q, "assets", []) or [])
    ]

    # Extract flag objects
    raw_flags = q.flags or []
    flags = []
    reasons = []
    for f in raw_flags:
        if isinstance(f, dict):
            code = f.get("code", "UNKNOWN")
            sev = f.get("severity", "warning")
            msg = f.get("message")
            flags.append(QuestionFlagSchema(code=code, severity=sev, message=msg))
            reasons.append(code)
        elif isinstance(f, str):
            flags.append(QuestionFlagSchema(code=f, severity="warning", message=f))
            reasons.append(f)

    if q.confidence < 0.60 and "LOW_CONFIDENCE" not in reasons:
        reasons.append("LOW_CONFIDENCE")

    review = QuestionReviewSchema(
        required=(q.status == "needs_review"),
        state=q.review_state or "none",
        reasons=reasons,
        reviewed_by=q.reviewed_by,
        reviewed_at=q.reviewed_at,
        edited=q.edited,
    )

    extraction = QuestionExtractionSchema(
        method=q.extraction_method or "rules",
        model=q.model_name,
        grounding_score=q.grounding_score,
        ocr_confidence=q.ocr_confidence,
    )

    source = QuestionSourceSchema(
        document_id=q.document_id,
        pages=q.source_pages or [],
        bbox_by_page=q.source_bboxes or {},
    )

    number = QuestionNumberSchema(
        raw=q.number_raw,
        normalized=q.number_norm,
        inferred=q.number_inferred,
    )

    return QuestionResponse(
        id=q.id,
        document_id=q.document_id,
        sequence=q.sequence,
        number=number,
        section=q.section,
        type=q.type,
        text=q.text,
        options=options,
        answer=answer,
        assets=assets,
        source=source,
        confidence=q.confidence,
        status=q.status,
        flags=flags,
        review=review,
        extraction=extraction,
        created_at=q.created_at,
    )


async def patch_question(
    db: AsyncSession,
    question_id: uuid.UUID,
    patch_req: QuestionPatchRequest,
    editor_id: uuid.UUID | None,
) -> QuestionResponse:
    """Applies human corrections to a question and creates an audit revision row."""
    q = await get_question_by_id(db, question_id)
    if not q:
        raise NotFoundException(f"Question {question_id} not found")

    before_snapshot: dict[str, Any] = {
        "text": q.text,
        "type": q.type,
        "section": q.section,
        "number_raw": q.number_raw,
        "number_norm": q.number_norm,
        "options": q.options,
        "answer_raw": q.answer_raw,
        "answer_value": q.answer_value,
        "answer_status": q.answer_status,
        "status": q.status,
        "confidence": q.confidence,
    }

    # Apply updates
    if patch_req.text is not None:
        q.text = patch_req.text
    if patch_req.type is not None:
        q.type = patch_req.type
    if patch_req.section is not None:
        q.section = patch_req.section
    if patch_req.number_raw is not None:
        q.number_raw = patch_req.number_raw
    if patch_req.number_norm is not None:
        q.number_norm = patch_req.number_norm
    if patch_req.options is not None:
        q.options = [opt.model_dump() for opt in patch_req.options]
    if patch_req.answer_raw is not None:
        q.answer_raw = patch_req.answer_raw
    if patch_req.answer_value is not None:
        q.answer_value = patch_req.answer_value
    if patch_req.answer_status is not None:
        q.answer_status = patch_req.answer_status

    q.edited = True
    q.review_state = "corrected"
    q.reviewed_by = editor_id
    q.reviewed_at = datetime.now(UTC)

    # Re-evaluate confidence and status with human correction
    flag_codes: list[str] = [
        str(f.get("code"))
        for f in (q.flags or [])
        if isinstance(f, dict) and f.get("code")
    ]
    # Remove critical completeness flags that were corrected
    if q.text and len(q.text.strip()) >= 5:
        flag_codes = [f for f in flag_codes if f != "MISSING_TEXT"]
    if q.type.startswith("mcq") and len(q.options or []) >= 2:
        flag_codes = [f for f in flag_codes if f != "MCQ_OPTIONS_LT_2"]

    new_conf, new_status, updated_flags = compute_item_confidence_and_status(
        text=q.text,
        question_type=q.type,
        options=q.options or [],
        number_norm=q.number_norm,
        flags=flag_codes,
        ocr_confidence=q.ocr_confidence,
        grounding_score=q.grounding_score,
        llm_self_confidence=q.llm_self_confidence,
    )
    # Corrected by human: if no critical flags remain, status becomes extracted
    has_crit = any(
        f in {"MISSING_TEXT", "MCQ_OPTIONS_LT_2", "LOW_GROUNDING", "ORPHAN_FRAGMENT"}
        for f in updated_flags
    )
    if not has_crit:
        q.status = "extracted"
    else:
        q.status = new_status
    q.confidence = new_conf

    after_snapshot: dict[str, Any] = {
        "text": q.text,
        "type": q.type,
        "section": q.section,
        "number_raw": q.number_raw,
        "number_norm": q.number_norm,
        "options": q.options,
        "answer_raw": q.answer_raw,
        "answer_value": q.answer_value,
        "answer_status": q.answer_status,
        "status": q.status,
        "confidence": q.confidence,
    }

    await create_question_revision(
        db=db,
        question_id=q.id,
        editor_id=editor_id,
        before_state=before_snapshot,
        after_state=after_snapshot,
    )

    await db.commit()
    await db.refresh(q)
    return build_spec_question_response(q)


async def review_question_decision(
    db: AsyncSession,
    question_id: uuid.UUID,
    review_req: QuestionReviewActionRequest,
    reviewer_id: uuid.UUID | None,
) -> QuestionResponse:
    """Applies a human review decision (approve, reject, or pending)."""
    q = await get_question_by_id(db, question_id)
    if not q:
        raise NotFoundException(f"Question {question_id} not found")

    if review_req.action == "approve":
        q.review_state = "approved"
        q.status = "extracted"
    elif review_req.action == "reject":
        q.review_state = "rejected"
    elif review_req.action == "pending":
        q.review_state = "pending"

    q.reviewed_by = reviewer_id
    q.reviewed_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(q)
    return build_spec_question_response(q)


async def get_document_review_queue(
    db: AsyncSession,
    doc_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
) -> ReviewQueueResponse:
    """Fetches questions in needs_review ordered by lowest confidence with reasons & page refs."""
    questions, total = await list_review_queue_for_document(
        db=db, doc_id=doc_id, limit=limit, offset=offset
    )

    items = []
    for q in questions:
        spec_q = build_spec_question_response(q)
        items.append(
            ReviewQueueItemResponse(
                question=spec_q,
                reasons=spec_q.review.reasons,
                page_refs=spec_q.source.pages,
            )
        )

    return ReviewQueueResponse(items=items, total=total, limit=limit, offset=offset)


async def get_document_warnings_response(
    db: AsyncSession,
    doc_id: uuid.UUID,
    severity: str | None = None,
    code: str | None = None,
    resolved: bool | None = None,
    question_id: uuid.UUID | None = None,
    limit: int = 100,
    offset: int = 0,
) -> WarningListResponse:
    """Returns paginated quality warnings for a document."""
    warnings, total = await list_warnings_for_document(
        db=db,
        doc_id=doc_id,
        severity=severity,
        code=code,
        resolved=resolved,
        question_id=question_id,
        limit=limit,
        offset=offset,
    )

    items = [
        WarningItemResponse(
            id=w.id,
            document_id=w.document_id,
            question_id=w.question_id,
            page_no=w.page_no,
            code=w.code,
            severity=w.severity,
            message=w.message,
            details=w.details or {},
            resolved=w.resolved,
            created_at=w.created_at,
        )
        for w in warnings
    ]

    return WarningListResponse(items=items, total=total, limit=limit, offset=offset)


async def build_document_export_response(
    db: AsyncSession, doc: Document
) -> DocumentExportResponse:
    """Builds a complete export JSON containing metadata, questions, answer key, and warnings."""
    doc_detail = await build_document_detail_response(db, doc)

    # Load all questions
    questions, _ = await list_questions_for_document(
        db=db, doc_id=doc.id, limit=1000, offset=0
    )
    spec_questions = [build_spec_question_response(q) for q in questions]

    # Load all answer key entries
    entries = await get_entries_by_document(db=db, document_id=doc.id)
    spec_entries = [
        AnswerKeyEntryResponse(
            id=e.id,
            document_id=e.document_id,
            page_no=e.page_no,
            section=e.section,
            number_raw=e.number_raw,
            number_norm=e.number_norm,
            answer_raw=e.answer_raw,
            answer_value=e.answer_value or [],
            parse_confidence=e.parse_confidence,
            match_status=e.match_status,
            matched_question_id=e.matched_question_id,
        )
        for e in entries
    ]

    # Load all warnings
    warnings, _ = await list_warnings_for_document(
        db=db, doc_id=doc.id, limit=1000, offset=0
    )
    spec_warnings = [
        WarningItemResponse(
            id=w.id,
            document_id=w.document_id,
            question_id=w.question_id,
            page_no=w.page_no,
            code=w.code,
            severity=w.severity,
            message=w.message,
            details=w.details or {},
            resolved=w.resolved,
            created_at=w.created_at,
        )
        for w in warnings
    ]

    return DocumentExportResponse(
        document=doc_detail,
        questions=spec_questions,
        answer_key=spec_entries,
        warnings=spec_warnings,
    )


async def build_page_quality_list(
    db: AsyncSession, doc_id: uuid.UUID
) -> list[PageQualityResponse]:
    """Builds list of page quality records for document."""
    pages = await list_pages_for_document(db, doc_id)
    return [
        PageQualityResponse(
            page_no=p.page_no,
            status=p.status,
            has_text_layer=p.has_text_layer,
            ocr_used=p.ocr_used,
            ocr_mean_conf=p.ocr_mean_conf,
            text_source=p.text_source,
            rotation_applied=p.rotation_applied or 0,
            deskew_angle=p.deskew_angle or 0.0,
            blur_score=p.blur_score or 0.0,
            effective_dpi=p.effective_dpi or 0,
            page_type=p.page_type,
            section_heading=p.section_heading,
            image_url=f"/api/v1/documents/{doc_id}/pages/{p.page_no}/image"
            if p.image_key
            else None,
            quality_flags=p.quality_flags or [],
        )
        for p in pages
    ]

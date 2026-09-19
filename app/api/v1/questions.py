import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.question import (
    QuestionAnswerResponse,
    QuestionListResponse,
    QuestionOptionResponse,
    QuestionResponse,
)
from app.db.models.document import Document
from app.db.models.question import Question
from app.db.models.user import User
from app.db.repositories.document_repo import get_document_by_id
from app.db.repositories.question_repo import get_question_by_id, list_questions_for_document
from app.db.session import get_db
from app.deps import get_current_user, get_owned_document
from app.errors import DocumentNotReadyException, NotFoundException

router = APIRouter(tags=["Questions"])


def build_question_response(q: Question) -> QuestionResponse:
    options = [
        QuestionOptionResponse(
            label=opt.get("label", ""),
            raw_label=opt.get("raw_label", ""),
            text=opt.get("text", ""),
        )
        for opt in (q.options or [])
    ]
    answer = QuestionAnswerResponse(
        status=q.answer_status or "not_found",
        value=q.answer_value or [],
        raw=q.answer_raw,
        source=q.answer_source or {},
        confidence=q.answer_confidence,
    )
    return QuestionResponse(
        id=q.id,
        document_id=q.document_id,
        sequence=q.sequence,
        number_raw=q.number_raw,
        number_norm=q.number_norm,
        number_inferred=q.number_inferred,
        section=q.section,
        type=q.type,
        text=q.text,
        options=options,
        source_pages=q.source_pages or [],
        extraction_method=q.extraction_method,
        ocr_confidence=q.ocr_confidence,
        confidence=q.confidence,
        status=q.status,
        flags=q.flags or [],
        answer=answer,
        created_at=q.created_at,
    )


@router.get("/documents/{id}/questions", response_model=QuestionListResponse)
async def get_document_questions(
    doc: Document = Depends(get_owned_document),
    status: str | None = Query(None, description="Filter by question status"),
    needs_review: bool | None = Query(None, description="Filter questions needing review"),
    answer_status: str | None = Query(None, description="Filter by answer status"),
    section: str | None = Query(None, description="Filter by section"),
    type: str | None = Query(None, description="Filter by question type"),
    min_confidence: float | None = Query(None, ge=0.0, le=1.0),
    max_confidence: float | None = Query(None, ge=0.0, le=1.0),
    sort: str = Query("sequence", pattern="^(sequence|confidence)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> QuestionListResponse:
    """Returns paginated questions extracted from a document."""
    if doc.status in ("queued", "processing"):
        raise DocumentNotReadyException(
            message=f"Document {doc.id} is still processing",
            details={
                "status": doc.status,
                "stage": doc.stage,
                "progress_pct": doc.progress_pct,
            },
        )

    items, total = await list_questions_for_document(
        db=db,
        doc_id=doc.id,
        status=status,
        needs_review=needs_review,
        answer_status=answer_status,
        section=section,
        question_type=type,
        min_confidence=min_confidence,
        max_confidence=max_confidence,
        sort_by=sort,
        limit=limit,
        offset=offset,
    )

    return QuestionListResponse(
        items=[build_question_response(q) for q in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/questions/{id}", response_model=QuestionResponse)
async def get_question(
    id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QuestionResponse:
    """Returns full details of an individual question."""
    q = await get_question_by_id(db, id)
    if not q:
        raise NotFoundException("Question not found")

    doc = await get_document_by_id(db, q.document_id)
    if not doc or (current_user.role != "admin" and doc.owner_id != current_user.id):
        raise NotFoundException("Question not found")

    return build_question_response(q)

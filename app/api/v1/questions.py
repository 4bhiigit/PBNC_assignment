import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.question import (
    QuestionListResponse,
    QuestionPatchRequest,
    QuestionResponse,
    QuestionReviewActionRequest,
)
from app.core.storage import get_storage
from app.db.models.document import Document
from app.db.models.user import User
from app.db.repositories.document_repo import get_document_by_id
from app.db.repositories.question_repo import (
    get_question_asset_by_id,
    get_question_by_id,
    list_questions_for_document,
)
from app.db.session import get_db
from app.deps import get_current_user, get_owned_document
from app.errors import DocumentNotReadyException, NotFoundException
from app.services.review_service import (
    build_spec_question_response,
    patch_question,
    review_question_decision,
)

router = APIRouter(tags=["Questions"])


@router.get(
    "/documents/{id}/questions",
    response_model=QuestionListResponse,
    summary="List extracted questions for a document with filtering and sorting",
)
async def get_document_questions(
    doc: Document = Depends(get_owned_document),
    status: str | None = Query(None, description="Filter by question status"),
    needs_review: bool | None = Query(None, description="Filter questions needing human review"),
    answer_status: str | None = Query(None, description="Filter by answer status"),
    page: int | None = Query(None, description="Filter by page number"),
    section: str | None = Query(None, description="Filter by section heading"),
    type: str | None = Query(None, description="Filter by question type"),
    min_confidence: float | None = Query(None, ge=0.0, le=1.0, description="Minimum confidence"),
    max_confidence: float | None = Query(None, ge=0.0, le=1.0, description="Maximum confidence"),
    sort: str = Query("sequence", pattern="^(sequence|confidence)$", description="Sort order"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> QuestionListResponse:
    """Returns paginated questions extracted from a document.

    Raises 409 DOCUMENT_NOT_READY if document is currently queued or processing.
    """
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
        page=page,
        section=section,
        question_type=type,
        min_confidence=min_confidence,
        max_confidence=max_confidence,
        sort_by=sort,
        limit=limit,
        offset=offset,
    )

    return QuestionListResponse(
        items=[build_spec_question_response(q) for q in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/questions/{id}",
    response_model=QuestionResponse,
    summary="Get full details of a specific question",
)
async def get_question(
    id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QuestionResponse:
    """Returns full details of an individual question with review state."""
    q = await get_question_by_id(db, id)
    if not q:
        raise NotFoundException("Question not found")

    doc = await get_document_by_id(db, q.document_id)
    if not doc or (current_user.role != "admin" and doc.owner_id != current_user.id):
        raise NotFoundException("Question not found")

    return build_spec_question_response(q)


@router.get(
    "/documents/{id}/questions/{qid}",
    response_model=QuestionResponse,
    summary="Get question by document ID and question ID",
)
async def get_document_question_by_id(
    qid: uuid.UUID,
    doc: Document = Depends(get_owned_document),
    db: AsyncSession = Depends(get_db),
) -> QuestionResponse:
    """Returns question details ensuring it belongs to the specified document."""
    q = await get_question_by_id(db, qid)
    if not q or q.document_id != doc.id:
        raise NotFoundException("Question not found in specified document")

    return build_spec_question_response(q)


@router.patch(
    "/questions/{id}",
    response_model=QuestionResponse,
    summary="Apply human correction to a question",
)
async def update_question(
    id: uuid.UUID,
    patch_req: QuestionPatchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QuestionResponse:
    """Applies human corrections to question and records an audit revision."""
    q = await get_question_by_id(db, id)
    if not q:
        raise NotFoundException("Question not found")

    doc = await get_document_by_id(db, q.document_id)
    if not doc or (current_user.role != "admin" and doc.owner_id != current_user.id):
        raise NotFoundException("Question not found")

    return await patch_question(
        db=db, question_id=id, patch_req=patch_req, editor_id=current_user.id
    )


@router.post(
    "/questions/{id}/review",
    response_model=QuestionResponse,
    summary="Submit a human review decision for a question",
)
async def submit_question_review(
    id: uuid.UUID,
    review_req: QuestionReviewActionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QuestionResponse:
    """Approve or reject an extracted question during human review."""
    q = await get_question_by_id(db, id)
    if not q:
        raise NotFoundException("Question not found")

    doc = await get_document_by_id(db, q.document_id)
    if not doc or (current_user.role != "admin" and doc.owner_id != current_user.id):
        raise NotFoundException("Question not found")

    return await review_question_decision(
        db=db, question_id=id, review_req=review_req, reviewer_id=current_user.id
    )


@router.get(
    "/assets/{id}",
    summary="Stream question asset image (figure / table)",
)
async def get_asset(
    id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Streams cropped figure or table image for a question."""
    asset = await get_question_asset_by_id(db, id)
    if not asset:
        raise NotFoundException("Asset not found")

    q = await get_question_by_id(db, asset.question_id)
    if not q:
        raise NotFoundException("Asset not found")

    doc = await get_document_by_id(db, q.document_id)
    if not doc or (current_user.role != "admin" and doc.owner_id != current_user.id):
        raise NotFoundException("Asset not found")

    storage = get_storage()
    stream = storage.get_stream(asset.storage_key)
    return StreamingResponse(stream, media_type="image/png")

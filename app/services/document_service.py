import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.document import (
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentStatusResponse,
    QuestionSummary,
)
from app.core.storage import get_storage
from app.db.models.document import Document
from app.db.repositories.document_repo import (
    get_question_counts,
    list_documents_for_user,
)


async def build_document_detail_response(db: AsyncSession, doc: Document) -> DocumentDetailResponse:
    counts = await get_question_counts(db, doc.id)
    summary = QuestionSummary(
        total=counts["total"],
        extracted=counts["extracted"],
        partial=counts["partial"],
        needs_review=counts["needs_review"],
    )
    return DocumentDetailResponse(
        id=doc.id,
        original_filename=doc.original_filename,
        mime_type=doc.mime_type,
        size_bytes=doc.size_bytes,
        page_count=doc.page_count,
        role_hint=doc.role_hint,
        detected_role=doc.detected_role,
        status=doc.status,
        stage=doc.stage,
        progress_pct=doc.progress_pct,
        pages_done=doc.pages_done,
        error_code=doc.error_code,
        error_message=doc.error_message,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        completed_at=doc.completed_at,
        summary=summary,
    )


async def get_document_status_response(doc: Document) -> DocumentStatusResponse:
    return DocumentStatusResponse(
        id=doc.id,
        status=doc.status,
        stage=doc.stage,
        progress_pct=doc.progress_pct,
        pages_done=doc.pages_done,
        page_count=doc.page_count,
        error=doc.error_message,
        updated_at=doc.updated_at,
    )


async def list_user_documents(
    db: AsyncSession,
    owner_id: uuid.UUID,
    status: str | None = None,
    role: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> DocumentListResponse:
    items, total = await list_documents_for_user(
        db=db, owner_id=owner_id, status=status, role=role, limit=limit, offset=offset
    )
    detail_items = [await build_document_detail_response(db, doc) for doc in items]
    return DocumentListResponse(
        items=detail_items,
        total=total,
        limit=limit,
        offset=offset,
    )


async def delete_document_record(db: AsyncSession, doc: Document) -> None:
    storage = get_storage()

    # 1. Delete physical storage file
    if doc.storage_key:
        try:
            await storage.delete(doc.storage_key)
        except Exception:
            pass

    # 2. Delete database record (cascades to pages, questions, assets, etc.)
    await db.delete(doc)
    await db.commit()

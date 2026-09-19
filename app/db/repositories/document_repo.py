import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.document import Document
from app.db.models.question import Question


async def get_document_by_id(db: AsyncSession, doc_id: uuid.UUID) -> Document | None:
    query = select(Document).where(Document.id == doc_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def get_document_by_id_and_owner(
    db: AsyncSession, doc_id: uuid.UUID, owner_id: uuid.UUID
) -> Document | None:
    query = select(Document).where(Document.id == doc_id, Document.owner_id == owner_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def find_duplicate_document(
    db: AsyncSession, owner_id: uuid.UUID, sha256_hash: str
) -> Document | None:
    query = select(Document).where(
        Document.owner_id == owner_id,
        Document.sha256 == sha256_hash,
        Document.status != "failed",
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def list_documents_for_user(
    db: AsyncSession,
    owner_id: uuid.UUID,
    status: str | None = None,
    role: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[Sequence[Document], int]:
    base_query = select(Document).where(Document.owner_id == owner_id)
    if status:
        base_query = base_query.where(Document.status == status)
    if role:
        base_query = base_query.where(Document.detected_role == role)

    # Total count query
    count_query = select(func.count()).select_from(base_query.subquery())
    total = (await db.execute(count_query)).scalar_one() or 0

    # Paginated ordered query
    query = base_query.order_by(Document.created_at.desc()).offset(offset).limit(limit)
    items = (await db.execute(query)).scalars().all()
    return items, total


async def get_question_counts(db: AsyncSession, doc_id: uuid.UUID) -> dict[str, int]:
    query = (
        select(Question.status, func.count(Question.id))
        .where(Question.document_id == doc_id)
        .group_by(Question.status)
    )
    results = (await db.execute(query)).all()
    counts = {"total": 0, "extracted": 0, "partial": 0, "needs_review": 0}
    for st, cnt in results:
        counts[st] = cnt
        counts["total"] += cnt
    return counts

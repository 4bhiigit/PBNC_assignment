import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.question import Question


async def get_question_by_id(db: AsyncSession, question_id: uuid.UUID) -> Question | None:
    query = select(Question).where(Question.id == question_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def list_questions_for_document(
    db: AsyncSession,
    doc_id: uuid.UUID,
    status: str | None = None,
    needs_review: bool | None = None,
    answer_status: str | None = None,
    section: str | None = None,
    question_type: str | None = None,
    min_confidence: float | None = None,
    max_confidence: float | None = None,
    sort_by: str = "sequence",
    limit: int = 50,
    offset: int = 0,
) -> tuple[Sequence[Question], int]:
    base_query = select(Question).where(Question.document_id == doc_id)

    if status:
        base_query = base_query.where(Question.status == status)
    if needs_review is True:
        base_query = base_query.where(Question.status == "needs_review")
    elif needs_review is False:
        base_query = base_query.where(Question.status != "needs_review")
    if answer_status:
        base_query = base_query.where(Question.answer_status == answer_status)
    if section:
        base_query = base_query.where(Question.section == section)
    if question_type:
        base_query = base_query.where(Question.type == question_type)
    if min_confidence is not None:
        base_query = base_query.where(Question.confidence >= min_confidence)
    if max_confidence is not None:
        base_query = base_query.where(Question.confidence <= max_confidence)

    count_query = select(func.count()).select_from(base_query.subquery())
    total = (await db.execute(count_query)).scalar_one() or 0

    if sort_by == "confidence":
        ordered = base_query.order_by(Question.confidence.desc(), Question.sequence.asc())
    else:
        ordered = base_query.order_by(Question.sequence.asc())

    query = ordered.offset(offset).limit(limit)
    items = (await db.execute(query)).scalars().all()
    return items, total

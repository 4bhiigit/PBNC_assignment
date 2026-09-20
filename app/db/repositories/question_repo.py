import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.question import Question
from app.db.models.question_asset import QuestionAsset
from app.db.models.question_revision import QuestionRevision
from app.db.models.warning import Warning


async def get_question_by_id(db: AsyncSession, question_id: uuid.UUID) -> Question | None:
    query = (
        select(Question)
        .options(selectinload(Question.assets), selectinload(Question.warnings))
        .where(Question.id == question_id)
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def list_questions_for_document(
    db: AsyncSession,
    doc_id: uuid.UUID,
    status: str | None = None,
    needs_review: bool | None = None,
    answer_status: str | None = None,
    page: int | None = None,
    section: str | None = None,
    question_type: str | None = None,
    min_confidence: float | None = None,
    max_confidence: float | None = None,
    sort_by: str = "sequence",
    limit: int = 50,
    offset: int = 0,
) -> tuple[Sequence[Question], int]:
    base_query = (
        select(Question)
        .options(selectinload(Question.assets), selectinload(Question.warnings))
        .where(Question.document_id == doc_id)
    )

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

    # Note: page filtering is done in Python if page filter is provided
    # (since source_pages is a JSON array)
    count_query = select(func.count()).select_from(base_query.subquery())
    total = (await db.execute(count_query)).scalar_one() or 0

    if sort_by == "confidence":
        ordered = base_query.order_by(Question.confidence.asc(), Question.sequence.asc())
    else:
        ordered = base_query.order_by(Question.sequence.asc())

    if page is not None:
        # Load all matching, filter by page in source_pages, then slice
        all_items = (await db.execute(ordered)).scalars().all()
        filtered = [q for q in all_items if page in (q.source_pages or [])]
        return filtered[offset : offset + limit], len(filtered)

    query = ordered.offset(offset).limit(limit)
    items = (await db.execute(query)).scalars().all()
    return items, total


async def list_review_queue_for_document(
    db: AsyncSession,
    doc_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
) -> tuple[Sequence[Question], int]:
    base_query = (
        select(Question)
        .options(selectinload(Question.assets), selectinload(Question.warnings))
        .where(
            Question.document_id == doc_id,
            (Question.status == "needs_review") | (Question.review_state == "pending"),
        )
    )

    count_query = select(func.count()).select_from(base_query.subquery())
    total = (await db.execute(count_query)).scalar_one() or 0

    ordered = base_query.order_by(Question.confidence.asc(), Question.sequence.asc())
    query = ordered.offset(offset).limit(limit)
    items = (await db.execute(query)).scalars().all()
    return items, total


async def list_warnings_for_document(
    db: AsyncSession,
    doc_id: uuid.UUID,
    severity: str | None = None,
    code: str | None = None,
    resolved: bool | None = None,
    question_id: uuid.UUID | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[Sequence[Warning], int]:
    base_query = select(Warning).where(Warning.document_id == doc_id)

    if severity:
        base_query = base_query.where(Warning.severity == severity)
    if code:
        base_query = base_query.where(Warning.code == code)
    if resolved is not None:
        base_query = base_query.where(Warning.resolved == resolved)
    if question_id:
        base_query = base_query.where(Warning.question_id == question_id)

    count_query = select(func.count()).select_from(base_query.subquery())
    total = (await db.execute(count_query)).scalar_one() or 0

    query = (
        base_query.order_by(Warning.page_no.asc().nulls_last(), Warning.created_at.asc())
        .offset(offset)
        .limit(limit)
    )
    items = (await db.execute(query)).scalars().all()
    return items, total


async def get_question_asset_by_id(db: AsyncSession, asset_id: uuid.UUID) -> QuestionAsset | None:
    query = select(QuestionAsset).where(QuestionAsset.id == asset_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def create_question_revision(
    db: AsyncSession,
    question_id: uuid.UUID,
    editor_id: uuid.UUID | None,
    before_state: dict[str, Any],
    after_state: dict[str, Any],
) -> QuestionRevision:
    revision = QuestionRevision(
        id=uuid.uuid4(),
        question_id=question_id,
        editor_id=editor_id,
        before=before_state,
        after=after_state,
    )
    db.add(revision)
    return revision

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.answer_key import AnswerKeyEntry


async def get_entries_by_document(
    db: AsyncSession, document_id: uuid.UUID
) -> Sequence[AnswerKeyEntry]:
    query = (
        select(AnswerKeyEntry)
        .where(AnswerKeyEntry.document_id == document_id)
        .order_by(AnswerKeyEntry.page_no.asc(), AnswerKeyEntry.number_norm.asc())
    )
    result = await db.execute(query)
    return result.scalars().all()


async def get_unmatched_entries_by_document(
    db: AsyncSession, document_id: uuid.UUID
) -> Sequence[AnswerKeyEntry]:
    query = (
        select(AnswerKeyEntry)
        .where(
            AnswerKeyEntry.document_id == document_id,
            AnswerKeyEntry.match_status.in_(["unmatched", "ambiguous", "duplicate"]),
        )
        .order_by(AnswerKeyEntry.page_no.asc(), AnswerKeyEntry.number_norm.asc())
    )
    result = await db.execute(query)
    return result.scalars().all()


async def get_answer_key_summary(db: AsyncSession, document_id: uuid.UUID) -> dict[str, int]:
    query = (
        select(AnswerKeyEntry.match_status, func.count(AnswerKeyEntry.id))
        .where(AnswerKeyEntry.document_id == document_id)
        .group_by(AnswerKeyEntry.match_status)
    )
    result = await db.execute(query)
    counts = {"total": 0, "matched": 0, "unmatched": 0, "ambiguous": 0, "conflict": 0, "invalid": 0}
    for status, count in result.all():
        counts[status] = count
        counts["total"] += count
    return counts

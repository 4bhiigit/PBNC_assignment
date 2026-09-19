import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.page import Page


async def get_page_by_doc_and_no(db: AsyncSession, doc_id: uuid.UUID, page_no: int) -> Page | None:
    query = select(Page).where(Page.document_id == doc_id, Page.page_no == page_no)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def list_pages_for_document(db: AsyncSession, doc_id: uuid.UUID) -> Sequence[Page]:
    query = select(Page).where(Page.document_id == doc_id).order_by(Page.page_no.asc())
    result = await db.execute(query)
    return result.scalars().all()

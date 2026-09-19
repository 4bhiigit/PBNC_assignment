import uuid
from collections.abc import Sequence

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.document_link import DocumentLink


async def get_links_for_document(
    db: AsyncSession, document_id: uuid.UUID
) -> Sequence[DocumentLink]:
    query = (
        select(DocumentLink)
        .where(
            or_(
                DocumentLink.from_document_id == document_id,
                DocumentLink.to_document_id == document_id,
            )
        )
        .order_by(DocumentLink.created_at.desc())
    )
    result = await db.execute(query)
    return result.scalars().all()


async def get_link_by_id(db: AsyncSession, link_id: uuid.UUID) -> DocumentLink | None:
    query = select(DocumentLink).where(DocumentLink.id == link_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def find_link(
    db: AsyncSession,
    from_id: uuid.UUID,
    to_id: uuid.UUID,
    relation: str,
) -> DocumentLink | None:
    query = select(DocumentLink).where(
        DocumentLink.from_document_id == from_id,
        DocumentLink.to_document_id == to_id,
        DocumentLink.relation == relation,
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def create_document_link(
    db: AsyncSession,
    from_id: uuid.UUID,
    to_id: uuid.UUID,
    relation: str,
    origin: str = "user",
) -> DocumentLink:
    link = DocumentLink(
        from_document_id=from_id,
        to_document_id=to_id,
        relation=relation,
        origin=origin,
    )
    db.add(link)
    await db.flush()
    await db.refresh(link)
    return link

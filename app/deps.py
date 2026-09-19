import uuid

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.models.document import Document
from app.db.models.user import User
from app.db.repositories.document_repo import get_document_by_id
from app.db.session import get_db
from app.errors import ForbiddenException, NotFoundException, UnauthenticatedException


async def get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthenticatedException("Missing or malformed Authorization header")

    token = authorization.split(" ", 1)[1].strip()
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise UnauthenticatedException("Invalid or expired authentication token")

    try:
        user_id = uuid.UUID(payload["sub"])
    except (ValueError, TypeError):
        raise UnauthenticatedException("Invalid subject identifier in token") from None

    query = select(User).where(User.id == user_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise UnauthenticatedException("User account not found or inactive")

    return user


async def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != "admin":
        raise ForbiddenException("Administrator privileges required")
    return current_user


async def get_owned_document(
    id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Document:
    doc = await get_document_by_id(db, id)
    if not doc:
        raise NotFoundException("Document not found")

    # Strict owner-scoping: foreign IDs return 404 Not Found to prevent enumeration
    if current_user.role != "admin" and doc.owner_id != current_user.id:
        raise NotFoundException("Document not found")

    return doc

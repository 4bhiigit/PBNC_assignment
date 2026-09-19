import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.answer_key import DocumentAnswerKeyResponse
from app.db.models.user import User
from app.db.session import get_db
from app.deps import get_current_user
from app.services.answer_key_service import get_document_answer_key

router = APIRouter(tags=["answer-keys"])


@router.get(
    "/documents/{document_id}/answer-key",
    response_model=DocumentAnswerKeyResponse,
    summary="Get document answer key entries and summary",
    description=(
        "Returns all parsed answer key entries, unmatched entries, "
        "and match status summary counts."
    ),
)
async def get_answer_key(
    document_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentAnswerKeyResponse:
    return await get_document_answer_key(
        db=db,
        document_id=document_id,
        owner_id=user.id,
    )

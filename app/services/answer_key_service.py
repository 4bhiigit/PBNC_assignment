import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.answer_key import (
    AnswerKeyEntryResponse,
    AnswerKeySummaryResponse,
    DocumentAnswerKeyResponse,
)
from app.db.repositories.answer_key_repository import (
    get_answer_key_summary,
    get_entries_by_document,
    get_unmatched_entries_by_document,
)
from app.db.repositories.document_repo import get_document_by_id_and_owner
from app.errors import NotFoundException


async def get_document_answer_key(
    db: AsyncSession,
    document_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> DocumentAnswerKeyResponse:
    """Retrieves all answer key entries, unmatched entries, and summary counts for a document."""
    doc = await get_document_by_id_and_owner(db, document_id, owner_id)
    if not doc:
        raise NotFoundException(f"Document {document_id} not found")

    entries = await get_entries_by_document(db, document_id)
    unmatched = await get_unmatched_entries_by_document(db, document_id)
    summary_counts = await get_answer_key_summary(db, document_id)

    summary = AnswerKeySummaryResponse(
        total=summary_counts.get("total", 0),
        matched=summary_counts.get("matched", 0),
        unmatched=summary_counts.get("unmatched", 0),
        ambiguous=summary_counts.get("ambiguous", 0),
        conflict=summary_counts.get("conflict", 0),
        invalid=summary_counts.get("invalid", 0),
    )

    return DocumentAnswerKeyResponse(
        document_id=document_id,
        detected_role=doc.detected_role,
        summary=summary,
        entries=[AnswerKeyEntryResponse.model_validate(e) for e in entries],
        unmatched_entries=[AnswerKeyEntryResponse.model_validate(e) for e in unmatched],
    )

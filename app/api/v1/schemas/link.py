import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CreateLinkRequest(BaseModel):
    to_document_id: uuid.UUID
    relation: Literal["answer_key_for", "continuation_of", "related"]


class DocumentLinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    from_document_id: uuid.UUID
    to_document_id: uuid.UUID
    relation: str
    origin: str
    created_at: datetime


class ReconcileResponse(BaseModel):
    document_id: uuid.UUID
    status: str
    questions_matched: int
    questions_total: int
    reconciled_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

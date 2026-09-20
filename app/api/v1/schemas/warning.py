from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class WarningItemResponse(BaseModel):
    id: UUID
    document_id: UUID
    question_id: UUID | None = None
    page_no: int | None = None
    code: str
    severity: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    resolved: bool = False
    created_at: datetime


class WarningListResponse(BaseModel):
    items: list[WarningItemResponse]
    total: int
    limit: int
    offset: int

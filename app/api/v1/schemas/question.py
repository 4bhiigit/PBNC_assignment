from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class QuestionOptionResponse(BaseModel):
    label: str
    raw_label: str
    text: str


class QuestionAnswerResponse(BaseModel):
    status: str = "not_found"
    value: list[str] = Field(default_factory=list)
    raw: str | None = None
    source: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = None


class QuestionResponse(BaseModel):
    id: UUID
    document_id: UUID
    sequence: int
    number_raw: str | None = None
    number_norm: str | None = None
    number_inferred: bool = False
    section: str | None = None
    type: str
    text: str
    options: list[QuestionOptionResponse] = Field(default_factory=list)
    source_pages: list[int] = Field(default_factory=list)
    extraction_method: str
    ocr_confidence: float | None = None
    confidence: float = 1.0
    status: str
    flags: list[dict[str, Any]] = Field(default_factory=list)
    answer: QuestionAnswerResponse
    created_at: datetime


class QuestionListResponse(BaseModel):
    items: list[QuestionResponse]
    total: int
    limit: int
    offset: int

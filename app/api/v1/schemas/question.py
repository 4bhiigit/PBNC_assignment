from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class QuestionNumberSchema(BaseModel):
    raw: str | None = None
    normalized: str | None = None
    inferred: bool = False


class QuestionOptionSchema(BaseModel):
    label: str
    raw_label: str
    text: str


class QuestionAnswerSchema(BaseModel):
    status: str = "not_found"
    value: list[str] = Field(default_factory=list)
    raw: str | None = None
    source: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = None
    candidates: list[dict[str, Any]] = Field(default_factory=list)


class QuestionAssetSchema(BaseModel):
    id: UUID
    kind: str
    page: int
    bbox: list[float] | None = None
    url: str
    table_markdown: str | None = None
    caption: str | None = None


class QuestionSourceSchema(BaseModel):
    document_id: UUID
    pages: list[int] = Field(default_factory=list)
    bbox_by_page: dict[str, Any] = Field(default_factory=dict)


class QuestionFlagSchema(BaseModel):
    code: str
    severity: str
    message: str | None = None


class QuestionReviewSchema(BaseModel):
    required: bool = False
    state: str = "none"
    reasons: list[str] = Field(default_factory=list)
    reviewed_by: UUID | None = None
    reviewed_at: datetime | None = None
    edited: bool = False


class QuestionExtractionSchema(BaseModel):
    method: str = "rules"
    model: str | None = None
    grounding_score: float | None = None
    ocr_confidence: float | None = None


class QuestionResponse(BaseModel):
    id: UUID
    document_id: UUID
    sequence: int
    number: QuestionNumberSchema
    section: str | None = None
    type: str
    text: str
    options: list[QuestionOptionSchema] = Field(default_factory=list)
    answer: QuestionAnswerSchema
    assets: list[QuestionAssetSchema] = Field(default_factory=list)
    source: QuestionSourceSchema
    confidence: float
    status: str
    flags: list[QuestionFlagSchema] = Field(default_factory=list)
    review: QuestionReviewSchema
    extraction: QuestionExtractionSchema
    created_at: datetime


class QuestionListResponse(BaseModel):
    items: list[QuestionResponse]
    total: int
    limit: int
    offset: int


class QuestionPatchRequest(BaseModel):
    text: str | None = None
    type: str | None = None
    section: str | None = None
    number_raw: str | None = None
    number_norm: str | None = None
    options: list[QuestionOptionSchema] | None = None
    answer_raw: str | None = None
    answer_value: list[str] | None = None
    answer_status: str | None = None


class QuestionReviewActionRequest(BaseModel):
    action: str = Field(..., pattern="^(approve|reject|pending)$")
    notes: str | None = None


class ReviewQueueItemResponse(BaseModel):
    question: QuestionResponse
    reasons: list[str]
    page_refs: list[int]


class ReviewQueueResponse(BaseModel):
    items: list[ReviewQueueItemResponse]
    total: int
    limit: int
    offset: int

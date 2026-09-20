import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.api.v1.schemas.answer_key import AnswerKeyEntryResponse
from app.api.v1.schemas.question import QuestionResponse
from app.api.v1.schemas.warning import WarningItemResponse


class DocumentUploadResponse(BaseModel):
    id: uuid.UUID = Field(..., examples=["a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d"])
    status: str = Field("queued", examples=["queued"])
    links: dict[str, str] = Field(
        ...,
        examples=[
            {
                "status": "/api/v1/documents/a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d/status",
                "self": "/api/v1/documents/a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
            }
        ],
    )


class QuestionSummary(BaseModel):
    total: int = 0
    extracted: int = 0
    partial: int = 0
    needs_review: int = 0


class DocumentDetailResponse(BaseModel):
    id: uuid.UUID
    original_filename: str
    mime_type: str
    size_bytes: int
    page_count: int
    role_hint: str | None = None
    detected_role: str | None = None
    status: str
    stage: str | None = None
    progress_pct: int
    pages_done: int
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    summary: QuestionSummary = Field(default_factory=QuestionSummary)

    model_config = {"from_attributes": True}


class DocumentStatusResponse(BaseModel):
    id: uuid.UUID
    status: str
    stage: str | None = None
    progress_pct: int
    pages_done: int
    page_count: int
    error: str | None = None
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    items: list[DocumentDetailResponse]
    total: int
    limit: int
    offset: int


class PageQualityResponse(BaseModel):
    page_no: int
    status: str
    has_text_layer: bool
    ocr_used: bool
    ocr_mean_conf: float | None = None
    text_source: str | None = None
    rotation_applied: int = 0
    deskew_angle: float = 0.0
    blur_score: float = 0.0
    effective_dpi: int = 0
    page_type: str | None = None
    section_heading: str | None = None
    image_url: str | None = None
    quality_flags: list[dict[str, Any]] = Field(default_factory=list)


class PageListResponse(BaseModel):
    items: list[PageQualityResponse]
    total: int


class DocumentExportResponse(BaseModel):
    document: DocumentDetailResponse
    questions: list[QuestionResponse]
    answer_key: list[AnswerKeyEntryResponse] = Field(default_factory=list)
    warnings: list[WarningItemResponse] = Field(default_factory=list)


class ReprocessRequest(BaseModel):
    overwrite_reviewed: bool = False

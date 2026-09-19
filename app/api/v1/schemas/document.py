import uuid
from datetime import datetime

from pydantic import BaseModel, Field


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

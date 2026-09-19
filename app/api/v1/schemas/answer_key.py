import uuid

from pydantic import BaseModel, ConfigDict, Field


class AnswerKeyEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    page_no: int
    section: str | None = None
    number_raw: str
    number_norm: str | None = None
    answer_raw: str
    answer_value: list[str] = Field(default_factory=list)
    parse_confidence: float = 1.0
    match_status: str = "unmatched"
    matched_question_id: uuid.UUID | None = None


class AnswerKeySummaryResponse(BaseModel):
    total: int = 0
    matched: int = 0
    unmatched: int = 0
    ambiguous: int = 0
    conflict: int = 0
    invalid: int = 0


class DocumentAnswerKeyResponse(BaseModel):
    document_id: uuid.UUID
    detected_role: str | None = None
    summary: AnswerKeySummaryResponse
    entries: list[AnswerKeyEntryResponse] = Field(default_factory=list)
    unmatched_entries: list[AnswerKeyEntryResponse] = Field(default_factory=list)

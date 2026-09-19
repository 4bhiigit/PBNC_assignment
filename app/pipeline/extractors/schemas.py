from uuid import UUID

from pydantic import BaseModel, Field


class PageContext(BaseModel):
    """Context passed to extractors for a single page."""

    document_id: UUID
    page_no: int
    total_pages: int
    text: str
    text_source: str = "text_layer"  # "text_layer", "ocr", "empty"
    image_bytes: bytes | None = None
    ocr_confidence: float | None = None
    prev_page_context: str | None = None


class ExtractedOption(BaseModel):
    """Normalized option item."""

    label: str  # "A", "B", "C", "D"...
    raw_label: str  # "(a)", "1)", "[A]", etc.
    text: str


class ExtractedFigure(BaseModel):
    """Figure or diagram detected on a page."""

    bbox_norm: list[float] = Field(default_factory=list)  # [y0, x0, y1, x1]
    caption: str | None = None


class ExtractedItem(BaseModel):
    """Extracted question or prompt candidate from a page."""

    number_raw: str | None = None
    number_norm: str | None = None
    text: str
    options: list[ExtractedOption] = Field(default_factory=list)
    question_type: str = "unknown"
    starts_on_previous_page: bool = False
    continues_on_next_page: bool = False
    figures: list[ExtractedFigure] = Field(default_factory=list)
    table_markdown: str | None = None
    inline_answer_raw: str | None = None
    self_confidence: float = 1.0
    notes: str | None = None


class AnswerKeyItem(BaseModel):
    """Answer key row or entry detected on a page."""

    section: str | None = None
    number_raw: str
    answer_raw: str


class PageExtraction(BaseModel):
    """Full extraction result for a single page."""

    # "questions", "answer_key", "instructions", "passage", "mixed", "other"
    page_type: str = "questions"
    section_heading: str | None = None
    items: list[ExtractedItem] = Field(default_factory=list)
    answer_key_entries: list[AnswerKeyItem] = Field(default_factory=list)

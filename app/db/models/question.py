import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import GUID, Base, utc_now


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    number_raw: Mapped[str | None] = mapped_column(String(64), nullable=True)
    number_norm: Mapped[str | None] = mapped_column(String(64), nullable=True)
    number_inferred: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    section: Mapped[str | None] = mapped_column(String(255), nullable=True)
    type: Mapped[str] = mapped_column(String(64), default="unknown", nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)

    source_pages: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    source_bboxes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    extraction_method: Mapped[str] = mapped_column(String(64), default="rules", nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    grounding_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    llm_self_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    status: Mapped[str] = mapped_column(String(64), default="extracted", nullable=False)
    flags: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)

    answer_status: Mapped[str] = mapped_column(String(64), default="not_found", nullable=False)
    answer_value: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    answer_raw: Mapped[str | None] = mapped_column(String(512), nullable=True)
    answer_source: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    answer_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    review_state: Mapped[str] = mapped_column(String(64), default="none", nullable=False)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    document = relationship("Document", back_populates="questions")
    revisions = relationship(
        "QuestionRevision", back_populates="question", cascade="all, delete-orphan"
    )
    assets = relationship("QuestionAsset", back_populates="question", cascade="all, delete-orphan")
    warnings = relationship("Warning", back_populates="question", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_questions_doc_seq", "document_id", "sequence"),
        Index("ix_questions_doc_status", "document_id", "status"),
        Index("ix_questions_doc_confidence", "document_id", "confidence"),
    )

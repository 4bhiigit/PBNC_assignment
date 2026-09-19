import uuid

from sqlalchemy import JSON, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import GUID, Base


class AnswerKeyEntry(Base):
    __tablename__ = "answer_key_entries"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_no: Mapped[int] = mapped_column(Integer, nullable=False)
    section: Mapped[str | None] = mapped_column(String(255), nullable=True)
    number_raw: Mapped[str] = mapped_column(String(64), nullable=False)
    number_norm: Mapped[str | None] = mapped_column(String(64), nullable=True)
    answer_raw: Mapped[str] = mapped_column(String(512), nullable=False)
    answer_value: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    parse_confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    match_status: Mapped[str] = mapped_column(String(32), default="unmatched", nullable=False)

    matched_question_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("questions.id", ondelete="SET NULL"), nullable=True, index=True
    )

    document = relationship("Document", back_populates="answer_key_entries")

    __table_args__ = (
        Index("ix_answer_key_doc_norm", "document_id", "number_norm"),
        Index("ix_answer_key_doc_match", "document_id", "match_status"),
    )

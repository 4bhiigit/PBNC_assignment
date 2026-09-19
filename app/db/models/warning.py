import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import GUID, Base, utc_now


class Warning(Base):
    __tablename__ = "warnings"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("questions.id", ondelete="CASCADE"), nullable=True, index=True
    )
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)

    code: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), default="warning", nullable=False)
    message: Mapped[str] = mapped_column(String(512), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    document = relationship("Document", back_populates="warnings")
    question = relationship("Question", back_populates="warnings")

    __table_args__ = (
        Index("ix_warnings_doc_code", "document_id", "code"),
        Index("ix_warnings_doc_sev", "document_id", "severity"),
    )

import uuid
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import GUID, Base


class Page(Base):
    __tablename__ = "pages"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)

    has_text_layer: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ocr_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ocr_mean_conf: Mapped[float | None] = mapped_column(Float, nullable=True)
    text_source: Mapped[str | None] = mapped_column(String(32), nullable=True)

    rotation_applied: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deskew_angle: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    blur_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    effective_dpi: Mapped[int | None] = mapped_column(Integer, nullable=True)

    page_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    section_heading: Mapped[str | None] = mapped_column(String(255), nullable=True)
    image_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    extraction: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    quality_flags: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)

    document = relationship("Document", back_populates="pages")

    __table_args__ = (
        UniqueConstraint("document_id", "page_no", name="uq_pages_document_page_no"),
        Index("ix_pages_doc_page", "document_id", "page_no"),
    )

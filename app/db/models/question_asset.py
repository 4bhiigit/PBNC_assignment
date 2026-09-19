import uuid

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import GUID, Base


class QuestionAsset(Base):
    __tablename__ = "question_assets"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    question_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    page_no: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    table_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    caption: Mapped[str | None] = mapped_column(String(512), nullable=True)

    question = relationship("Question", back_populates="assets")

    __table_args__ = (Index("ix_question_assets_q_kind", "question_id", "kind"),)

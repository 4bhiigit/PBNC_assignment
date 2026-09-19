"""initial schema for document intelligence service

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-09-19 21:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. users table
    op.create_table(
        "users",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), server_default="user", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # 2. documents table
    op.create_table(
        "documents",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("owner_id", sa.CHAR(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("mime_type", sa.String(128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("page_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("role_hint", sa.String(64), nullable=True),
        sa.Column("detected_role", sa.String(64), nullable=True),
        sa.Column("status", sa.String(64), server_default="queued", nullable=False),
        sa.Column("stage", sa.String(64), nullable=True),
        sa.Column("progress_pct", sa.Integer(), server_default="0", nullable=False),
        sa.Column("pages_done", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.String(1024), nullable=True),
        sa.Column("finalize_enqueued", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_documents_owner_id", "documents", ["owner_id"])
    op.create_index("ix_documents_sha256", "documents", ["sha256"])
    op.create_index("ix_documents_status", "documents", ["status"])
    op.create_index("ix_documents_owner_created", "documents", ["owner_id", "created_at"])
    op.create_index("ix_documents_status_created", "documents", ["status", "created_at"])

    # 3. document_links table
    op.create_table(
        "document_links",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("from_document_id", sa.CHAR(36), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("to_document_id", sa.CHAR(36), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relation", sa.String(64), nullable=False),
        sa.Column("origin", sa.String(32), server_default="user", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("from_document_id", "to_document_id", "relation", name="uq_document_links_from_to_relation"),
    )
    op.create_index("ix_document_links_from_relation", "document_links", ["from_document_id", "relation"])
    op.create_index("ix_document_links_to_relation", "document_links", ["to_document_id", "relation"])

    # 4. pages table
    op.create_table(
        "pages",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("document_id", sa.CHAR(36), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), server_default="pending", nullable=False),
        sa.Column("has_text_layer", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("ocr_used", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("ocr_mean_conf", sa.Float(), nullable=True),
        sa.Column("text_source", sa.String(32), nullable=True),
        sa.Column("rotation_applied", sa.Integer(), server_default="0", nullable=False),
        sa.Column("deskew_angle", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("blur_score", sa.Float(), nullable=True),
        sa.Column("effective_dpi", sa.Integer(), nullable=True),
        sa.Column("page_type", sa.String(64), nullable=True),
        sa.Column("section_heading", sa.String(255), nullable=True),
        sa.Column("image_key", sa.String(512), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("extraction", sa.JSON(), nullable=True),
        sa.Column("error", sa.String(1024), nullable=True),
        sa.Column("quality_flags", sa.JSON(), nullable=False),
        sa.UniqueConstraint("document_id", "page_no", name="uq_pages_document_page_no"),
    )
    op.create_index("ix_pages_doc_page", "pages", ["document_id", "page_no"])

    # 5. questions table
    op.create_table(
        "questions",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("document_id", sa.CHAR(36), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("number_raw", sa.String(64), nullable=True),
        sa.Column("number_norm", sa.String(64), nullable=True),
        sa.Column("number_inferred", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("section", sa.String(255), nullable=True),
        sa.Column("type", sa.String(64), server_default="unknown", nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("source_pages", sa.JSON(), nullable=False),
        sa.Column("source_bboxes", sa.JSON(), nullable=False),
        sa.Column("extraction_method", sa.String(64), server_default="rules", nullable=False),
        sa.Column("model_name", sa.String(128), nullable=True),
        sa.Column("ocr_confidence", sa.Float(), nullable=True),
        sa.Column("grounding_score", sa.Float(), nullable=True),
        sa.Column("llm_self_confidence", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), server_default="1.0", nullable=False),
        sa.Column("status", sa.String(64), server_default="extracted", nullable=False),
        sa.Column("flags", sa.JSON(), nullable=False),
        sa.Column("answer_status", sa.String(64), server_default="not_found", nullable=False),
        sa.Column("answer_value", sa.JSON(), nullable=False),
        sa.Column("answer_raw", sa.String(512), nullable=True),
        sa.Column("answer_source", sa.JSON(), nullable=False),
        sa.Column("answer_confidence", sa.Float(), nullable=True),
        sa.Column("review_state", sa.String(64), server_default="none", nullable=False),
        sa.Column("reviewed_by", sa.CHAR(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("edited", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_questions_doc_seq", "questions", ["document_id", "sequence"])
    op.create_index("ix_questions_doc_status", "questions", ["document_id", "status"])
    op.create_index("ix_questions_doc_confidence", "questions", ["document_id", "confidence"])

    # 6. question_revisions table
    op.create_table(
        "question_revisions",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("question_id", sa.CHAR(36), sa.ForeignKey("questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("editor_id", sa.CHAR(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("before", sa.JSON(), nullable=False),
        sa.Column("after", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_question_revisions_q_created", "question_revisions", ["question_id", "created_at"])

    # 7. question_assets table
    op.create_table(
        "question_assets",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("question_id", sa.CHAR(36), sa.ForeignKey("questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("page_no", sa.Integer(), nullable=False),
        sa.Column("bbox", sa.JSON(), nullable=True),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("table_markdown", sa.Text(), nullable=True),
        sa.Column("caption", sa.String(512), nullable=True),
    )
    op.create_index("ix_question_assets_q_kind", "question_assets", ["question_id", "kind"])

    # 8. answer_key_entries table
    op.create_table(
        "answer_key_entries",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("document_id", sa.CHAR(36), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_no", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(255), nullable=True),
        sa.Column("number_raw", sa.String(64), nullable=False),
        sa.Column("number_norm", sa.String(64), nullable=True),
        sa.Column("answer_raw", sa.String(512), nullable=False),
        sa.Column("answer_value", sa.JSON(), nullable=False),
        sa.Column("parse_confidence", sa.Float(), server_default="1.0", nullable=False),
        sa.Column("match_status", sa.String(32), server_default="unmatched", nullable=False),
        sa.Column("matched_question_id", sa.CHAR(36), sa.ForeignKey("questions.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_answer_key_doc_norm", "answer_key_entries", ["document_id", "number_norm"])
    op.create_index("ix_answer_key_doc_match", "answer_key_entries", ["document_id", "match_status"])

    # 9. warnings table
    op.create_table(
        "warnings",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("document_id", sa.CHAR(36), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", sa.CHAR(36), sa.ForeignKey("questions.id", ondelete="CASCADE"), nullable=True),
        sa.Column("page_no", sa.Integer(), nullable=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(32), server_default="warning", nullable=False),
        sa.Column("message", sa.String(512), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("resolved", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_warnings_doc_code", "warnings", ["document_id", "code"])
    op.create_index("ix_warnings_doc_sev", "warnings", ["document_id", "severity"])

    # 10. processing_events table
    op.create_table(
        "processing_events",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("document_id", sa.CHAR(36), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage", sa.String(64), nullable=False),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("attempt", sa.Integer(), server_default="1", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(1024), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=False),
    )
    op.create_index("ix_processing_events_doc_stage", "processing_events", ["document_id", "stage"])


def downgrade() -> None:
    op.drop_table("processing_events")
    op.drop_table("warnings")
    op.drop_table("answer_key_entries")
    op.drop_table("question_assets")
    op.drop_table("question_revisions")
    op.drop_table("questions")
    op.drop_table("pages")
    op.drop_table("document_links")
    op.drop_table("documents")
    op.drop_table("users")

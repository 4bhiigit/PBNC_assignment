import uuid
from pathlib import Path

import pytest

import app.db.session as session_module
from app.db.models.document import Document
from app.db.models.question import Question
from app.workers.tasks import finalize_document, process_document, process_page
from scripts.generate_samples import INPUT_DIR, generate_all_samples


@pytest.fixture(scope="module", autouse=True)
def setup_samples() -> None:
    generate_all_samples()


def _process_file(file_path: Path) -> uuid.UUID:
    session = session_module.get_sync_db()
    from app.core.storage import get_storage

    storage = get_storage()

    doc_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    file_bytes = file_path.read_bytes()

    storage_key = f"{owner_id}/{doc_id}"
    storage.save_sync(storage_key, file_bytes)

    doc = Document(
        id=doc_id,
        owner_id=owner_id,
        original_filename=file_path.name,
        storage_key=storage_key,
        mime_type="application/pdf",
        size_bytes=len(file_bytes),
        sha256="test_sha",
        page_count=1,
        status="queued",
        stage="ingest",
        progress_pct=0,
    )
    session.add(doc)
    session.commit()

    ingest_res = process_document(str(doc_id))
    p_count = ingest_res.get("page_count", 1)

    for p_no in range(1, p_count + 1):
        process_page(str(doc_id), p_no)

    finalize_document(str(doc_id))
    session.close()
    return doc_id


def test_digital_paper_mcq_pipeline() -> None:
    doc_id = _process_file(INPUT_DIR / "digital_paper_mcq.pdf")
    session = session_module.get_sync_db()
    from sqlalchemy import select

    questions = list(
        session.execute(
            select(Question).where(Question.document_id == doc_id).order_by(Question.sequence.asc())
        )
        .scalars()
        .all()
    )

    assert len(questions) == 20
    # Verify section headings
    sections = {q.section for q in questions if q.section}
    assert "Section A - Physics" in sections
    assert "Section B - Chemistry" in sections
    assert "Section C - Mathematics" in sections

    session.close()


def test_digital_paper_spanning_pipeline() -> None:
    doc_id = _process_file(INPUT_DIR / "digital_paper_spanning.pdf")
    session = session_module.get_sync_db()
    from sqlalchemy import select

    questions = list(
        session.execute(
            select(Question).where(Question.document_id == doc_id).order_by(Question.sequence.asc())
        )
        .scalars()
        .all()
    )

    assert len(questions) == 5

    # Question 2 should span page 1 and page 2
    q2 = next((q for q in questions if q.sequence == 2), None)
    assert q2 is not None
    assert 1 in q2.source_pages
    assert 2 in q2.source_pages

    # Question 4 should span 3 pages (2, 3, 4)
    q4 = next((q for q in questions if q.sequence == 4), None)
    assert q4 is not None
    assert 2 in q4.source_pages
    assert 3 in q4.source_pages
    assert 4 in q4.source_pages

    session.close()


def test_low_confidence_paper_pipeline() -> None:
    doc_id = _process_file(INPUT_DIR / "low_confidence.pdf")
    session = session_module.get_sync_db()
    from sqlalchemy import select

    questions = list(
        session.execute(
            select(Question).where(Question.document_id == doc_id).order_by(Question.sequence.asc())
        )
        .scalars()
        .all()
    )

    # Low confidence file must produce questions flagged for review
    assert any(q.status == "needs_review" for q in questions)
    flags = [f.get("code") for q in questions for f in (q.flags or []) if isinstance(f, dict)]
    assert any(f in ("MISSING_NUMBER", "DUPLICATE_NUMBER", "MCQ_OPTIONS_LT_2") for f in flags)

    session.close()

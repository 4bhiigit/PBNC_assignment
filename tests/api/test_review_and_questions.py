import uuid

import pytest
from httpx import AsyncClient

from app.core.security import create_access_token, hash_password
from app.db.models.document import Document
from app.db.models.question import Question
from app.db.models.question_revision import QuestionRevision
from app.db.models.user import User
from app.db.models.warning import Warning
from tests.conftest import AsyncTestingSessionLocal


@pytest.fixture
def auth_headers() -> tuple[dict[str, str], uuid.UUID]:
    user_id = uuid.uuid4()
    token = create_access_token(subject=str(user_id), role="user")
    return {"Authorization": f"Bearer {token}"}, user_id


@pytest.mark.asyncio
async def test_questions_document_not_ready_409(
    client: AsyncClient, auth_headers: tuple[dict[str, str], uuid.UUID]
) -> None:
    headers, user_id = auth_headers
    async with AsyncTestingSessionLocal() as session:
        user = User(
            id=user_id,
            email="test_user@example.com",
            password_hash=hash_password("password123"),
            role="user",
        )
        session.add(user)
        doc = Document(
            id=uuid.uuid4(),
            owner_id=user_id,
            original_filename="sample.pdf",
            storage_key="test/key",
            mime_type="application/pdf",
            size_bytes=1000,
            sha256="sha123",
            page_count=1,
            status="processing",
            stage="pages",
            progress_pct=50,
        )
        session.add(doc)
        await session.commit()
        doc_id = doc.id

    # Querying questions during processing should return 409 DOCUMENT_NOT_READY
    resp = await client.get(f"/api/v1/documents/{doc_id}/questions", headers=headers)
    assert resp.status_code == 409
    data = resp.json()
    assert data["error"]["code"] == "DOCUMENT_NOT_READY"

    # Querying review-queue during processing should return 409
    resp = await client.get(f"/api/v1/documents/{doc_id}/review-queue", headers=headers)
    assert resp.status_code == 409

    # Querying warnings during processing should return 409
    resp = await client.get(f"/api/v1/documents/{doc_id}/warnings", headers=headers)
    assert resp.status_code == 409

    # Querying export during processing should return 409
    resp = await client.get(f"/api/v1/documents/{doc_id}/export", headers=headers)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_questions_list_filter_and_sort(
    client: AsyncClient, auth_headers: tuple[dict[str, str], uuid.UUID]
) -> None:
    headers, user_id = auth_headers
    doc_id = uuid.uuid4()
    q1_id = uuid.uuid4()
    q2_id = uuid.uuid4()

    async with AsyncTestingSessionLocal() as session:
        user = User(
            id=user_id,
            email="test_filter@example.com",
            password_hash=hash_password("password123"),
            role="user",
        )
        session.add(user)
        doc = Document(
            id=doc_id,
            owner_id=user_id,
            original_filename="exam.pdf",
            storage_key="test/key2",
            mime_type="application/pdf",
            size_bytes=1000,
            sha256="sha456",
            page_count=2,
            status="completed",
            stage="finalize",
            progress_pct=100,
        )
        session.add(doc)

        q1 = Question(
            id=q1_id,
            document_id=doc_id,
            sequence=1,
            number_raw="Q.1",
            number_norm="1",
            section="Physics",
            type="mcq_single",
            text="What is the unit of force?",
            options=[
                {"label": "A", "raw_label": "(a)", "text": "Newton"},
                {"label": "B", "raw_label": "(b)", "text": "Joule"},
            ],
            source_pages=[1],
            confidence=0.95,
            status="extracted",
            answer_status="matched",
            answer_value=["A"],
            answer_raw="A",
            flags=[],
        )
        q2 = Question(
            id=q2_id,
            document_id=doc_id,
            sequence=2,
            number_raw="Q.2",
            number_norm="2",
            section="Chemistry",
            type="numerical",
            text="Calculate pH of water at 25C.",
            options=[],
            source_pages=[2],
            confidence=0.55,
            status="needs_review",
            answer_status="not_found",
            flags=[{"code": "LOW_CONFIDENCE", "severity": "warning"}],
        )
        session.add_all([q1, q2])
        await session.commit()

    # List all questions
    resp = await client.get(f"/api/v1/documents/{doc_id}/questions", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2

    # Check SPEC §14 fields format on q1
    item0 = next(item for item in data["items"] if item["id"] == str(q1_id))
    assert item0["number"]["raw"] == "Q.1"
    assert item0["number"]["normalized"] == "1"
    assert item0["section"] == "Physics"
    assert item0["type"] == "mcq_single"
    assert len(item0["options"]) == 2
    assert item0["answer"]["status"] == "matched"
    assert item0["answer"]["value"] == ["A"]
    assert item0["confidence"] == 0.95
    assert item0["status"] == "extracted"

    # Filter by needs_review=true
    resp = await client.get(
        f"/api/v1/documents/{doc_id}/questions?needs_review=true", headers=headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == str(q2_id)

    # Filter by section
    resp = await client.get(
        f"/api/v1/documents/{doc_id}/questions?section=Physics", headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 1

    # Filter by page
    resp = await client.get(
        f"/api/v1/documents/{doc_id}/questions?page=2", headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["id"] == str(q2_id)


@pytest.mark.asyncio
async def test_review_queue_endpoint(
    client: AsyncClient, auth_headers: tuple[dict[str, str], uuid.UUID]
) -> None:
    headers, user_id = auth_headers
    doc_id = uuid.uuid4()
    q_id = uuid.uuid4()

    async with AsyncTestingSessionLocal() as session:
        user = User(
            id=user_id,
            email="test_rq@example.com",
            password_hash=hash_password("password123"),
            role="user",
        )
        session.add(user)
        doc = Document(
            id=doc_id,
            owner_id=user_id,
            original_filename="exam.pdf",
            storage_key="test/key3",
            mime_type="application/pdf",
            size_bytes=1000,
            sha256="sha789",
            page_count=1,
            status="completed_with_warnings",
            stage="finalize",
            progress_pct=100,
        )
        session.add(doc)

        q = Question(
            id=q_id,
            document_id=doc_id,
            sequence=1,
            number_raw="Q.1",
            number_norm="1",
            section="Physics",
            type="mcq_single",
            text="Incomplete question text",
            options=[{"label": "A", "raw_label": "(a)", "text": "Opt 1"}],
            source_pages=[1],
            confidence=0.45,
            status="needs_review",
            flags=[
                {"code": "MCQ_OPTIONS_LT_2", "severity": "critical"},
                {"code": "LOW_CONFIDENCE", "severity": "warning"},
            ],
        )
        session.add(q)
        await session.commit()

    resp = await client.get(f"/api/v1/documents/{doc_id}/review-queue", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    item = data["items"][0]
    assert item["question"]["id"] == str(q_id)
    assert "MCQ_OPTIONS_LT_2" in item["reasons"]
    assert item["page_refs"] == [1]


@pytest.mark.asyncio
async def test_patch_question_human_correction_and_revision_audit(
    client: AsyncClient, auth_headers: tuple[dict[str, str], uuid.UUID]
) -> None:
    headers, user_id = auth_headers
    doc_id = uuid.uuid4()
    q_id = uuid.uuid4()

    async with AsyncTestingSessionLocal() as session:
        user = User(
            id=user_id,
            email="test_patch@example.com",
            password_hash=hash_password("password123"),
            role="user",
        )
        session.add(user)
        doc = Document(
            id=doc_id,
            owner_id=user_id,
            original_filename="exam.pdf",
            storage_key="test/key4",
            mime_type="application/pdf",
            size_bytes=1000,
            sha256="sha101112",
            page_count=1,
            status="completed_with_warnings",
            stage="finalize",
            progress_pct=100,
        )
        session.add(doc)

        q = Question(
            id=q_id,
            document_id=doc_id,
            sequence=1,
            number_raw="Q.1",
            number_norm="1",
            type="mcq_single",
            text="Original OCR text with typos",
            options=[{"label": "A", "raw_label": "(a)", "text": "Opt A"}],
            source_pages=[1],
            confidence=0.50,
            status="needs_review",
            flags=[{"code": "MCQ_OPTIONS_LT_2", "severity": "critical"}],
        )
        session.add(q)
        await session.commit()

    # Perform PATCH to correct text and add second option
    patch_payload = {
        "text": "Corrected question text by human reviewer.",
        "options": [
            {"label": "A", "raw_label": "(a)", "text": "Correct Option A"},
            {"label": "B", "raw_label": "(b)", "text": "Correct Option B"},
        ],
        "answer_raw": "B",
        "answer_value": ["B"],
        "answer_status": "matched",
    }
    patch_resp = await client.patch(
        f"/api/v1/questions/{q_id}", json=patch_payload, headers=headers
    )
    assert patch_resp.status_code == 200
    q_data = patch_resp.json()
    assert q_data["text"] == "Corrected question text by human reviewer."
    assert len(q_data["options"]) == 2
    assert q_data["review"]["edited"] is True
    assert q_data["review"]["state"] == "corrected"
    assert q_data["status"] == "extracted"

    # Verify that a revision was created in question_revisions table
    async with AsyncTestingSessionLocal() as session:
        from sqlalchemy import select

        revs = (
            (
                await session.execute(
                    select(QuestionRevision).where(QuestionRevision.question_id == q_id)
                )
            )
            .scalars()
            .all()
        )
        assert len(revs) == 1
        assert revs[0].editor_id == user_id
        assert revs[0].before["text"] == "Original OCR text with typos"
        assert revs[0].after["text"] == "Corrected question text by human reviewer."


@pytest.mark.asyncio
async def test_post_question_review_action(
    client: AsyncClient, auth_headers: tuple[dict[str, str], uuid.UUID]
) -> None:
    headers, user_id = auth_headers
    doc_id = uuid.uuid4()
    q_id = uuid.uuid4()

    async with AsyncTestingSessionLocal() as session:
        user = User(
            id=user_id,
            email="test_rev_action@example.com",
            password_hash=hash_password("password123"),
            role="user",
        )
        session.add(user)
        doc = Document(
            id=doc_id,
            owner_id=user_id,
            original_filename="exam.pdf",
            storage_key="test/key5",
            mime_type="application/pdf",
            size_bytes=1000,
            sha256="sha131415",
            page_count=1,
            status="completed_with_warnings",
            stage="finalize",
            progress_pct=100,
        )
        session.add(doc)

        q = Question(
            id=q_id,
            document_id=doc_id,
            sequence=1,
            number_raw="Q.1",
            number_norm="1",
            type="mcq_single",
            text="Valid question text.",
            options=[
                {"label": "A", "raw_label": "(a)", "text": "Opt A"},
                {"label": "B", "raw_label": "(b)", "text": "Opt B"},
            ],
            source_pages=[1],
            confidence=0.75,
            status="partial",
        )
        session.add(q)
        await session.commit()

    # Submit approve review action
    review_resp = await client.post(
        f"/api/v1/questions/{q_id}/review",
        json={"action": "approve", "notes": "Looks good"},
        headers=headers,
    )
    assert review_resp.status_code == 200
    q_data = review_resp.json()
    assert q_data["review"]["state"] == "approved"
    assert q_data["status"] == "extracted"


@pytest.mark.asyncio
async def test_export_document_json(
    client: AsyncClient, auth_headers: tuple[dict[str, str], uuid.UUID]
) -> None:
    headers, user_id = auth_headers
    doc_id = uuid.uuid4()
    q_id = uuid.uuid4()

    async with AsyncTestingSessionLocal() as session:
        user = User(
            id=user_id,
            email="test_export@example.com",
            password_hash=hash_password("password123"),
            role="user",
        )
        session.add(user)
        doc = Document(
            id=doc_id,
            owner_id=user_id,
            original_filename="full_paper.pdf",
            storage_key="test/key6",
            mime_type="application/pdf",
            size_bytes=5000,
            sha256="shaexport123",
            page_count=1,
            status="completed",
            stage="finalize",
            progress_pct=100,
        )
        session.add(doc)

        q = Question(
            id=q_id,
            document_id=doc_id,
            sequence=1,
            number_raw="Q.1",
            number_norm="1",
            section="Physics",
            type="mcq_single",
            text="Sample export question text.",
            options=[
                {"label": "A", "raw_label": "(a)", "text": "Choice 1"},
                {"label": "B", "raw_label": "(b)", "text": "Choice 2"},
            ],
            source_pages=[1],
            confidence=0.92,
            status="extracted",
            answer_status="matched",
            answer_value=["A"],
            answer_raw="A",
        )
        session.add(q)

        w = Warning(
            id=uuid.uuid4(),
            document_id=doc_id,
            question_id=q_id,
            page_no=1,
            code="ROTATED_CORRECTED",
            severity="info",
            message="Page rotated 90 degrees",
        )
        session.add(w)
        await session.commit()

    resp = await client.get(f"/api/v1/documents/{doc_id}/export", headers=headers)
    assert resp.status_code == 200
    export_data = resp.json()

    assert export_data["document"]["id"] == str(doc_id)
    assert len(export_data["questions"]) == 1
    assert export_data["questions"][0]["id"] == str(q_id)
    assert export_data["questions"][0]["number"]["raw"] == "Q.1"
    assert len(export_data["warnings"]) == 1
    assert export_data["warnings"][0]["code"] == "ROTATED_CORRECTED"


@pytest.mark.asyncio
async def test_reprocess_document_endpoint(
    client: AsyncClient, auth_headers: tuple[dict[str, str], uuid.UUID]
) -> None:
    headers, user_id = auth_headers
    doc_id = uuid.uuid4()

    async with AsyncTestingSessionLocal() as session:
        user = User(
            id=user_id,
            email="test_reprocess@example.com",
            password_hash=hash_password("password123"),
            role="user",
        )
        session.add(user)
        doc = Document(
            id=doc_id,
            owner_id=user_id,
            original_filename="reprocess.pdf",
            storage_key="test/key7",
            mime_type="application/pdf",
            size_bytes=1000,
            sha256="shareprocess",
            page_count=1,
            status="completed",
            stage="finalize",
            progress_pct=100,
        )
        session.add(doc)
        await session.commit()

    resp = await client.post(
        f"/api/v1/documents/{doc_id}/reprocess?overwrite_reviewed=false",
        headers=headers,
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "queued"
    assert data["stage"] == "ingest"

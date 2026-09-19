import io

import fitz
import pytest
from httpx import AsyncClient

from app.workers.tasks import finalize_document, process_document, process_page


def create_sample_pdf_bytes() -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    sample_text = """
    Section A - Science

    1. What is the SI unit of force?
    (A) Joule
    (B) Newton
    (C) Pascal
    (D) Watt

    2. Which gas is most abundant in Earth's atmosphere?
    (a) Oxygen
    (b) Nitrogen
    (c) Carbon dioxide
    (d) Argon
    Ans: (b)
    """
    page.insert_text((50, 50), sample_text)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


@pytest.mark.asyncio
async def test_end_to_end_rules_pipeline_and_api(client: AsyncClient) -> None:
    # 1. Register and login User A
    user_a_res = await client.post(
        "/api/v1/auth/register",
        json={"email": "alice@example.com", "password": "SecurePassword123!"},
    )
    assert user_a_res.status_code == 201
    login_a_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "SecurePassword123!"},
    )
    assert login_a_res.status_code == 200
    token_a = login_a_res.json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Register User B
    user_b_res = await client.post(
        "/api/v1/auth/register",
        json={"email": "bob@example.com", "password": "SecurePassword123!"},
    )
    assert user_b_res.status_code == 201
    login_b_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "bob@example.com", "password": "SecurePassword123!"},
    )
    assert login_b_res.status_code == 200
    token_b = login_b_res.json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # 2. Upload document via API
    pdf_bytes = create_sample_pdf_bytes()
    upload_res = await client.post(
        "/api/v1/documents",
        files={"file": ("physics_test.pdf", pdf_bytes, "application/pdf")},
        headers=headers_a,
    )
    assert upload_res.status_code == 202
    doc_id = upload_res.json()["id"]

    # 3. Test 409 DOCUMENT_NOT_READY before pipeline finishes
    not_ready_res = await client.get(
        f"/api/v1/documents/{doc_id}/questions",
        headers=headers_a,
    )
    assert not_ready_res.status_code == 409
    assert not_ready_res.json()["error"]["code"] == "DOCUMENT_NOT_READY"

    # 4. Execute pipeline worker tasks
    ingest_res = process_document(doc_id)
    assert ingest_res["status"] == "pages_enqueued"

    page_res = process_page(doc_id, 1)
    assert page_res["status"] == "completed"

    fin_res = finalize_document(doc_id)
    assert fin_res["status"] == "completed"
    assert fin_res["questions_count"] == 2

    # 5. Fetch questions via API
    questions_res = await client.get(
        f"/api/v1/documents/{doc_id}/questions",
        headers=headers_a,
    )
    assert questions_res.status_code == 200
    q_data = questions_res.json()
    assert q_data["total"] == 2
    assert len(q_data["items"]) == 2

    q1 = q_data["items"][0]
    assert q1["sequence"] == 1
    assert q1["number_norm"] == "1"
    assert "SI unit of force" in q1["text"]
    assert len(q1["options"]) == 4
    assert [opt["label"] for opt in q1["options"]] == ["A", "B", "C", "D"]

    q2 = q_data["items"][1]
    assert q2["sequence"] == 2
    assert q2["number_norm"] == "2"
    assert "abundant in Earth's atmosphere" in q2["text"]
    assert q2["answer"]["status"] == "matched"
    assert q2["answer"]["value"] == ["B"]

    # 6. Fetch single question
    q1_detail_res = await client.get(
        f"/api/v1/questions/{q1['id']}",
        headers=headers_a,
    )
    assert q1_detail_res.status_code == 200
    assert q1_detail_res.json()["id"] == q1["id"]

    # 7. Verify cross-tenant isolation (User B must get 404, not 403)
    user_b_list_res = await client.get(
        f"/api/v1/documents/{doc_id}/questions",
        headers=headers_b,
    )
    assert user_b_list_res.status_code == 404
    assert user_b_list_res.json()["error"]["code"] == "NOT_FOUND"

    user_b_single_res = await client.get(
        f"/api/v1/questions/{q1['id']}",
        headers=headers_b,
    )
    assert user_b_single_res.status_code == 404
    assert user_b_single_res.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_end_to_end_scanned_image_pipeline(client: AsyncClient) -> None:
    from PIL import Image

    email = "charlie@example.com"
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!"},
    )
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    img = Image.new("RGB", (800, 600), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    upload_res = await client.post(
        "/api/v1/documents",
        files={"file": ("scan_question.png", png_bytes, "image/png")},
        headers=headers,
    )
    assert upload_res.status_code == 202
    doc_id = upload_res.json()["id"]

    ingest_res = process_document(doc_id)
    assert ingest_res["status"] == "pages_enqueued"
    assert ingest_res["page_count"] == 1

    page_res = process_page(doc_id, 1)
    assert page_res["status"] == "completed"

    fin_res = finalize_document(doc_id)
    assert fin_res["status"] == "completed"

    status_res = await client.get(f"/api/v1/documents/{doc_id}/status", headers=headers)
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "completed"

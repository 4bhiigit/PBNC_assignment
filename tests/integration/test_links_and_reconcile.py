import io

import fitz
import pytest
from httpx import AsyncClient

from app.workers.tasks import finalize_document, process_document, process_page


def create_question_paper_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    text = """
    Section A - Physics

    1. What is the acceleration due to gravity on Earth?
    (A) 9.8 m/s^2
    (B) 8.9 m/s^2
    (C) 10.5 m/s^2
    (D) 12.0 m/s^2

    2. Which electromagnetic wave has the shortest wavelength?
    (A) Radio waves
    (B) Microwaves
    (C) Gamma rays
    (D) Infrared rays
    """
    page.insert_text((50, 50), text)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def create_answer_key_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    text = """
    Official Answer Key - Physics Examination
    Subject: Physics
    Standard Examination Paper Code: PHY-01

    1. A
    2. C
    """
    page.insert_text((50, 50), text)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


@pytest.mark.asyncio
async def test_links_and_reconciliation_flow(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "extractor", "rules")

    # 1. Register and login User A
    user_a = await client.post(
        "/api/v1/auth/register",
        json={"email": "alice_links@example.com", "password": "Password123!"},
    )
    assert user_a.status_code == 201
    login_a = await client.post(
        "/api/v1/auth/login",
        json={"email": "alice_links@example.com", "password": "Password123!"},
    )
    token_a = login_a.json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # 2. Register and login User B (for tenant isolation check)
    user_b = await client.post(
        "/api/v1/auth/register",
        json={"email": "bob_links@example.com", "password": "Password123!"},
    )
    assert user_b.status_code == 201
    login_b = await client.post(
        "/api/v1/auth/login",
        json={"email": "bob_links@example.com", "password": "Password123!"},
    )
    token_b = login_b.json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # 3. User A uploads Question Paper
    q_pdf = create_question_paper_pdf()
    res_q = await client.post(
        "/api/v1/documents",
        files={"file": ("physics_paper.pdf", q_pdf, "application/pdf")},
        headers=headers_a,
    )
    assert res_q.status_code == 202
    q_doc_id = res_q.json()["id"]

    # Process Question Paper
    process_document(q_doc_id)
    process_page(q_doc_id, 1)
    finalize_document(q_doc_id)

    # Verify questions extracted but answers not_found
    q_res = await client.get(f"/api/v1/documents/{q_doc_id}", headers=headers_a)
    assert q_res.status_code == 200
    assert q_res.json()["detected_role"] == "question_paper"

    # 4. User A uploads Answer Key document
    k_pdf = create_answer_key_pdf()
    res_k = await client.post(
        "/api/v1/documents",
        files={"file": ("physics_key.pdf", k_pdf, "application/pdf")},
        data={"role_hint": "answer_key"},
        headers=headers_a,
    )
    assert res_k.status_code == 202
    k_doc_id = res_k.json()["id"]

    # Process Answer Key
    process_document(k_doc_id)
    process_page(k_doc_id, 1)
    finalize_document(k_doc_id)

    # 5. Check Answer Key endpoint on the key doc
    ak_res = await client.get(f"/api/v1/documents/{k_doc_id}/answer-key", headers=headers_a)
    assert ak_res.status_code == 200
    ak_data = ak_res.json()
    assert ak_data["summary"]["total"] == 2
    assert ak_data["detected_role"] == "answer_key"

    # 6. Tenant isolation check: User B tries to link User A's documents -> 404
    foreign_link_res = await client.post(
        f"/api/v1/documents/{q_doc_id}/links",
        json={"to_document_id": k_doc_id, "relation": "answer_key_for"},
        headers=headers_b,
    )
    assert foreign_link_res.status_code == 404

    # 7. Self-link check -> 422
    self_link_res = await client.post(
        f"/api/v1/documents/{q_doc_id}/links",
        json={"to_document_id": q_doc_id, "relation": "related"},
        headers=headers_a,
    )
    assert self_link_res.status_code == 422

    # 8. User A creates link: key_doc is answer_key_for q_doc
    link_res = await client.post(
        f"/api/v1/documents/{k_doc_id}/links",
        json={"to_document_id": q_doc_id, "relation": "answer_key_for"},
        headers=headers_a,
    )
    assert link_res.status_code == 201
    link_id = link_res.json()["id"]

    # 9. Verify link appears in list
    list_res = await client.get(f"/api/v1/documents/{q_doc_id}/links", headers=headers_a)
    assert list_res.status_code == 200
    links = list_res.json()
    assert len(links) == 1
    assert links[0]["id"] == link_id

    # 10. Reconcile question paper answers
    rec_res = await client.post(f"/api/v1/documents/{q_doc_id}/reconcile", headers=headers_a)
    assert rec_res.status_code == 200
    rec_data = rec_res.json()
    assert rec_data["status"] == "completed"
    assert rec_data["questions_matched"] == 2

    # 11. Verify questions on Question Paper now have matched answers from linked doc
    paper_ak_res = await client.get(f"/api/v1/documents/{q_doc_id}/answer-key", headers=headers_a)
    assert paper_ak_res.status_code == 200

    # 12. Delete link
    del_res = await client.delete(
        f"/api/v1/documents/{q_doc_id}/links/{link_id}", headers=headers_a
    )
    assert del_res.status_code == 204

    # Verify link list is now empty
    list_after_del = await client.get(f"/api/v1/documents/{q_doc_id}/links", headers=headers_a)
    assert list_after_del.status_code == 200
    assert len(list_after_del.json()) == 0

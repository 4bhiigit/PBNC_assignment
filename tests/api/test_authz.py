import fitz
import pytest
from httpx import AsyncClient


def make_pdf_bytes(text: str = "Confidential User A Document") -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), text)
    return doc.write()


async def register_and_login(
    client: AsyncClient, email: str, role: str = "user"
) -> tuple[str, str]:
    res = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!"},
    )
    user_id = res.json()["id"]

    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    token = login_res.json()["access_token"]
    return user_id, token


@pytest.mark.asyncio
async def test_cross_tenant_isolation_returns_404_not_403(client: AsyncClient) -> None:
    # 1. User A registers and uploads a document
    _, token_a = await register_and_login(client, "user_a@tenant.com")
    upload_res = await client.post(
        "/api/v1/documents",
        files={"file": ("doc_a.pdf", make_pdf_bytes("Doc A"), "application/pdf")},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert upload_res.status_code == 202
    doc_a_id = upload_res.json()["id"]

    # 2. User B registers and attempts to access User A's document
    _, token_b = await register_and_login(client, "user_b@tenant.com")
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # GET /documents/{id} -> must be 404
    res_get = await client.get(f"/api/v1/documents/{doc_a_id}", headers=headers_b)
    assert res_get.status_code == 404
    assert res_get.json()["error"]["code"] == "NOT_FOUND"

    # GET /documents/{id}/status -> must be 404
    res_status = await client.get(f"/api/v1/documents/{doc_a_id}/status", headers=headers_b)
    assert res_status.status_code == 404
    assert res_status.json()["error"]["code"] == "NOT_FOUND"

    # DELETE /documents/{id} -> must be 404
    res_del = await client.delete(f"/api/v1/documents/{doc_a_id}", headers=headers_b)
    assert res_del.status_code == 404
    assert res_del.json()["error"]["code"] == "NOT_FOUND"

    # GET /documents/{id}/pages/1/image -> must be 404
    res_img = await client.get(f"/api/v1/documents/{doc_a_id}/pages/1/image", headers=headers_b)
    assert res_img.status_code == 404
    assert res_img.json()["error"]["code"] == "NOT_FOUND"

    # GET /documents -> User B's list must not contain User A's document
    res_list = await client.get("/api/v1/documents", headers=headers_b)
    assert res_list.status_code == 200
    b_doc_ids = [item["id"] for item in res_list.json()["items"]]
    assert doc_a_id not in b_doc_ids

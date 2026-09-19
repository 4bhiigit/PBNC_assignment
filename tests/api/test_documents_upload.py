import io

import fitz
import pytest
from httpx import AsyncClient
from PIL import Image


async def get_auth_token(client: AsyncClient, email: str = "doc_uploader@example.com") -> str:
    res = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!"},
    )
    if res.status_code == 409:
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "Password123!"},
        )
        return login_res.json()["access_token"]
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    return login_res.json()["access_token"]


def make_pdf_bytes(text: str = "Test Question Paper") -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), text)
    return doc.write()


def make_png_bytes() -> bytes:
    img = Image.new("RGB", (100, 100), color="red")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_upload_pdf_success_returns_202(client: AsyncClient) -> None:
    token = await get_auth_token(client, "user_pdf@example.com")
    pdf_bytes = make_pdf_bytes("Question 1. What is physics?")

    files = {"file": ("paper.pdf", pdf_bytes, "application/pdf")}
    res = await client.post(
        "/api/v1/documents",
        files=files,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 202
    data = res.json()
    assert "id" in data
    assert data["status"] == "queued"
    assert "status" in data["links"]
    assert "self" in data["links"]


@pytest.mark.asyncio
async def test_upload_image_success_returns_202(client: AsyncClient) -> None:
    token = await get_auth_token(client, "user_png@example.com")
    png_bytes = make_png_bytes()

    files = {"file": ("scan.png", png_bytes, "image/png")}
    res = await client.post(
        "/api/v1/documents",
        files=files,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 202
    data = res.json()
    assert "id" in data
    assert data["status"] == "queued"


@pytest.mark.asyncio
async def test_upload_rejected_wrong_magic_bytes(client: AsyncClient) -> None:
    token = await get_auth_token(client, "user_fake@example.com")
    fake_content = b"This is not a real PDF"

    files = {"file": ("fake.pdf", fake_content, "application/pdf")}
    res = await client.post(
        "/api/v1/documents",
        files=files,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 415
    data = res.json()
    assert data["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"


@pytest.mark.asyncio
async def test_upload_rejected_txt_file(client: AsyncClient) -> None:
    token = await get_auth_token(client, "user_txt@example.com")
    files = {"file": ("notes.txt", b"simple notes", "text/plain")}
    res = await client.post(
        "/api/v1/documents",
        files=files,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 415
    assert res.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"


@pytest.mark.asyncio
async def test_upload_unauthenticated_rejected(client: AsyncClient) -> None:
    files = {"file": ("paper.pdf", make_pdf_bytes(), "application/pdf")}
    res = await client.post("/api/v1/documents", files=files)
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "UNAUTHENTICATED"


@pytest.mark.asyncio
async def test_document_lifecycle_and_deduplication(client: AsyncClient) -> None:
    token = await get_auth_token(client, "user_lifecycle@example.com")
    pdf_bytes = make_pdf_bytes("Deduplication Unique Content 12345")

    # 1. First upload
    res1 = await client.post(
        "/api/v1/documents",
        files={"file": ("doc.pdf", pdf_bytes, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res1.status_code == 202
    doc_id = res1.json()["id"]

    # 2. Duplicate upload without force -> returns same id
    res2 = await client.post(
        "/api/v1/documents",
        files={"file": ("doc_dup.pdf", pdf_bytes, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res2.status_code == 202
    assert res2.json()["id"] == doc_id

    # 3. GET /documents list
    list_res = await client.get(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["total"] >= 1
    assert any(item["id"] == doc_id for item in list_data["items"])

    # 4. GET /documents/{id} detail
    detail_res = await client.get(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert detail_res.status_code == 200
    assert detail_res.json()["id"] == doc_id
    assert "summary" in detail_res.json()

    # 5. GET /documents/{id}/status
    status_res = await client.get(
        f"/api/v1/documents/{doc_id}/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert status_res.status_code == 200
    assert status_res.json()["id"] == doc_id
    assert "progress_pct" in status_res.json()

    # 6. DELETE /documents/{id}
    del_res = await client.delete(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_res.status_code == 204

    # 7. Subsequent GET returns 404
    after_del_res = await client.get(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert after_del_res.status_code == 404
    assert after_del_res.json()["error"]["code"] == "NOT_FOUND"

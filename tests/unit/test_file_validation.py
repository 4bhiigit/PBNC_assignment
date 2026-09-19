import io

import fitz
import pytest
from fastapi import UploadFile
from PIL import Image

from app.errors import (
    MalformedFileException,
    PdfEncryptedException,
    UnsupportedMediaTypeException,
)
from app.services.upload_service import (
    MAGIC_JPEG,
    MAGIC_PDF,
    MAGIC_PNG,
    detect_magic_mime,
    stream_and_validate_upload,
)


def create_sample_pdf_bytes(pages: int = 1, encrypt_password: str | None = None) -> bytes:
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((50, 50), f"Sample page {i + 1}")

    if encrypt_password:
        return doc.write(
            encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw=encrypt_password, user_pw=encrypt_password
        )
    return doc.write()


def create_sample_image_bytes(format: str = "PNG", size: tuple[int, int] = (100, 100)) -> bytes:
    img = Image.new("RGB", size, color="blue")
    buf = io.BytesIO()
    img.save(buf, format=format)
    return buf.getvalue()


def test_detect_magic_mime() -> None:
    assert detect_magic_mime(MAGIC_PDF) == "application/pdf"
    assert detect_magic_mime(MAGIC_PNG) == "image/png"
    assert detect_magic_mime(MAGIC_JPEG) == "image/jpeg"
    assert detect_magic_mime(b"random garbage text") is None


@pytest.mark.asyncio
async def test_valid_pdf_validation() -> None:
    pdf_bytes = create_sample_pdf_bytes(pages=2)
    upload = UploadFile(filename="exam.pdf", file=io.BytesIO(pdf_bytes))
    result = await stream_and_validate_upload(upload)

    assert result.mime_type == "application/pdf"
    assert result.page_count == 2
    assert result.size_bytes == len(pdf_bytes)
    assert len(result.sha256) == 64


@pytest.mark.asyncio
async def test_valid_image_validation() -> None:
    png_bytes = create_sample_image_bytes(format="PNG", size=(200, 150))
    upload = UploadFile(filename="scan.png", file=io.BytesIO(png_bytes))
    result = await stream_and_validate_upload(upload)

    assert result.mime_type == "image/png"
    assert result.page_count == 1
    assert result.size_bytes == len(png_bytes)


@pytest.mark.asyncio
async def test_rejected_fake_pdf_with_wrong_magic() -> None:
    fake_bytes = b"Hello this is just a plain text file renamed to fake.pdf"
    upload = UploadFile(filename="fake.pdf", file=io.BytesIO(fake_bytes))

    with pytest.raises(UnsupportedMediaTypeException):
        await stream_and_validate_upload(upload)


@pytest.mark.asyncio
async def test_rejected_empty_file() -> None:
    upload = UploadFile(filename="empty.pdf", file=io.BytesIO(b""))

    with pytest.raises(MalformedFileException) as exc_info:
        await stream_and_validate_upload(upload)
    assert "empty" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_rejected_encrypted_pdf() -> None:
    enc_pdf = create_sample_pdf_bytes(pages=1, encrypt_password="secretpassword")
    upload = UploadFile(filename="locked.pdf", file=io.BytesIO(enc_pdf))

    with pytest.raises(PdfEncryptedException):
        await stream_and_validate_upload(upload)

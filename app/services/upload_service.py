import hashlib
import logging
import os
import tempfile
import uuid

import fitz  # PyMuPDF
from fastapi import UploadFile
from PIL import Image

from app.config import get_settings
from app.core.storage import get_storage
from app.errors import (
    FileTooLargeException,
    MalformedFileException,
    PdfEncryptedException,
    QueueUnavailableException,
    TooManyPagesException,
    UnsupportedMediaTypeException,
)
from app.workers.tasks import process_document

logger = logging.getLogger(__name__)

# Magic byte signatures
MAGIC_PDF = b"%PDF-"
MAGIC_PNG = b"\x89PNG\r\n\x1a\n"
MAGIC_JPEG = b"\xff\xd8\xff"


def detect_magic_mime(header: bytes) -> str | None:
    if header.startswith(MAGIC_PDF):
        return "application/pdf"
    if header.startswith(MAGIC_PNG):
        return "image/png"
    if header.startswith(MAGIC_JPEG):
        return "image/jpeg"
    return None


class UploadValidationResult:
    def __init__(
        self,
        temp_file_path: str,
        filename: str,
        mime_type: str,
        size_bytes: int,
        sha256: str,
        page_count: int,
    ) -> None:
        self.temp_file_path = temp_file_path
        self.filename = filename
        self.mime_type = mime_type
        self.size_bytes = size_bytes
        self.sha256 = sha256
        self.page_count = page_count


async def stream_and_validate_upload(file: UploadFile) -> UploadValidationResult:
    settings = get_settings()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    Image.MAX_IMAGE_PIXELS = settings.max_image_pixels

    # 1. Stream to a temporary file while counting bytes (do not trust Content-Length)
    hasher = hashlib.sha256()
    total_bytes = 0
    header_bytes = b""

    with tempfile.NamedTemporaryFile(delete=False, prefix="upload_", suffix=".tmp") as tmp:
        temp_file_path = tmp.name
        try:
            while chunk := await file.read(65536):
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise FileTooLargeException(
                        f"File size exceeds the {settings.max_upload_mb} MB limit",
                        details={"max_mb": settings.max_upload_mb, "bytes_received": total_bytes},
                    )

                if len(header_bytes) < 16:
                    header_bytes += chunk[: 16 - len(header_bytes)]

                hasher.update(chunk)
                tmp.write(chunk)
        except Exception:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
            raise

    if total_bytes == 0:
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)
        raise MalformedFileException("Uploaded file is empty (0 bytes)")

    # 2. Magic bytes validation
    detected_mime = detect_magic_mime(header_bytes)
    if not detected_mime or detected_mime not in settings.allowed_mime:
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)
        raise UnsupportedMediaTypeException(
            "Unsupported file type. Only PDF, PNG, and JPEG files are permitted.",
            details={"allowed": settings.allowed_mime},
        )

    sha256_hash = hasher.hexdigest()
    page_count = 1

    # 3. Deep validation
    if detected_mime == "application/pdf":
        try:
            doc = fitz.open(temp_file_path)
        except Exception as exc:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
            raise MalformedFileException(f"Failed to parse PDF document: {exc}") from exc

        try:
            if doc.is_encrypted:
                raise PdfEncryptedException()

            page_count = doc.page_count
            if page_count == 0:
                raise MalformedFileException("PDF contains 0 pages")

            if page_count > settings.max_pages:
                raise TooManyPagesException(
                    f"PDF has {page_count} pages, exceeding the limit of "
                    f"{settings.max_pages} pages",
                    details={"page_count": page_count, "max_pages": settings.max_pages},
                )

            # Test reading the first page to confirm file is not truncated
            _ = doc.load_page(0).get_text()
        except (PdfEncryptedException, TooManyPagesException, MalformedFileException):
            if not getattr(doc, "is_closed", False):
                doc.close()
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
            raise
        except Exception as exc:
            if not getattr(doc, "is_closed", False):
                doc.close()
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
            raise MalformedFileException(f"Corrupted or truncated PDF file: {exc}") from exc
        finally:
            if not getattr(doc, "is_closed", False):
                doc.close()

    else:
        # Image deep validation (PNG / JPEG)
        try:
            with open(temp_file_path, "rb") as img_file:
                with Image.open(img_file) as img:
                    img.verify()

            # Reopen to check dimensions and decompression bomb limit
            with Image.open(temp_file_path) as img:
                width, height = img.size
                if width * height > settings.max_image_pixels:
                    raise MalformedFileException(
                        "Image dimensions exceed decompression bomb threshold",
                        details={"pixels": width * height, "max_pixels": settings.max_image_pixels},
                    )
            page_count = 1
        except Image.DecompressionBombError as exc:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
            raise MalformedFileException(
                "Decompression bomb detected: image exceeds pixel limit"
            ) from exc
        except MalformedFileException:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
            raise
        except Exception as exc:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
            raise MalformedFileException(f"Invalid or corrupted image: {exc}") from exc

    return UploadValidationResult(
        temp_file_path=temp_file_path,
        filename=os.path.basename(file.filename or "upload"),
        mime_type=detected_mime,
        size_bytes=total_bytes,
        sha256=sha256_hash,
        page_count=page_count,
    )


async def store_and_enqueue_document(
    owner_id: uuid.UUID,
    validation: UploadValidationResult,
    doc_id: uuid.UUID,
) -> str:
    """Stores the temporary file to permanent storage under {owner_id}/{doc_id}.{ext}
    and enqueues the Celery processing task.
    """
    storage = get_storage()
    ext = (
        "pdf"
        if validation.mime_type == "application/pdf"
        else ("png" if validation.mime_type == "image/png" else "jpg")
    )
    storage_key = f"{owner_id}/{doc_id}.{ext}"

    try:
        with open(validation.temp_file_path, "rb") as f:
            await storage.save(storage_key, f)
    finally:
        if os.path.exists(validation.temp_file_path):
            os.unlink(validation.temp_file_path)

    # Enqueue Celery task with error handling
    try:
        process_document.delay(str(doc_id))
    except Exception as exc:
        logger.error("Failed to enqueue document %s to Celery: %s", doc_id, exc)
        raise QueueUnavailableException("Failed to enqueue processing job") from exc

    return storage_key

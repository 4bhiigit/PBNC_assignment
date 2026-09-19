import io
from dataclasses import dataclass, field
from uuid import UUID

import fitz  # PyMuPDF
from PIL import Image

from app.core.storage.base import StorageBackend
from app.pipeline.page_analysis import analyze_pdf_page


@dataclass
class PageIngestInfo:
    page_no: int
    width: int
    height: int
    image_key: str
    char_count: int
    decision: str  # "text_layer", "ocr", "mixed"
    text: str
    image_bytes: bytes


@dataclass
class IngestResult:
    page_count: int
    pages: list[PageIngestInfo] = field(default_factory=list)


def ingest_document(
    file_bytes: bytes,
    mime_type: str,
    owner_id: UUID,
    doc_id: UUID,
    storage: StorageBackend,
    render_dpi: int = 200,
    min_chars: int = 50,
) -> IngestResult:
    """
    Renders pages to PNG, persists page renders via storage,
    and analyzes whether each page contains digital text or requires OCR.
    """
    if mime_type == "application/pdf":
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        page_count = len(doc)
        pages: list[PageIngestInfo] = []

        try:
            for page_idx in range(page_count):
                page_no = page_idx + 1
                page = doc[page_idx]

                # Render page at specified DPI
                pix = page.get_pixmap(dpi=render_dpi)
                png_bytes = pix.tobytes("png")

                # Store rendered image
                image_key = f"{owner_id}/pages/{doc_id}_{page_no}.png"
                storage.save_sync(image_key, png_bytes)

                # Analyze digital text vs scan
                analysis = analyze_pdf_page(page, min_chars=min_chars)
                text = page.get_text("text")

                pages.append(
                    PageIngestInfo(
                        page_no=page_no,
                        width=int(page.rect.width),
                        height=int(page.rect.height),
                        image_key=image_key,
                        char_count=analysis.text_chars,
                        decision=analysis.decision,
                        text=text,
                        image_bytes=png_bytes,
                    )
                )
        finally:
            if not getattr(doc, "is_closed", False):
                doc.close()

        return IngestResult(page_count=page_count, pages=pages)

    # Single-page Image handling
    pil_img = Image.open(io.BytesIO(file_bytes))
    width, height = pil_img.size

    img_buf = io.BytesIO()
    pil_img.save(img_buf, format="PNG")
    png_bytes = img_buf.getvalue()

    image_key = f"{owner_id}/pages/{doc_id}_1.png"
    storage.save_sync(image_key, png_bytes)

    page_info = PageIngestInfo(
        page_no=1,
        width=width,
        height=height,
        image_key=image_key,
        char_count=0,
        decision="ocr",
        text="",
        image_bytes=png_bytes,
    )

    return IngestResult(page_count=1, pages=[page_info])

import string
from typing import NamedTuple

import fitz  # PyMuPDF


class PageAnalysisResult(NamedTuple):
    text_chars: int
    printable_ratio: float
    image_coverage: float
    decision: str  # "text_layer", "ocr", "mixed"


PRINTABLE_SET = set(string.printable)


def analyze_pdf_page(page: fitz.Page, min_chars: int = 50) -> PageAnalysisResult:
    """Analyzes a PyMuPDF page to decide whether it is digital text, scanned, or mixed."""
    text = page.get_text("text")
    text_chars = len(text.strip())

    if text_chars > 0:
        printable_count = sum(1 for c in text if c in PRINTABLE_SET)
        printable_ratio = printable_count / len(text)
    else:
        printable_ratio = 0.0

    # Calculate image coverage ratio
    page_rect = page.rect
    page_area = page_rect.width * page_rect.height if page_rect.width and page_rect.height else 1.0

    image_area = 0.0
    image_list = page.get_images(full=True)
    for img in image_list:
        xref = img[0]
        rects = page.get_image_rects(xref)
        for r in rects:
            image_area += r.width * r.height

    image_coverage = min(1.0, image_area / page_area)

    # Decision logic per SPEC §7
    is_image_dominated = image_coverage > 0.85
    if text_chars >= min_chars and printable_ratio >= 0.80 and not is_image_dominated:
        if image_coverage > 0.20:
            decision = "mixed"
        else:
            decision = "text_layer"
    else:
        decision = "ocr"

    return PageAnalysisResult(
        text_chars=text_chars,
        printable_ratio=printable_ratio,
        image_coverage=image_coverage,
        decision=decision,
    )

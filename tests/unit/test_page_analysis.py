import fitz

from app.pipeline.page_analysis import analyze_pdf_page


def test_analyze_digital_pdf_page() -> None:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    # Insert text (> 50 chars)
    page.insert_text(
        (50, 50),
        "This is a digital question paper with clear text layer. Question 1. What is energy?",
    )

    result = analyze_pdf_page(page, min_chars=50)
    assert result.decision == "text_layer"
    assert result.text_chars > 50
    assert result.printable_ratio > 0.9
    assert result.image_coverage == 0.0
    doc.close()


def test_analyze_scanned_pdf_page() -> None:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    # No text inserted (simulating scanned page)

    result = analyze_pdf_page(page, min_chars=50)
    assert result.decision == "ocr"
    assert result.text_chars == 0
    doc.close()

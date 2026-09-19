import uuid

import pytest

from app.config import get_settings
from app.pipeline.extractors.gemini import GeminiExtractor
from app.pipeline.extractors.schemas import PageContext
from app.pipeline.grounding import verify_item_grounding


@pytest.mark.live
def test_gemini_extraction_live() -> None:
    settings = get_settings()
    api_key = settings.gemini_api_key.get_secret_value() if settings.gemini_api_key else ""
    if not api_key or "your_" in api_key or api_key == "test-key":
        pytest.skip("GEMINI_API_KEY is not configured in environment or is a placeholder")

    sample_page_text = """
    PHYSICS SECTION A
    Answer all questions. Each question carries 4 marks.

    1. A particle moves in a circle of radius 20 cm with a linear speed of 10 m/s.
    Find the angular velocity of the particle.
    (A) 50 rad/s
    (B) 25 rad/s
    (C) 100 rad/s
    (D) 10 rad/s
    Ans: (a)

    2. Which of the following quantities is a scalar?
    (A) Velocity
    (B) Acceleration
    (C) Electric potential
    (D) Force
    """

    extractor = GeminiExtractor()
    ctx = PageContext(
        document_id=uuid.uuid4(),
        page_no=1,
        total_pages=1,
        text=sample_page_text.strip(),
        text_source="text_layer",
    )

    extraction = extractor.extract_page(ctx)

    print("\n--- LIVE GEMINI EXTRACTION REPORT ---")
    print(f"Extracted item count: {len(extraction.items)}")
    print(f"Page flags: {extraction.flags}")

    assert len(extraction.items) >= 2, f"Expected at least 2 questions, got {len(extraction.items)}"

    for idx, item in enumerate(extraction.items):
        grounding = verify_item_grounding(item, source_text=sample_page_text)
        print(
            f"Question {idx+1} [Raw: {item.number_raw}, Norm: {item.number_norm}]: "
            f"Grounding={grounding:.3f}, Options={len(item.options)}, Flags={item.flags}"
        )
        assert grounding >= 0.70, f"Question {idx+1} failed grounding: {grounding}"
        assert len(item.options) == 4, f"Question {idx+1} should have 4 options"

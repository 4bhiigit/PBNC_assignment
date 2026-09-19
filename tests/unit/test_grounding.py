from app.pipeline.extractors.schemas import ExtractedItem, ExtractedOption
from app.pipeline.grounding import (
    check_count_mismatch,
    compute_item_grounding,
    verify_item_grounding,
)


def test_grounding_high_match() -> None:
    source = "1. What is the powerhouse of the cell? (A) Nucleus (B) Mitochondria (C) Ribosome"
    score = compute_item_grounding(
        item_text="What is the powerhouse of the cell?",
        options_text=["Nucleus", "Mitochondria", "Ribosome"],
        source_text=source,
    )
    assert score >= 0.85


def test_grounding_low_match_triggers_flag() -> None:
    source = "Section A: Physics and Chemistry instructions. Answer all questions."
    item = ExtractedItem(
        text="What is the capital of Australia and its economic output?",
        options=[
            ExtractedOption(label="A", raw_label="(a)", text="Sydney"),
            ExtractedOption(label="B", raw_label="(b)", text="Canberra"),
        ],
    )
    score = verify_item_grounding(item, source_text=source, threshold=0.70)
    assert score < 0.70
    assert "LOW_GROUNDING" in item.flags


def test_count_mismatch_detection() -> None:
    # Identical counts
    assert check_count_mismatch(5, 5) is False

    # Minor acceptable difference
    assert check_count_mismatch(5, 4) is False

    # Significant divergence (> 25% and diff >= 2)
    assert check_count_mismatch(10, 5) is True

    # One found questions, other found none
    assert check_count_mismatch(4, 0) is True
    assert check_count_mismatch(0, 3) is True

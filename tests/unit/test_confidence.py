import pytest

from app.pipeline.confidence import (
    calculate_confidence_score,
    compute_item_confidence_and_status,
    determine_question_status,
)


@pytest.mark.parametrize(
    "text_quality,grounding,completeness,llm_self,seq_consistency,flags,expected_score",
    [
        # Perfect extraction without penalties
        (1.0, 1.0, 1.0, 1.0, 1.0, [], 1.0),
        # Weights check: 0.30*0.8 + 0.25*0.9 + 0.25*1.0 + 0.10*1.0 + 0.10*1.0
        # = 0.24 + 0.225 + 0.25 + 0.10 + 0.10 = 0.915
        (0.8, 0.9, 1.0, 1.0, 1.0, [], 0.915),
        # Clean stitched question penalty: -0.05
        (1.0, 1.0, 1.0, 1.0, 1.0, ["CROSS_PAGE_STITCHED"], 0.95),
        # Uncertain stitched question penalty: -0.15
        (1.0, 1.0, 1.0, 1.0, 1.0, ["STITCH_UNCERTAIN"], 0.85),
        # Fallback used penalty: -0.10
        (1.0, 1.0, 1.0, 1.0, 1.0, ["LLM_FALLBACK_USED"], 0.90),
        # Multiple penalties combined: -0.05 - 0.10 = -0.15
        (1.0, 1.0, 1.0, 1.0, 1.0, ["CROSS_PAGE_STITCHED", "LLM_FALLBACK_USED"], 0.85),
        # Clamping floor at 0.0
        (0.0, 0.0, 0.0, 0.0, 0.0, ["STITCH_UNCERTAIN", "LLM_FALLBACK_USED"], 0.0),
    ],
)
def test_calculate_confidence_score(
    text_quality: float,
    grounding: float,
    completeness: float,
    llm_self: float,
    seq_consistency: float,
    flags: list[str],
    expected_score: float,
) -> None:
    score = calculate_confidence_score(
        text_quality=text_quality,
        grounding=grounding,
        completeness=completeness,
        llm_self=llm_self,
        sequence_consistency=seq_consistency,
        flags=flags,
    )
    assert score == pytest.approx(expected_score, rel=1e-3)


@pytest.mark.parametrize(
    "confidence,flags,expected_status",
    [
        # High confidence >= 0.85 -> extracted
        (0.95, [], "extracted"),
        (0.85, ["CROSS_PAGE_STITCHED"], "extracted"),
        # Medium confidence 0.60..0.85 -> partial
        (0.84, [], "partial"),
        (0.60, [], "partial"),
        # Low confidence < 0.60 -> needs_review
        (0.59, [], "needs_review"),
        (0.20, [], "needs_review"),
        # Critical flags override high score to force needs_review
        (0.99, ["MISSING_TEXT"], "needs_review"),
        (0.99, ["MCQ_OPTIONS_LT_2"], "needs_review"),
        (0.99, ["LOW_GROUNDING"], "needs_review"),
        (0.99, ["ORPHAN_FRAGMENT"], "needs_review"),
        (0.99, ["ANSWER_OUT_OF_RANGE"], "needs_review"),
        (0.99, ["PAGE_FAILED"], "needs_review"),
    ],
)
def test_determine_question_status(
    confidence: float, flags: list[str], expected_status: str
) -> None:
    status = determine_question_status(confidence=confidence, flags=flags)
    assert status == expected_status


def test_compute_item_confidence_and_status_mcq() -> None:
    conf, status, flags = compute_item_confidence_and_status(
        text="Which planet is known as the Red Planet?",
        question_type="mcq_single",
        options=[
            {"label": "A", "raw_label": "(a)", "text": "Venus"},
            {"label": "B", "raw_label": "(b)", "text": "Mars"},
            {"label": "C", "raw_label": "(c)", "text": "Jupiter"},
            {"label": "D", "raw_label": "(d)", "text": "Saturn"},
        ],
        number_norm="1",
        flags=[],
        ocr_confidence=0.95,
        grounding_score=0.98,
        llm_self_confidence=1.0,
    )
    assert conf >= 0.85
    assert status == "extracted"
    assert "MISSING_TEXT" not in flags
    assert "MCQ_OPTIONS_LT_2" not in flags


def test_compute_item_confidence_and_status_critical_flag_override() -> None:
    # MCQ with only 1 option should detect MCQ_OPTIONS_LT_2 and force status='needs_review'
    conf, status, flags = compute_item_confidence_and_status(
        text="What is the speed of light in vacuum?",
        question_type="mcq_single",
        options=[{"label": "A", "raw_label": "(a)", "text": "3x10^8 m/s"}],
        number_norm="2",
        flags=[],
        ocr_confidence=1.0,
        grounding_score=1.0,
        llm_self_confidence=1.0,
    )
    assert "MCQ_OPTIONS_LT_2" in flags
    assert status == "needs_review"

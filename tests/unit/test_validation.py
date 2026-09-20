from app.pipeline.validation import (
    CRITICAL_FLAGS,
    FLAG_CATALOGUE,
    evaluate_completeness,
    evaluate_sequence_consistency,
    get_flag_severity,
)


def test_flag_catalogue_completeness() -> None:
    expected_flags = [
        "MISSING_NUMBER",
        "NUMBER_INFERRED",
        "NUMBER_GAP",
        "DUPLICATE_NUMBER",
        "OPTIONS_INCOMPLETE",
        "MCQ_OPTIONS_LT_2",
        "LOW_OCR_CONFIDENCE",
        "LOW_RESOLUTION",
        "BLURRY",
        "ROTATED_CORRECTED",
        "LOW_GROUNDING",
        "COUNT_MISMATCH",
        "CROSS_PAGE_STITCHED",
        "STITCH_UNCERTAIN",
        "ORPHAN_FRAGMENT",
        "FIGURE_UNVERIFIED",
        "TABLE_UNVERIFIED",
        "LLM_FALLBACK_USED",
        "ANSWER_NOT_FOUND",
        "ANSWER_AMBIGUOUS",
        "ANSWER_CONFLICT",
        "ANSWER_OUT_OF_RANGE",
        "ANSWER_DIGIT_MAPPED",
        "KEY_ENTRY_UNMATCHED",
        "PAGE_FAILED",
    ]
    for flag in expected_flags:
        assert flag in FLAG_CATALOGUE


def test_critical_flags_severities() -> None:
    for crit_flag in CRITICAL_FLAGS:
        assert get_flag_severity(crit_flag) == "critical"

    assert get_flag_severity("CROSS_PAGE_STITCHED") == "info"
    assert get_flag_severity("NUMBER_INFERRED") == "info"
    assert get_flag_severity("NUMBER_GAP") == "warning"


def test_evaluate_completeness_valid_mcq() -> None:
    score, detected = evaluate_completeness(
        text="A sample valid question text with sufficient length.",
        question_type="mcq_single",
        options=[
            {"label": "A", "raw_label": "(a)", "text": "Opt 1"},
            {"label": "B", "raw_label": "(b)", "text": "Opt 2"},
            {"label": "C", "raw_label": "(c)", "text": "Opt 3"},
            {"label": "D", "raw_label": "(d)", "text": "Opt 4"},
        ],
        number_norm="1",
        flags=[],
    )
    assert score == 1.0
    assert len(detected) == 0


def test_evaluate_completeness_missing_text() -> None:
    score, detected = evaluate_completeness(
        text="   ",
        question_type="numerical",
        options=[],
        number_norm="5",
        flags=[],
    )
    assert score <= 0.60
    assert "MISSING_TEXT" in detected


def test_evaluate_completeness_duplicate_options() -> None:
    score, detected = evaluate_completeness(
        text="A question text with duplicate option labels.",
        question_type="mcq_single",
        options=[
            {"label": "A", "raw_label": "(a)", "text": "Opt 1"},
            {"label": "A", "raw_label": "(a)", "text": "Opt 2"},
        ],
        number_norm="10",
        flags=[],
    )
    assert score <= 0.80
    assert "OPTIONS_INCOMPLETE" in detected


def test_evaluate_sequence_consistency() -> None:
    assert evaluate_sequence_consistency([]) == 1.0
    assert evaluate_sequence_consistency(["NUMBER_GAP"]) == 0.70
    assert evaluate_sequence_consistency(["DUPLICATE_NUMBER"]) == 0.50
    assert evaluate_sequence_consistency(["NUMBER_GAP", "DUPLICATE_NUMBER"]) == 0.20

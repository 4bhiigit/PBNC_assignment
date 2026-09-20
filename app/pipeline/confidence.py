"""Confidence calculation engine implementing SPEC §10 formula and threshold rules."""

from typing import Any

from app.pipeline.validation import (
    CRITICAL_FLAGS,
    evaluate_completeness,
    evaluate_sequence_consistency,
)


def calculate_confidence_score(
    text_quality: float,
    grounding: float,
    completeness: float,
    llm_self: float,
    sequence_consistency: float,
    flags: list[str],
    unverified_figures_count: int = 0,
) -> float:
    """Calculates question extraction confidence score (0.0 to 1.0) strictly per SPEC §10.

    Formula:
    base = (0.30*text_quality + 0.25*grounding + 0.25*completeness
            + 0.10*llm_self + 0.10*sequence_consistency)
    penalties:
      -0.05 CROSS_PAGE_STITCHED
      -0.15 STITCH_UNCERTAIN
      -0.05 per unverified figure/table
      -0.10 LLM_FALLBACK_USED
    confidence = clamp(base - penalties, 0.0, 1.0)
    """
    base = (
        0.30 * text_quality
        + 0.25 * grounding
        + 0.25 * completeness
        + 0.10 * llm_self
        + 0.10 * sequence_consistency
    )

    penalties = 0.0
    if "CROSS_PAGE_STITCHED" in flags:
        penalties += 0.05
    if "STITCH_UNCERTAIN" in flags:
        penalties += 0.15
    if "LLM_FALLBACK_USED" in flags:
        penalties += 0.10
    if "FIGURE_UNVERIFIED" in flags:
        penalties += 0.05
    if "TABLE_UNVERIFIED" in flags:
        penalties += 0.05
    if unverified_figures_count > 0:
        # Avoid double penalizing if flag is already counted
        additional = max(
            0,
            unverified_figures_count
            - (1 if "FIGURE_UNVERIFIED" in flags else 0)
            - (1 if "TABLE_UNVERIFIED" in flags else 0),
        )
        penalties += 0.05 * additional

    raw_conf = max(0.0, min(1.0, base - penalties))
    return round(raw_conf, 3)


def determine_question_status(
    confidence: float,
    flags: list[str],
    conf_extracted_min: float = 0.85,
    conf_partial_min: float = 0.60,
) -> str:
    """Assigns question status ('extracted', 'partial', 'needs_review').

    Critical flags always force 'needs_review' regardless of confidence score.
    """
    has_critical = any(f in CRITICAL_FLAGS for f in flags)
    if has_critical or confidence < conf_partial_min:
        return "needs_review"
    if confidence >= conf_extracted_min:
        return "extracted"
    return "partial"


def compute_item_confidence_and_status(
    text: str,
    question_type: str,
    options: list[dict[str, Any]],
    number_norm: str | None,
    flags: list[str],
    ocr_confidence: float | None = None,
    grounding_score: float | None = None,
    llm_self_confidence: float | None = None,
    conf_extracted_min: float = 0.85,
    conf_partial_min: float = 0.60,
) -> tuple[float, str, list[str]]:
    """Evaluates question confidence, status, and appends newly detected quality flags."""
    updated_flags = list(flags)

    # 1. Text quality: 1.0 for clean text layer, else OCR mean confidence
    text_quality = ocr_confidence if ocr_confidence is not None else 1.0

    # 2. Grounding: 0.90 default if uncomputed
    grounding = grounding_score if grounding_score is not None else 0.90

    # 3. Completeness check
    completeness, new_flags = evaluate_completeness(
        text=text,
        question_type=question_type,
        options=options,
        number_norm=number_norm,
        flags=updated_flags,
    )
    for nf in new_flags:
        if nf not in updated_flags:
            updated_flags.append(nf)

    # 4. LLM self confidence
    llm_self = llm_self_confidence if llm_self_confidence is not None else 1.0

    # 5. Sequence consistency
    seq_consistency = evaluate_sequence_consistency(updated_flags)

    # 6. Calculate base score & apply penalties
    conf = calculate_confidence_score(
        text_quality=text_quality,
        grounding=grounding,
        completeness=completeness,
        llm_self=llm_self,
        sequence_consistency=seq_consistency,
        flags=updated_flags,
    )

    # 7. Determine status
    status = determine_question_status(
        confidence=conf,
        flags=updated_flags,
        conf_extracted_min=conf_extracted_min,
        conf_partial_min=conf_partial_min,
    )

    return conf, status, updated_flags

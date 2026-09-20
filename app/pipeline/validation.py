"""Quality flag definitions, severity classifications, and pure validation functions."""

from typing import Any

# Complete Flag Catalogue from SPEC §10
FLAG_CATALOGUE: dict[str, dict[str, str]] = {
    # Numbering and Sequence flags
    "MISSING_NUMBER": {
        "severity": "warning",
        "description": "Question number was missing from original source text.",
    },
    "NUMBER_INFERRED": {
        "severity": "info",
        "description": "Question number was inferred from sequence continuity.",
    },
    "NUMBER_GAP": {
        "severity": "warning",
        "description": "Gap detected in question numbering sequence.",
    },
    "DUPLICATE_NUMBER": {
        "severity": "warning",
        "description": "Duplicate question number found in the same section.",
    },
    # Question text and options flags
    "MISSING_TEXT": {
        "severity": "critical",
        "description": "Question text is empty or unreadably short.",
    },
    "OPTIONS_INCOMPLETE": {
        "severity": "warning",
        "description": "Option labels have gaps or non-standard sequence.",
    },
    "MCQ_OPTIONS_LT_2": {
        "severity": "critical",
        "description": "MCQ question has fewer than two options.",
    },
    # Image & OCR quality flags
    "LOW_OCR_CONFIDENCE": {
        "severity": "warning",
        "description": "OCR word confidence is below quality threshold.",
    },
    "LOW_RESOLUTION": {
        "severity": "warning",
        "description": "Page image resolution is lower than standard DPI.",
    },
    "BLURRY": {
        "severity": "warning",
        "description": "Page image Laplacian blur variance indicates blurriness.",
    },
    "ROTATED_CORRECTED": {
        "severity": "info",
        "description": "Page orientation required rotation correction.",
    },
    # Extraction and Grounding flags
    "LOW_GROUNDING": {
        "severity": "critical",
        "description": "Extracted text has low fuzzy match against OCR ground truth.",
    },
    "COUNT_MISMATCH": {
        "severity": "warning",
        "description": "Mismatch between LLM extracted item count and rules regex count.",
    },
    "CROSS_PAGE_STITCHED": {
        "severity": "info",
        "description": "Question cleanly stitched across multiple pages.",
    },
    "STITCH_UNCERTAIN": {
        "severity": "warning",
        "description": "Question continuation stitched using heuristic criteria.",
    },
    "ORPHAN_FRAGMENT": {
        "severity": "critical",
        "description": "Continuation fragment found without preceding question stem.",
    },
    "FIGURE_UNVERIFIED": {
        "severity": "warning",
        "description": "Figure bounding box could not be cropped or verified.",
    },
    "TABLE_UNVERIFIED": {
        "severity": "warning",
        "description": "Table markdown or crop region could not be verified.",
    },
    "LLM_FALLBACK_USED": {
        "severity": "warning",
        "description": "Extraction fell back to rules parser due to LLM failure/timeout.",
    },
    # Answer Key and Reconciliation flags
    "ANSWER_NOT_FOUND": {
        "severity": "warning",
        "description": "No corresponding answer key entry was found for question.",
    },
    "ANSWER_AMBIGUOUS": {
        "severity": "warning",
        "description": "Multiple ambiguous key candidates found without section distinction.",
    },
    "ANSWER_CONFLICT": {
        "severity": "warning",
        "description": "Conflicting answer entries found across answer sources.",
    },
    "ANSWER_OUT_OF_RANGE": {
        "severity": "critical",
        "description": "Answer key letter does not exist among question options.",
    },
    "ANSWER_DIGIT_MAPPED": {
        "severity": "warning",
        "description": "Numerical key digit mapped to corresponding letter option.",
    },
    "KEY_ENTRY_UNMATCHED": {
        "severity": "warning",
        "description": "Answer key entry does not match any question in the document.",
    },
    "PAGE_FAILED": {
        "severity": "critical",
        "description": "Processing or OCR failed completely for this page.",
    },
}

# Critical flags that force status='needs_review' regardless of confidence score
CRITICAL_FLAGS: set[str] = {
    "MISSING_TEXT",
    "MCQ_OPTIONS_LT_2",
    "LOW_GROUNDING",
    "ORPHAN_FRAGMENT",
    "ANSWER_OUT_OF_RANGE",
    "PAGE_FAILED",
}


def get_flag_severity(flag_code: str) -> str:
    """Returns the severity for a flag code ('info', 'warning', 'critical')."""
    if flag_code in CRITICAL_FLAGS:
        return "critical"
    catalog_info = FLAG_CATALOGUE.get(flag_code)
    if catalog_info:
        return catalog_info["severity"]
    return "warning"


def evaluate_completeness(
    text: str,
    question_type: str,
    options: list[dict[str, Any]],
    number_norm: str | None,
    flags: list[str],
) -> tuple[float, list[str]]:
    """Evaluates question completeness score (0.0 to 1.0) and adds any detected flags.

    Checks:
    - Text presence (>= 5 chars)
    - MCQ options >= 2
    - Option labels contiguous and unique
    - Question number present
    """
    score = 1.0
    detected_flags: list[str] = []

    # 1. Check text presence
    if not text or len(text.strip()) < 5:
        score -= 0.40
        if "MISSING_TEXT" not in flags:
            detected_flags.append("MISSING_TEXT")

    # 2. Check MCQ options
    is_mcq = question_type.startswith("mcq") or len(options) > 0
    if is_mcq:
        if len(options) < 2:
            score -= 0.40
            if "MCQ_OPTIONS_LT_2" not in flags:
                detected_flags.append("MCQ_OPTIONS_LT_2")

        # Check option label uniqueness and sequence
        labels = [opt.get("label", "").strip().upper() for opt in options if opt.get("label")]
        if len(labels) != len(set(labels)):
            score -= 0.20
            if "OPTIONS_INCOMPLETE" not in flags and "OPTIONS_INCOMPLETE" not in detected_flags:
                detected_flags.append("OPTIONS_INCOMPLETE")
        elif len(labels) >= 2:
            # Check if labels form an expected alphabetic contiguous sequence (A, B, C...)
            expected = [chr(ord("A") + idx) for idx in range(len(labels))]
            if labels != expected:
                score -= 0.10
                if "OPTIONS_INCOMPLETE" not in flags and "OPTIONS_INCOMPLETE" not in detected_flags:
                    detected_flags.append("OPTIONS_INCOMPLETE")

    # 3. Check question number presence
    if not number_norm and "MISSING_NUMBER" in flags:
        score -= 0.20

    return max(0.0, score), detected_flags


def evaluate_sequence_consistency(flags: list[str]) -> float:
    """Evaluates numbering continuity score (0.0 to 1.0) based on sequence flags."""
    score = 1.0
    if "NUMBER_GAP" in flags:
        score -= 0.30
    if "DUPLICATE_NUMBER" in flags:
        score -= 0.50
    return round(max(0.0, score), 3)

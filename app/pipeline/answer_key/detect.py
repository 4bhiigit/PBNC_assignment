import re
from collections.abc import Sequence

ANSWER_KEY_HEADING_PATTERN = re.compile(
    r"(?i)(?:\b(?:answer\s*keys?|answers?|solutions?|key|ans\.?)\b|उत्तर\s*कुंजी|उत्तरमाला)"
)

DENSE_KEY_PAIR_PATTERN = re.compile(
    r"(?:(?:Q\.?|Que\.?)?\s*\d+\s*[-.:)]\s*(?:\([A-Da-d1-4]\)|[A-Da-d1-4]))"
)


EXACT_KEY_HEADINGS = {
    "answer",
    "answers",
    "answer key",
    "answer keys",
    "key",
    "keys",
    "solution",
    "solutions",
    "ans",
    "ans.",
    "उत्तर",
    "उत्तर कुंजी",
    "उत्तरमाला",
}

KEY_HEADING_PREFIX = re.compile(
    r"(?i)^(?:official|final|provisional|tentative|revised|model|complete|standard)?\s*"
    r"(?:answer\s*keys?|answers?|solutions?|key|ans\.?|उत्तर\s*कुंजी|उत्तरमाला)"
    r"(?:\s*[-:]|\s+for|\s+to|\s+of|\s*$)"
)


def is_answer_key_heading(line: str) -> bool:
    """Checks if a single line or heading text indicates an answer key section."""
    clean = line.strip().rstrip(":-. ")
    if not clean or len(clean) > 80:
        return False
    lower = clean.lower()
    if lower in EXACT_KEY_HEADINGS:
        return True
    if "answer key" in lower or "उत्तर कुंजी" in lower or "उत्तरमाला" in lower:
        return True
    if KEY_HEADING_PREFIX.match(clean):
        if any(
            w in lower
            for w in ("question", "without", "which", "what", "where", "how", "following")
        ):
            return False
        return True
    return False


def is_answer_key_page(
    page_type: str | None,
    text: str,
    section_heading: str | None = None,
) -> bool:
    """Determines whether a page contains an answer key.

    Uses page_type, section headings, and pattern density (multiple Q-A pairs per line).
    """
    if page_type == "answer_key":
        return True

    if section_heading and is_answer_key_heading(section_heading):
        return True

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return False

    # Check top 5 lines for answer key headings
    for line in lines[:5]:
        if is_answer_key_heading(line):
            return True

    # Check density of question-answer pairs
    total_pairs = sum(len(DENSE_KEY_PAIR_PATTERN.findall(line)) for line in lines)
    if total_pairs >= 6:
        # If there are 6+ compact pairs and relatively short average line length
        avg_line_len = sum(len(line) for line in lines) / len(lines)
        if avg_line_len < 60 or total_pairs >= 10:
            return True

    return False


def normalize_page_type(pt: str | None) -> str:
    """Normalizes raw page type strings to canonical categories."""
    if not pt:
        return "unknown"
    p = pt.strip().lower()
    if any(q_word in p for q_word in ("question", "exam", "quiz", "problem", "test", "mcq")):
        return "questions"
    if any(k_word in p for k_word in ("answer", "key", "solution", "उत्तर")):
        return "answer_key"
    if "instruction" in p or "cover" in p:
        return "instructions"
    if "passage" in p or "comprehension" in p:
        return "passage"
    if "mixed" in p or "combined" in p:
        return "mixed"
    return "other"


def detect_document_role(
    page_types: Sequence[str | None],
    questions_count: int = 0,
    answer_keys_count: int = 0,
    role_hint: str | None = None,
) -> str:
    """Computes the overall detected_role of a document based on its page classifications
    and extracted items.

    Returns one of: 'question_paper', 'answer_key', 'combined', or 'unknown'.
    """
    norm_types = [normalize_page_type(pt) for pt in page_types if pt]
    q_pages = norm_types.count("questions") + norm_types.count("mixed")
    k_pages = norm_types.count("answer_key")

    q_total = q_pages + (1 if questions_count > 0 else 0)
    k_total = k_pages + (1 if answer_keys_count > 0 else 0)

    if q_total > 0 and k_total > 0:
        return "combined"
    if k_total > 0 and q_total == 0:
        return "answer_key"
    if q_total > 0 and k_total == 0:
        return "question_paper"

    if role_hint in ("question_paper", "answer_key", "combined"):
        return role_hint

    return "unknown"

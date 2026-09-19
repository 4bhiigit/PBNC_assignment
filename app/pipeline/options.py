import re
from typing import NamedTuple


class OptionItem(NamedTuple):
    label: str  # Normalized label: "A", "B", "C", ...
    raw_label: str  # Exact text: "(a)", "A.", "1)", "[B]"
    text: str


# Single option label at start of line
OPTION_START_REGEX = re.compile(
    r"^(?:"
    r"\(([A-Da-d])\)|"  # (A), (a)
    r"\[([A-Da-d])\]|"  # [A], [a]
    r"([A-Da-d])[\.\)]|"  # A., a), A)
    r"\(([1-4])\)|"  # (1), (2), (3), (4)
    r"([1-4])\)|"  # 1), 2), 3), 4)
    r"\(([ivxIVX]{1,4})\)"  # (i), (ii), (iii), (iv)
    r")\s*(.*)$"
)

# Inline options pattern (multiple options on a single line)
INLINE_OPTIONS_REGEX = re.compile(
    r"(?:\s*|^)"
    r"(?:"
    r"\(([A-Da-d1-4]|(?:[ivxIVX]{1,4}))\)|"
    r"\[([A-Da-d])\]|"
    r"([A-Da-d])[\.\)]"
    r")\s+"
)

# Normalization mapping
DIGIT_TO_LETTER = {"1": "A", "2": "B", "3": "C", "4": "D"}
ROMAN_TO_LETTER = {
    "i": "A",
    "ii": "B",
    "iii": "C",
    "iv": "D",
    "I": "A",
    "II": "B",
    "III": "C",
    "IV": "D",
}


def normalize_option_label(raw: str) -> str:
    """Normalizes any option label to standard uppercase letter A, B, C, D..."""
    clean = re.sub(r"[\[\(\]\)\.\:\s]", "", raw)
    if clean.isdigit() and clean in DIGIT_TO_LETTER:
        return DIGIT_TO_LETTER[clean]
    lower = clean.lower()
    if lower in ROMAN_TO_LETTER:
        return ROMAN_TO_LETTER[lower]
    return clean.upper()


def match_stacked_option(line: str) -> OptionItem | None:
    """Checks if a single line starts with an option label."""
    clean = line.strip()
    match = OPTION_START_REGEX.match(clean)
    if not match:
        return None

    # Group 1: (A), Group 2: [A], Group 3: A., Group 4: (1), Group 5: 1), Group 6: (i)
    matched_label = next(g for g in match.groups()[:6] if g is not None)
    text = match.group(7).strip()
    raw_label = clean[: match.start(7)].strip()

    normalized = normalize_option_label(matched_label)
    return OptionItem(label=normalized, raw_label=raw_label, text=text)


def parse_inline_options(line: str) -> list[OptionItem]:
    """Extracts multiple options embedded on a single line."""
    clean = line.strip()
    matches = list(INLINE_OPTIONS_REGEX.finditer(clean))
    if len(matches) < 2:
        return []

    items: list[OptionItem] = []
    for i, m in enumerate(matches):
        raw_token = next(g for g in m.groups() if g is not None)
        start_text = m.end()
        end_text = matches[i + 1].start() if i + 1 < len(matches) else len(clean)
        opt_text = clean[start_text:end_text].strip()
        raw_label = m.group(0).strip()
        items.append(
            OptionItem(
                label=normalize_option_label(raw_token),
                raw_label=raw_label,
                text=opt_text,
            )
        )
    return items


def normalize_answer_value(raw: str) -> list[str]:
    """Extracts and normalizes answer value tokens (e.g. 'Ans: (b)' -> ['B'])."""
    clean = re.sub(
        r"^(?:ans(?:wer)?|option|correct)?[:\s\-\.]*", "", raw.strip(), flags=re.I
    ).strip()
    m = re.search(r"[\(\[]?([A-Za-z0-9]+)[\)\]]?", clean)
    if m:
        token = m.group(1)
        norm = normalize_option_label(token)
        return [norm]
    return [clean.upper()] if clean else []

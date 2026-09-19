import re
from typing import NamedTuple


class NumberMatch(NamedTuple):
    raw: str
    normalized: str
    rest_of_line: str


# Pattern matches:
# 1. Standard: 1., 1), (1), [1]
# 2. Question prefixes: Q1., Q.1, Q 1:, Q1:, Question 1:, Question 1., Question 1 -, Que. 4
# 3. Dash / colon: 1 -, 1:
# 4. Hindi prefixes: प्र. 1, प्र.1, प्रश्न 1, प्रश्न. 1
QUESTION_NUMBER_REGEX = re.compile(
    r"^(?:"
    r"(?:Question|Q\.?|Que\.?|प्र\.?|प्रश्न)\s*(\d{1,4})(?:\s*[:\.\-\)]|\s+)|"
    r"\((\d{1,4})\)|"
    r"\[(\d{1,4})\]|"
    r"(\d{1,4})\s*[\.\:\-\)]"
    r")\s*(.*)$",
    re.IGNORECASE,
)

SECTION_REGEX = re.compile(
    r"^(?:"
    r"(?:Section|Part|खंड|खण्ड|भाग)\b.*"
    r"|(?:Physics|Chemistry|Mathematics|Biology|General Knowledge|English|Hindi|Reasoning)\b.*"
    r")$",
    re.IGNORECASE,
)


def match_question_number(line: str) -> NumberMatch | None:
    """Detects and extracts question numbering from the start of a line."""
    clean = line.strip()
    match = QUESTION_NUMBER_REGEX.match(clean)
    if not match:
        return None

    # Find which group captured the number digits (groups 1 to 4)
    number_digits = match.group(1) or match.group(2) or match.group(3) or match.group(4)
    raw_number = clean[: match.start(5)].strip()
    rest = match.group(5).strip()

    return NumberMatch(
        raw=raw_number,
        normalized=number_digits,
        rest_of_line=rest,
    )


def match_section_heading(line: str) -> str | None:
    """Detects section or subject header lines."""
    clean = line.strip()
    match = SECTION_REGEX.match(clean)
    if match and len(clean) < 100:
        return clean
    return None


def normalize_number_string(raw: str) -> str | None:
    """Extracts normalized digit string from raw question numbering."""
    clean = raw.strip()
    digits = re.findall(r"\d+", clean)
    if digits:
        return str(int(digits[0]))
    return None

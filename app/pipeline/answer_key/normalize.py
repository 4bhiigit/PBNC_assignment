import re
from typing import Any

DIGIT_TO_LETTER_MAP = {
    "1": "A",
    "2": "B",
    "3": "C",
    "4": "D",
    "5": "E",
    "6": "F",
    "7": "G",
    "8": "H",
}


def normalize_answer_token(token: str) -> str:
    """Normalizes a single answer token by removing enclosing punctuation and uppercasing."""
    cleaned = token.strip()
    cleaned = re.sub(r"^[\[\(\s\.]+|[\]\)\s\.]+$", "", cleaned)
    return cleaned.upper()


def normalize_answer_string(raw_answer: str) -> list[str]:
    """Parses and normalizes a raw answer string into a list of normalized answer values.

    Handles:
    - Single letters: 'A', '(b)' -> ['A'], ['B']
    - Delimited lists: 'A, B', 'A/C', 'A & B', 'A or B' -> ['A', 'B'], ['A', 'C']
    - Contiguous letter combinations: 'AC', 'BCD' (2 to 4 letters) -> ['A', 'C'], ['B', 'C', 'D']
    - Digits: '1', '2' -> ['1'], ['2']
    - Numerical values: '12.5', '-4' -> ['12.5'], ['-4']
    """
    cleaned = raw_answer.strip()
    if not cleaned:
        return []

    # Strip prefix like "Ans:", "Ans -", "Answer:"
    cleaned = re.sub(r"(?i)^(?:ans(?:wer)?|key)\s*[:\-]?\s*", "", cleaned).strip()

    # Check for multi-answers with explicit delimiters: ',', ';', '/', '&', 'or', 'and'
    delimiters = re.split(r"[,;/&]|\b(?:or|and)\b", cleaned, flags=re.IGNORECASE)
    if len(delimiters) > 1:
        results: list[str] = []
        for part in delimiters:
            token = normalize_answer_token(part)
            if token and token not in results:
                results.append(token)
        if results:
            return sorted(results)

    # Check for contiguous 2-4 uppercase/lowercase letters like 'AC', 'AB', 'abd'
    stripped = re.sub(r"[\[\(\]\)\.\s]", "", cleaned)
    if 2 <= len(stripped) <= 4 and stripped.isalpha():
        chars = [c.upper() for c in stripped]
        return sorted(list(dict.fromkeys(chars)))

    # Single token (letter, digit, or numerical string)
    token = normalize_answer_token(cleaned)
    if token:
        return [token]

    return [cleaned]


def map_digits_to_letters_if_applicable(
    answer_values: list[str],
    question_options: list[dict[str, Any]],
) -> tuple[list[str], bool]:
    """Maps digit answers (1-4) to option letters (A-D) if the question options use letters.

    Returns:
        tuple[list[str], bool]: (normalized_values, was_mapped)
    """
    if not answer_values or not question_options:
        return answer_values, False

    # Check if all question option labels are uppercase letters A, B, C, D...
    option_labels = [opt.get("label", "").upper() for opt in question_options if opt.get("label")]
    if not option_labels:
        return answer_values, False

    all_options_are_letters = all(len(lbl) == 1 and "A" <= lbl <= "Z" for lbl in option_labels)
    if not all_options_are_letters:
        return answer_values, False

    # Check if all answer values are single digits present in DIGIT_TO_LETTER_MAP
    all_answers_are_digits = all(val in DIGIT_TO_LETTER_MAP for val in answer_values)
    if not all_answers_are_digits:
        return answer_values, False

    # Check that mapped letters actually exist in question options
    mapped_letters: list[str] = []
    for val in answer_values:
        letter = DIGIT_TO_LETTER_MAP[val]
        if letter in option_labels:
            mapped_letters.append(letter)
        else:
            return answer_values, False

    return mapped_letters, True

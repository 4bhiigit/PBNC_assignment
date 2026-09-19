import re
from typing import Any

from pydantic import BaseModel

from app.pipeline.answer_key.normalize import normalize_answer_string
from app.pipeline.numbering import match_section_heading, normalize_number_string

RANGE_PATTERN = re.compile(
    r"^(?:(?:Q|Que|Question)\.?\s*)?(\d+)\s*(?:-|–|—|\bto\b)\s*(\d+)\s*[:=\-]\s*([A-Za-z0-9,\s/\&]+)$",
    re.IGNORECASE,
)

SINGLE_LINE_PATTERN = re.compile(
    r"^(?:(?:Q|Que|Question)\.?\s*)?(\d+)\s*[-.:)]\s*([A-Za-z0-9,\(\)\[\]\.\s/\&\-]+)$",
    re.IGNORECASE,
)

INLINE_PAIRS_PATTERN = re.compile(
    r"(?:(?:Q|Que|Question)\.?\s*)?(\d+)\s*[-.:)]\s*(\([A-Za-z0-9]+\)|\[[A-Za-z0-9]+\]|[A-Za-z0-9,/\&]+)",
    re.IGNORECASE,
)

GRID_HEADER_PATTERN = re.compile(
    r"(?i)\b(?:q(?:ue|uestion)?\.?\s*(?:no\.?)?|no\.?)\b.*\b(?:ans(?:wer)?|key|opt(?:ion)?)\b"
)


class ParsedKeyEntry(BaseModel):
    page_no: int
    section: str | None = None
    number_raw: str
    number_norm: str
    answer_raw: str
    answer_value: list[str]
    parse_confidence: float = 1.0


def parse_answer_key_text(
    text: str,
    page_no: int,
    initial_section: str | None = None,
) -> list[ParsedKeyEntry]:
    """Deterministically extracts answer key entries from page text.

    Supports:
    - Single line entries: '1. A', 'Q. 1 - (b)', '1: C'
    - Ranges: '1-5: A', '6 to 10: B'
    - Multi-column / dense pairs: '1-A 2-C 3-D'
    - Tabular grids: '1 A 11 B 21 C'
    - Section tracking: 'Physics', 'Section A'
    """
    entries: list[ParsedKeyEntry] = []
    current_section = initial_section
    seen_numbers_in_section: set[tuple[str | None, str]] = set()

    def add_entry(num_raw: str, ans_raw: str, confidence: float = 1.0) -> None:
        norm_num = normalize_number_string(num_raw)
        if not norm_num:
            return
        key = (current_section, norm_num)
        if key in seen_numbers_in_section:
            # Duplicate entry in same section on same page
            return
        ans_values = normalize_answer_string(ans_raw)
        if not ans_values:
            return

        seen_numbers_in_section.add(key)
        entries.append(
            ParsedKeyEntry(
                page_no=page_no,
                section=current_section,
                number_raw=num_raw.strip(),
                number_norm=norm_num,
                answer_raw=ans_raw.strip(),
                answer_value=ans_values,
                parse_confidence=confidence,
            )
        )

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    for line in lines:
        # Check if line is a section header (e.g. 'Section A', 'Physics')
        section_match = match_section_heading(line)
        if section_match:
            current_section = section_match
            continue

        # Check for range: '1-5: A'
        range_match = RANGE_PATTERN.match(line)
        if range_match:
            start_s, end_s, ans_raw = range_match.groups()
            try:
                start_n = int(start_s)
                end_n = int(end_s)
                if 1 <= end_n - start_n <= 50:
                    for n in range(start_n, end_n + 1):
                        add_entry(str(n), ans_raw, confidence=0.95)
                    continue
            except ValueError:
                pass

        # Check for multiple inline pairs: '1-A 2-C 3-D 4-B'
        pairs = INLINE_PAIRS_PATTERN.findall(line)
        if len(pairs) >= 2:
            for num_raw, ans_raw in pairs:
                add_entry(num_raw, ans_raw, confidence=1.0)
            continue

        # Check for single line entry: '1. A', 'Q1: (b)'
        single_match = SINGLE_LINE_PATTERN.match(line)
        if single_match:
            num_raw, ans_raw = single_match.groups()
            # Ensure ans_raw is not an entire sentence/prose
            if len(ans_raw.split()) <= 4 and len(ans_raw) <= 30:
                add_entry(num_raw, ans_raw, confidence=1.0)
            continue

        # Check for space/tab-separated table row pairs: '1  A   2  B   3  C'
        tokens = line.split()
        if len(tokens) >= 4 and len(tokens) % 2 == 0:
            is_valid_row = True
            row_pairs: list[tuple[str, str]] = []
            for i in range(0, len(tokens), 2):
                num_tok = tokens[i].rstrip(".:-)")
                ans_tok = tokens[i + 1]
                if num_tok.isdigit() and len(ans_tok) <= 5:
                    row_pairs.append((num_tok, ans_tok))
                else:
                    is_valid_row = False
                    break
            if is_valid_row and row_pairs:
                for num_tok, ans_tok in row_pairs:
                    add_entry(num_tok, ans_tok, confidence=0.95)

    return entries


def merge_llm_answer_key_entries(
    deterministic_entries: list[ParsedKeyEntry],
    llm_raw_entries: list[dict[str, Any]],
    page_no: int,
) -> list[ParsedKeyEntry]:
    """Merges LLM-extracted answer key entries with deterministically parsed entries.

    Deterministic entries take precedence; LLM entries fill gaps for irregular layouts.
    """
    merged = list(deterministic_entries)
    existing_keys = {(e.section, e.number_norm) for e in merged}

    for item in llm_raw_entries:
        num_raw = str(item.get("number_raw", "")).strip()
        ans_raw = str(item.get("answer_raw", "")).strip()
        sec = item.get("section")
        if not num_raw or not ans_raw:
            continue

        norm_num = normalize_number_string(num_raw)
        if not norm_num:
            continue

        key = (sec, norm_num)
        if key not in existing_keys:
            ans_values = normalize_answer_string(ans_raw)
            if ans_values:
                existing_keys.add(key)
                merged.append(
                    ParsedKeyEntry(
                        page_no=page_no,
                        section=sec,
                        number_raw=num_raw,
                        number_norm=norm_num,
                        answer_raw=ans_raw,
                        answer_value=ans_values,
                        parse_confidence=0.90,
                    )
                )

    return merged

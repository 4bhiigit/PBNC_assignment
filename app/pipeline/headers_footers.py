import re

from rapidfuzz import fuzz

PAGE_NUMBER_REGEX = re.compile(
    r"^(?:Page\s+\d+(?:\s+of\s+\d+)?|\d+\s*/\s*\d+|[-—]\s*\d+\s*[-—]|\b\d+\b)$",
    re.IGNORECASE,
)


def is_page_number_line(line: str) -> bool:
    """Returns True if the line is an isolated page number or simple pagination marker."""
    return bool(PAGE_NUMBER_REGEX.match(line.strip()))


def find_repeated_header_footers(
    pages_lines: list[list[str]],
    threshold_ratio: float = 0.50,
) -> set[str]:
    """
    Finds header/footer lines that repeat across >= threshold_ratio of pages.
    Inspects the first 3 and last 3 lines of each page.
    """
    if len(pages_lines) < 2:
        return set()

    # Collect candidate edge lines per page
    edge_lines_per_page: list[list[str]] = []
    for lines in pages_lines:
        clean = [line_text.strip() for line_text in lines if line_text.strip()]
        if not clean:
            edge_lines_per_page.append([])
            continue
        top = clean[:3]
        bottom = clean[-3:] if len(clean) > 3 else clean
        edge_lines_per_page.append(top + bottom)

    # Count occurrences using fuzzy matching
    min_occurrences = max(2, int(len(pages_lines) * threshold_ratio))
    repeated: set[str] = set()

    all_candidates = [line_text for page in edge_lines_per_page for line_text in page]
    unique_candidates = list(set(all_candidates))

    for cand in unique_candidates:
        if len(cand) < 3 or is_page_number_line(cand):
            continue
        count = 0
        for page_cands in edge_lines_per_page:
            if any(fuzz.ratio(cand.lower(), pc.lower()) >= 85 for pc in page_cands):
                count += 1
        if count >= min_occurrences:
            repeated.add(cand.lower())

    return repeated


def clean_page_lines(lines: list[str], repeated_headers: set[str] | None = None) -> list[str]:
    """Filters out detected repeated headers/footers and standalone page numbers."""
    headers = repeated_headers or set()
    cleaned: list[str] = []

    for i, line in enumerate(lines):
        clean = line.strip()
        if not clean:
            continue

        # Filter out standalone page numbers at top or bottom of page
        if (i < 3 or i >= len(lines) - 3) and is_page_number_line(clean):
            continue

        # Check against repeated headers
        if headers:
            lower = clean.lower()
            if any(fuzz.ratio(lower, h) >= 85 for h in headers):
                continue

        cleaned.append(line)

    return cleaned

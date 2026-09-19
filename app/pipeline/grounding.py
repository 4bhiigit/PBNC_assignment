import re

from rapidfuzz import fuzz

from app.pipeline.extractors.schemas import ExtractedItem


def normalize_text_for_grounding(text: str) -> str:
    """Normalizes text by lowercasing and collapsing whitespace/symbols."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def compute_item_grounding(
    item_text: str,
    options_text: list[str],
    source_text: str,
) -> float:
    """Computes a normalized grounding score between 0.0 and 1.0 using RapidFuzz partial ratio."""
    full_item = item_text + " " + " ".join(options_text)
    norm_query = normalize_text_for_grounding(full_item)
    norm_source = normalize_text_for_grounding(source_text)

    if not norm_query:
        return 1.0
    if not norm_source:
        return 0.0

    # RapidFuzz partial_ratio returns 0 - 100
    ratio = fuzz.partial_ratio(norm_query, norm_source)
    return round(float(ratio) / 100.0, 3)


def verify_item_grounding(
    item: ExtractedItem,
    source_text: str,
    threshold: float = 0.70,
) -> float:
    """Computes grounding score and appends LOW_GROUNDING flag if below threshold."""
    opts = [opt.text for opt in item.options]
    score = compute_item_grounding(item.text, opts, source_text)

    if score < threshold:
        if "LOW_GROUNDING" not in item.flags:
            item.flags.append("LOW_GROUNDING")

    return score


def check_count_mismatch(llm_count: int, rules_count: int) -> bool:
    """Returns True if the item count between LLM and regex rules diverges significantly."""
    if llm_count == rules_count:
        return False

    max_count = max(llm_count, rules_count)
    if max_count == 0:
        return False

    diff = abs(llm_count - rules_count)
    # Divergence > 25% with diff >= 2, or when one found items and the other found 0
    if (llm_count == 0 and rules_count > 0) or (rules_count == 0 and llm_count > 0):
        return True

    return diff >= 2 and (diff / max_count) > 0.25

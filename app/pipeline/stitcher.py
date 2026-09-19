import re
from typing import Any

from pydantic import BaseModel, Field

from app.pipeline.extractors.schemas import (
    ExtractedFigure,
    ExtractedItem,
    ExtractedOption,
    PageExtraction,
)


class PageExtractionInput(BaseModel):
    page_no: int
    page_type: str = "questions"
    section_heading: str | None = None
    ocr_confidence: float | None = 1.0
    text_source: str = "text_layer"
    extraction: PageExtraction


class StitchedQuestion(BaseModel):
    sequence: int = 1
    number_raw: str | None = None
    number_norm: str | None = None
    number_inferred: bool = False
    section: str | None = None
    type: str = "unknown"
    text: str
    options: list[ExtractedOption] = Field(default_factory=list)
    source_pages: list[int] = Field(default_factory=list)
    source_bboxes: dict[str, Any] = Field(default_factory=dict)
    extraction_method: str = "rules"
    ocr_confidence: float | None = None
    grounding_score: float | None = None
    llm_self_confidence: float | None = None
    confidence: float = 1.0
    status: str = "extracted"
    flags: list[str] = Field(default_factory=list)
    inline_answer_raw: str | None = None
    figures: list[ExtractedFigure] = Field(default_factory=list)
    table_markdown: str | None = None


def join_stitched_text(text_a: str, text_b: str) -> str:
    """Joins two consecutive text blocks, de-hyphenating words split across page breaks."""
    text_a = text_a.rstrip()
    text_b = text_b.lstrip()
    if not text_a:
        return text_b
    if not text_b:
        return text_a

    # De-hyphenate word cut across page: "com- \n puter" -> "computer"
    if text_a.endswith("-") and len(text_a) >= 2 and text_a[-2].isalnum() and text_b[0].isalnum():
        return text_a[:-1] + text_b

    # If text_a ends with standard punctuation, join with space or newline
    return text_a + " " + text_b


def merge_extracted_options(
    opts_a: list[ExtractedOption],
    opts_b: list[ExtractedOption],
) -> list[ExtractedOption]:
    """Appends continuation options, relabeling if duplicate letters are encountered."""
    merged = list(opts_a)
    existing_labels = {opt.label.upper() for opt in merged}

    next_char_code = ord("A") + len(merged)

    for opt in opts_b:
        label = opt.label.upper()
        if label in existing_labels:
            new_label = (
                chr(next_char_code)
                if next_char_code <= ord("Z")
                else f"OPT_{len(merged)+1}"
            )
            merged.append(
                ExtractedOption(
                    label=new_label,
                    raw_label=opt.raw_label,
                    text=opt.text,
                )
            )
            existing_labels.add(new_label)
            next_char_code += 1
        else:
            merged.append(opt)
            existing_labels.add(label)
            next_char_code = max(
                next_char_code,
                ord(label) + 1 if len(label) == 1 else next_char_code,
            )

    return merged


def is_heuristic_continuation(prev_item: ExtractedItem, curr_item: ExtractedItem) -> bool:
    """Detects if curr_item is a continuation of prev_item without explicit flags."""
    # curr_item must lack a distinct question number
    if curr_item.number_raw or curr_item.number_norm:
        return False

    # curr_item starts lowercase or with an option-like label
    text = curr_item.text.strip()
    starts_lower = bool(text and text[0].islower())
    starts_with_option = (
        bool(re.match(r"^[\(\[]?[a-dA-D1-4ivx]+[\)\.\]]", text)) or bool(curr_item.options)
    )

    # prev_item looks unfinished: no terminal punctuation or incomplete MCQ
    prev_text = prev_item.text.strip()
    unfinished_punct = bool(prev_text and prev_text[-1] not in ".?!:)\"")
    incomplete_mcq = (
        (prev_item.question_type == "mcq" or bool(prev_item.options))
        and len(prev_item.options) < 2
    )

    return (starts_lower or starts_with_option) and (unfinished_punct or incomplete_mcq)


def stitch_document_extractions(pages_input: list[PageExtractionInput]) -> list[StitchedQuestion]:
    """Stitches question fragments across pages into full questions, applying flags."""
    stitched: list[StitchedQuestion] = []
    current_q: StitchedQuestion | None = None

    for p in pages_input:
        page_no = p.page_no
        items = p.extraction.items

        for idx, item in enumerate(items):
            is_first_on_page = (idx == 0)

            # Check if this item continues current_q
            should_stitch = False
            stitch_uncertain = False

            if current_q is not None and is_first_on_page:
                has_continues = bool(current_q.flags and "CONTINUES_NEXT_PAGE" in current_q.flags)
                has_no_number = not (item.number_raw or item.number_norm)

                if has_continues and item.starts_on_previous_page:
                    should_stitch = True
                elif item.starts_on_previous_page and has_no_number:
                    should_stitch = True
                    if not has_continues:
                        stitch_uncertain = True
                elif has_continues and has_no_number:
                    should_stitch = True
                    if not item.starts_on_previous_page:
                        stitch_uncertain = True
                elif is_heuristic_continuation(
                    ExtractedItem(
                        text=current_q.text,
                        options=current_q.options,
                        question_type=current_q.type,
                        number_raw=current_q.number_raw,
                    ),
                    item,
                ):
                    should_stitch = True
                    stitch_uncertain = True

            if should_stitch and current_q is not None:
                # Merge into current_q
                current_q.text = join_stitched_text(current_q.text, item.text)
                current_q.options = merge_extracted_options(current_q.options, item.options)
                if page_no not in current_q.source_pages:
                    current_q.source_pages.append(page_no)

                current_q.figures.extend(item.figures)
                if item.table_markdown:
                    current_q.table_markdown = (
                        (current_q.table_markdown + "\n\n" + item.table_markdown)
                        if current_q.table_markdown
                        else item.table_markdown
                    )
                if item.inline_answer_raw and not current_q.inline_answer_raw:
                    current_q.inline_answer_raw = item.inline_answer_raw

                # Merge flags
                if stitch_uncertain:
                    if "STITCH_UNCERTAIN" not in current_q.flags:
                        current_q.flags.append("STITCH_UNCERTAIN")
                else:
                    if "CROSS_PAGE_STITCHED" not in current_q.flags:
                        current_q.flags.append("CROSS_PAGE_STITCHED")

                # Remove temporary marker
                if "CONTINUES_NEXT_PAGE" in current_q.flags:
                    current_q.flags.remove("CONTINUES_NEXT_PAGE")

                # If the continuation item also continues on next page, mark it
                if item.continues_on_next_page:
                    current_q.flags.append("CONTINUES_NEXT_PAGE")

            else:
                # Close previous question if pending
                if current_q is not None:
                    if "CONTINUES_NEXT_PAGE" in current_q.flags:
                        current_q.flags.remove("CONTINUES_NEXT_PAGE")
                    stitched.append(current_q)
                    current_q = None

                # Check if item is an orphan fragment
                is_orphan = (
                    is_first_on_page
                    and item.starts_on_previous_page
                    and not (item.number_raw or item.number_norm)
                )

                item_flags = list(item.flags)
                if is_orphan and "ORPHAN_FRAGMENT" not in item_flags:
                    item_flags.append("ORPHAN_FRAGMENT")
                if item.continues_on_next_page:
                    item_flags.append("CONTINUES_NEXT_PAGE")

                current_q = StitchedQuestion(
                    sequence=len(stitched) + 1,
                    number_raw=item.number_raw,
                    number_norm=item.number_norm,
                    number_inferred=False,
                    section=p.section_heading,
                    type=item.question_type,
                    text=item.text,
                    options=list(item.options),
                    source_pages=[page_no],
                    source_bboxes={},
                    ocr_confidence=p.ocr_confidence,
                    llm_self_confidence=item.self_confidence,
                    flags=item_flags,
                    inline_answer_raw=item.inline_answer_raw,
                    figures=list(item.figures),
                    table_markdown=item.table_markdown,
                )

    if current_q is not None:
        if "CONTINUES_NEXT_PAGE" in current_q.flags:
            current_q.flags.remove("CONTINUES_NEXT_PAGE")
        stitched.append(current_q)

    # Post-processing: infer missing numbers, detect gaps & duplicates, compute confidence
    _resequence_and_audit_numbering(stitched)
    _compute_all_confidences(stitched)

    return stitched


def _resequence_and_audit_numbering(questions: list[StitchedQuestion]) -> None:
    """Audits numbering continuity per section, infers single missing numbers, flags gaps/dupes."""
    for idx, q in enumerate(questions):
        q.sequence = idx + 1

    # Group by section for continuity check
    sections: dict[str | None, list[StitchedQuestion]] = {}
    for q in questions:
        sections.setdefault(q.section, []).append(q)

    for _, sec_questions in sections.items():
        seen_numbers: set[str] = set()

        for i, q in enumerate(sec_questions):
            # 1. Check for single inferred number between n-1 and n+1
            if not q.number_norm:
                prev_norm = sec_questions[i - 1].number_norm if i > 0 else None
                next_norm = sec_questions[i + 1].number_norm if i + 1 < len(sec_questions) else None

                if prev_norm and next_norm and prev_norm.isdigit() and next_norm.isdigit():
                    p_num, n_num = int(prev_norm), int(next_norm)
                    if n_num == p_num + 2:
                        q.number_norm = str(p_num + 1)
                        q.number_inferred = True
                        if "NUMBER_INFERRED" not in q.flags:
                            q.flags.append("NUMBER_INFERRED")

                if (
                    not q.number_norm
                    and "ORPHAN_FRAGMENT" not in q.flags
                    and "MISSING_NUMBER" not in q.flags
                ):
                    q.flags.append("MISSING_NUMBER")

            # 2. Check duplicates
            if q.number_norm:
                if q.number_norm in seen_numbers:
                    if "DUPLICATE_NUMBER" not in q.flags:
                        q.flags.append("DUPLICATE_NUMBER")
                else:
                    seen_numbers.add(q.number_norm)

            # 3. Check gaps vs previous number
            if i > 0 and q.number_norm and q.number_norm.isdigit():
                prev_norm = sec_questions[i - 1].number_norm
                if prev_norm and prev_norm.isdigit():
                    diff = int(q.number_norm) - int(prev_norm)
                    if diff > 1 and "NUMBER_GAP" not in q.flags:
                        q.flags.append("NUMBER_GAP")


def compute_question_confidence(q: StitchedQuestion) -> float:
    """Computes confidence score (0.0 to 1.0) strictly per SPEC §10."""
    # text_quality: 1.0 if clean text layer, else OCR mean confidence
    text_quality = q.ocr_confidence if q.ocr_confidence is not None else 1.0

    # grounding: from rapidfuzz check, default 0.90 if not yet evaluated
    grounding = q.grounding_score if q.grounding_score is not None else 0.90

    # completeness check
    completeness = 1.0
    if not q.text or len(q.text.strip()) < 5:
        completeness -= 0.40
        if "MISSING_TEXT" not in q.flags:
            q.flags.append("MISSING_TEXT")

    is_mcq = q.type.startswith("mcq") or len(q.options) > 0
    if is_mcq:
        if len(q.options) < 2:
            completeness -= 0.40
            if "MCQ_OPTIONS_LT_2" not in q.flags:
                q.flags.append("MCQ_OPTIONS_LT_2")
        # Check option label uniqueness
        labels = [opt.label for opt in q.options]
        if len(labels) != len(set(labels)):
            completeness -= 0.20

    if not q.number_norm and "MISSING_NUMBER" in q.flags:
        completeness -= 0.20

    completeness = max(0.0, completeness)

    # llm_self confidence
    llm_self = q.llm_self_confidence if q.llm_self_confidence is not None else 1.0

    # sequence_consistency: gap or duplicate lowers it
    seq_consistency = 1.0
    if "NUMBER_GAP" in q.flags:
        seq_consistency -= 0.30
    if "DUPLICATE_NUMBER" in q.flags:
        seq_consistency -= 0.50
    seq_consistency = max(0.0, seq_consistency)

    # Base weighted sum
    base = (
        0.30 * text_quality
        + 0.25 * grounding
        + 0.25 * completeness
        + 0.10 * llm_self
        + 0.10 * seq_consistency
    )

    # Penalties from SPEC §10
    penalties = 0.0
    if "CROSS_PAGE_STITCHED" in q.flags:
        penalties += 0.05
    if "STITCH_UNCERTAIN" in q.flags:
        penalties += 0.15
    if "LLM_FALLBACK_USED" in q.flags:
        penalties += 0.10

    raw_conf = max(0.0, min(1.0, base - penalties))
    return round(raw_conf, 3)


def _compute_all_confidences(questions: list[StitchedQuestion]) -> None:
    """Computes confidence score and assigns status ('extracted', 'partial', 'needs_review')."""
    critical_flags = {
        "MISSING_TEXT",
        "MCQ_OPTIONS_LT_2",
        "LOW_GROUNDING",
        "ORPHAN_FRAGMENT",
        "ANSWER_OUT_OF_RANGE",
    }

    for q in questions:
        conf = compute_question_confidence(q)
        q.confidence = conf

        # Critical flags force needs_review regardless of score
        has_critical = any(f in critical_flags for f in q.flags)

        if has_critical or conf < 0.60:
            q.status = "needs_review"
        elif conf >= 0.85:
            q.status = "extracted"
        else:
            q.status = "partial"

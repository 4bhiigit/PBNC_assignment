import re

from app.pipeline.answer_key.detect import is_answer_key_heading
from app.pipeline.extractors.base import Extractor
from app.pipeline.extractors.schemas import (
    AnswerKeyItem,
    ExtractedItem,
    ExtractedOption,
    PageContext,
    PageExtraction,
)
from app.pipeline.numbering import match_question_number, match_section_heading
from app.pipeline.options import match_stacked_option, parse_inline_options

INLINE_ANSWER_REGEX = re.compile(
    r"^(?:Ans(?:wer)?|Correct(?:\s+Option)?|उत्तर)\s*[:\.\-]?\s*(\([A-Da-d1-4]\)|\[[A-Da-d]\]|[A-Da-d1-4]|True|False)",
    re.IGNORECASE,
)

ANSWER_KEY_PAIR_REGEX = re.compile(
    r"(?:^|\s+)(?:Q\.?)?(\d{1,4})\s*[\-\.\:\)]\s*(\([A-Da-d1-4]\)|[A-Da-d1-4])",
    re.IGNORECASE,
)


class RulesExtractor(Extractor):
    """Rule-based question and option extractor using deterministic regex parsers."""

    def extract_page(self, ctx: PageContext) -> PageExtraction:
        raw_lines = [line.strip() for line in ctx.text.splitlines() if line.strip()]
        if not raw_lines:
            return PageExtraction(page_type="other", items=[], answer_key_entries=[])

        # First, check if the page is primarily an answer key
        answer_key_entries = self._try_parse_answer_key_page(raw_lines)
        has_key_heading = any(is_answer_key_heading(line) for line in raw_lines[:5])
        if (has_key_heading and answer_key_entries) or (
            len(answer_key_entries) >= 3 and len(answer_key_entries) >= len(raw_lines) * 0.5
        ):
            return PageExtraction(
                page_type="answer_key",
                items=[],
                answer_key_entries=answer_key_entries,
            )

        items: list[ExtractedItem] = []
        current_section: str | None = None
        current_item: ExtractedItem | None = None

        for line in raw_lines:
            # 1. Section heading
            sec = match_section_heading(line)
            if sec:
                current_section = sec
                continue

            # 2. Check for inline options (e.g. "(A) x (B) y" or "(1) True (2) False")
            if current_item:
                inline_opts = parse_inline_options(line)
                if inline_opts:
                    for opt in inline_opts:
                        current_item.options.append(
                            ExtractedOption(
                                label=opt.label,
                                raw_label=opt.raw_label,
                                text=opt.text,
                            )
                        )
                    continue

                # If already inside an option block, subsequent stacked options take precedence
                stacked_opt = match_stacked_option(line)
                if stacked_opt and current_item.options:
                    current_item.options.append(
                        ExtractedOption(
                            label=stacked_opt.label,
                            raw_label=stacked_opt.raw_label,
                            text=stacked_opt.text,
                        )
                    )
                    continue

                # Alphabetic options (A-D) always take precedence over question numbers
                if stacked_opt and re.sub(r"[\[\(\]\)\.\:\s]", "", stacked_opt.raw_label).isalpha():
                    current_item.options.append(
                        ExtractedOption(
                            label=stacked_opt.label,
                            raw_label=stacked_opt.raw_label,
                            text=stacked_opt.text,
                        )
                    )
                    continue

                # Inline answer on current question
                ans_match = INLINE_ANSWER_REGEX.match(line)
                if ans_match:
                    current_item.inline_answer_raw = ans_match.group(1).strip("()[]")
                    continue

            # 3. Question number match
            num_match = match_question_number(line)
            if num_match:
                if current_item:
                    items.append(self._finalize_item(current_item))
                current_item = ExtractedItem(
                    number_raw=num_match.raw,
                    number_norm=num_match.normalized,
                    text=num_match.rest_of_line,
                    options=[],
                    self_confidence=0.90,
                )
                continue

            # 4. Standalone stacked option or continuation line
            if current_item:
                stacked_opt = match_stacked_option(line)
                if stacked_opt:
                    current_item.options.append(
                        ExtractedOption(
                            label=stacked_opt.label,
                            raw_label=stacked_opt.raw_label,
                            text=stacked_opt.text,
                        )
                    )
                    continue

                # If inside an existing option, append continuation line
                if current_item.options:
                    last_opt = current_item.options[-1]
                    last_opt.text = (last_opt.text + " " + line).strip()
                    continue

                # Otherwise, it is continuation text for the question body
                current_item.text = (current_item.text + " " + line).strip()

        if current_item:
            items.append(self._finalize_item(current_item))

        # Check for answer keys in a mixed page (e.g. at bottom)
        if not answer_key_entries:
            answer_key_entries = self._find_embedded_answer_keys(raw_lines, items)

        page_type = "questions" if items else ("answer_key" if answer_key_entries else "other")
        return PageExtraction(
            page_type=page_type,
            section_heading=current_section,
            items=items,
            answer_key_entries=answer_key_entries,
        )

    def _finalize_item(self, item: ExtractedItem) -> ExtractedItem:
        """Infer question type and clean whitespace."""
        item.text = item.text.strip()
        if len(item.options) >= 2:
            texts = [o.text.lower() for o in item.options]
            if len(item.options) == 2 and ("true" in texts or "false" in texts):
                item.question_type = "true_false"
            else:
                item.question_type = "mcq_single"
        elif "___" in item.text or "blank" in item.text.lower():
            item.question_type = "fill_blank"
        else:
            item.question_type = "short_answer"

        return item

    def _try_parse_answer_key_page(self, lines: list[str]) -> list[AnswerKeyItem]:
        """Parses lines if they contain dense number-answer pairs."""
        entries: list[AnswerKeyItem] = []
        for line in lines:
            matches = ANSWER_KEY_PAIR_REGEX.findall(line)
            for num, ans in matches:
                clean_ans = ans.strip("()[]").upper()
                entries.append(
                    AnswerKeyItem(
                        section=None,
                        number_raw=num,
                        answer_raw=clean_ans,
                    )
                )
        return entries

    def _find_embedded_answer_keys(
        self, lines: list[str], items: list[ExtractedItem]
    ) -> list[AnswerKeyItem]:
        """Finds answer key pairs that are not part of question bodies."""
        if not items:
            return self._try_parse_answer_key_page(lines)
        return []

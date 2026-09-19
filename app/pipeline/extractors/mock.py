from app.pipeline.extractors.base import Extractor
from app.pipeline.extractors.schemas import (
    ExtractedItem,
    ExtractedOption,
    PageContext,
    PageExtraction,
)


class MockExtractor(Extractor):
    """Deterministic extractor for automated testing without external models."""

    def __init__(self, predefined: dict[int, PageExtraction] | None = None) -> None:
        self.predefined = predefined or {}

    def extract_page(self, ctx: PageContext) -> PageExtraction:
        if ctx.page_no in self.predefined:
            return self.predefined[ctx.page_no]

        # Default deterministic parsing for simple test strings
        items: list[ExtractedItem] = []
        lines = [line.strip() for line in ctx.text.splitlines() if line.strip()]

        current_item: ExtractedItem | None = None
        for line in lines:
            if line.startswith("Q") or (line and line[0].isdigit() and "." in line[:4]):
                if current_item:
                    items.append(current_item)
                parts = line.split(".", 1)
                num = parts[0].replace("Q", "").strip()
                q_text = parts[1].strip() if len(parts) > 1 else line
                current_item = ExtractedItem(
                    number_raw=parts[0].strip(),
                    number_norm=num,
                    text=q_text,
                    question_type="mcq_single",
                    self_confidence=1.0,
                )
            elif current_item and line.startswith(("(", "A.", "B.", "C.", "D.")):
                label = line[1] if line.startswith("(") else line[0]
                current_item.options.append(
                    ExtractedOption(
                        label=label.upper(),
                        raw_label=line[:3].strip(),
                        text=line[3:].strip(),
                    )
                )
            elif current_item:
                current_item.text += " " + line

        if current_item:
            items.append(current_item)

        return PageExtraction(
            page_type="questions" if items else "other",
            items=items,
            answer_key_entries=[],
        )

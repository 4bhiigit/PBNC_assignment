import logging

from app.config import get_settings
from app.pipeline.extractors.base import Extractor
from app.pipeline.extractors.limiter import acquire_llm_slot
from app.pipeline.extractors.prompts import EXTRACTION_SYSTEM_PROMPT, build_page_prompt
from app.pipeline.extractors.provider import GeminiProvider, LLMProvider
from app.pipeline.extractors.rules import RulesExtractor
from app.pipeline.extractors.schemas import PageContext, PageExtraction

logger = logging.getLogger(__name__)


class GeminiExtractor(Extractor):
    """LLM-based extractor using Gemini with structured output and rules fallback."""

    def __init__(
        self,
        provider: LLMProvider | None = None,
        rules_fallback: Extractor | None = None,
    ) -> None:
        settings = get_settings()
        self.rules_fallback = rules_fallback or RulesExtractor()
        self.send_image_policy = settings.llm_send_image
        self.timeout_s = settings.llm_timeout_s

        if provider is not None:
            self.provider: LLMProvider | None = provider
        elif settings.gemini_api_key and settings.gemini_api_key.get_secret_value().strip():
            self.provider = GeminiProvider(
                api_key=settings.gemini_api_key.get_secret_value(),
                model=settings.gemini_model,
                timeout_s=settings.llm_timeout_s,
            )
        else:
            self.provider = None

    def _should_send_image(self, context: PageContext) -> bool:
        if not context.image_bytes:
            return False
        if self.send_image_policy == "always":
            return True
        if self.send_image_policy == "never":
            return False
        # "auto" policy: send image when OCR was used, confidence is low, or text layer is sparse
        if context.text_source != "text_layer":
            return True
        if context.ocr_confidence is not None and context.ocr_confidence < 0.90:
            return True
        if len(context.text.strip()) < 100:
            return True
        return False

    def extract_page(self, context: PageContext) -> PageExtraction:
        if self.provider is None:
            logger.info("No Gemini API key configured; falling back directly to RulesExtractor")
            return self._fallback_extraction(context, reason="no_api_key")

        send_image = self._should_send_image(context)
        image_bytes = context.image_bytes if send_image else None
        user_prompt = build_page_prompt(
            page_no=context.page_no,
            total_pages=context.total_pages,
            extracted_text=context.text,
            prev_page_context=context.prev_page_context,
        )

        last_error: Exception | None = None
        for attempt in range(2):
            try:
                with acquire_llm_slot(timeout_s=float(self.timeout_s)):
                    extraction = self.provider.generate_extraction(
                        prompt=user_prompt,
                        system_instruction=EXTRACTION_SYSTEM_PROMPT,
                        image_bytes=image_bytes,
                        image_mime="image/png",
                    )
                    return extraction
            except Exception as exc:
                last_error = exc
                if attempt == 0:
                    logger.warning(
                        "Gemini extraction attempt 1 for page %d failed (%s); retrying",
                        context.page_no,
                        exc,
                    )
                    continue
                logger.error(
                    "Gemini attempt 2 for page %d failed (%s); falling back to rules",
                    context.page_no,
                    exc,
                )

        return self._fallback_extraction(context, reason=str(last_error))

    def _fallback_extraction(self, context: PageContext, reason: str) -> PageExtraction:
        extraction = self.rules_fallback.extract_page(context)
        flag = "LLM_FALLBACK_USED"
        if flag not in extraction.flags:
            extraction.flags.append(flag)
        for item in extraction.items:
            if flag not in item.flags:
                item.flags.append(flag)
            if not item.notes:
                item.notes = f"LLM fallback used: {reason}"
        return extraction

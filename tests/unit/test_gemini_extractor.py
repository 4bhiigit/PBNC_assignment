import uuid
from unittest.mock import MagicMock

import pytest

from app.pipeline.extractors.gemini import GeminiExtractor
from app.pipeline.extractors.provider import GeminiProvider, LLMProvider
from app.pipeline.extractors.schemas import (
    ExtractedItem,
    ExtractedOption,
    PageContext,
    PageExtraction,
)


class MockSuccessProvider(LLMProvider):
    def __init__(self) -> None:
        self.call_count = 0

    def generate_extraction(
        self,
        prompt: str,
        system_instruction: str,
        image_bytes: bytes | None = None,
        image_mime: str = "image/png",
    ) -> PageExtraction:
        self.call_count += 1
        return PageExtraction(
            page_type="questions",
            items=[
                ExtractedItem(
                    number_raw="1.",
                    number_norm="1",
                    text="Mock question text",
                    options=[
                        ExtractedOption(label="A", raw_label="(a)", text="Opt A"),
                        ExtractedOption(label="B", raw_label="(b)", text="Opt B"),
                    ],
                )
            ],
        )


class FlakyProvider(LLMProvider):
    def __init__(self) -> None:
        self.attempts = 0

    def generate_extraction(
        self,
        prompt: str,
        system_instruction: str,
        image_bytes: bytes | None = None,
        image_mime: str = "image/png",
    ) -> PageExtraction:
        self.attempts += 1
        if self.attempts == 1:
            raise TimeoutError("Simulated LLM network timeout")
        return PageExtraction(
            page_type="questions",
            items=[ExtractedItem(number_raw="1.", number_norm="1", text="Recovered question")],
        )


class FailingProvider(LLMProvider):
    def generate_extraction(
        self,
        prompt: str,
        system_instruction: str,
        image_bytes: bytes | None = None,
        image_mime: str = "image/png",
    ) -> PageExtraction:
        raise RuntimeError("LLM service unavailable")


def test_gemini_extractor_success() -> None:
    provider = MockSuccessProvider()
    extractor = GeminiExtractor(provider=provider)
    ctx = PageContext(
        document_id=uuid.uuid4(),
        page_no=1,
        total_pages=1,
        text="1. Mock question text\n(a) Opt A\n(b) Opt B",
    )
    result = extractor.extract_page(ctx)
    assert len(result.items) == 1
    assert result.items[0].number_norm == "1"
    assert provider.call_count == 1


def test_gemini_extractor_retries_once() -> None:
    flaky = FlakyProvider()
    extractor = GeminiExtractor(provider=flaky)
    ctx = PageContext(
        document_id=uuid.uuid4(),
        page_no=1,
        total_pages=1,
        text="1. Recovered question",
    )
    result = extractor.extract_page(ctx)
    assert len(result.items) == 1
    assert result.items[0].text == "Recovered question"
    assert flaky.attempts == 2


def test_gemini_extractor_falls_back_to_rules() -> None:
    failing = FailingProvider()
    extractor = GeminiExtractor(provider=failing)
    ctx = PageContext(
        document_id=uuid.uuid4(),
        page_no=1,
        total_pages=1,
        text="1. Rules fallback question\n(A) True\n(B) False",
    )
    result = extractor.extract_page(ctx)
    assert len(result.items) == 1
    assert "LLM_FALLBACK_USED" in result.flags
    assert "LLM_FALLBACK_USED" in result.items[0].flags


def test_gemini_provider_empty_key_rejected() -> None:
    with pytest.raises(ValueError, match="Gemini API key must not be empty"):
        GeminiProvider(api_key="   ")


def test_gemini_provider_parses_parsed_object() -> None:
    provider = GeminiProvider(api_key="test-key")
    mock_extraction = PageExtraction(page_type="questions", items=[])
    mock_resp = MagicMock()
    mock_resp.parsed = mock_extraction
    provider.client = MagicMock()
    provider.client.models.generate_content.return_value = mock_resp

    result = provider.generate_extraction("prompt", "sys")
    assert result.page_type == "questions"


def test_gemini_provider_parses_dict_parsed_object() -> None:
    provider = GeminiProvider(api_key="test-key")
    mock_resp = MagicMock()
    mock_resp.parsed = {"page_type": "questions", "items": [{"number_raw": "1", "text": "Q1"}]}
    provider.client = MagicMock()
    provider.client.models.generate_content.return_value = mock_resp

    result = provider.generate_extraction("prompt", "sys")
    assert result.page_type == "questions"
    assert len(result.items) == 1
    assert result.items[0].text == "Q1"


def test_gemini_provider_parses_markdown_json() -> None:
    provider = GeminiProvider(api_key="test-key")
    mock_resp = MagicMock()
    mock_resp.parsed = None
    mock_resp.text = (
        '```json\n{"page_type": "questions", "items": [{"number_raw": "2", "text": "Q2"}]}\n```'
    )
    provider.client = MagicMock()
    provider.client.models.generate_content.return_value = mock_resp

    result = provider.generate_extraction("prompt", "sys")
    assert result.page_type == "questions"
    assert result.items[0].text == "Q2"


def test_gemini_provider_blocked_finish_reason() -> None:
    provider = GeminiProvider(api_key="test-key")
    mock_resp = MagicMock()
    mock_resp.parsed = None
    mock_resp.text = None
    candidate = MagicMock()
    candidate.finish_reason = "SAFETY"
    mock_resp.candidates = [candidate]
    provider.client = MagicMock()
    provider.client.models.generate_content.return_value = mock_resp

    with pytest.raises(ValueError, match="finish reason: SAFETY"):
        provider.generate_extraction("prompt", "sys")

import logging
import re
from abc import ABC, abstractmethod
from typing import Any

from google import genai
from google.genai import types

from app.pipeline.extractors.schemas import PageExtraction

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """Abstract interface for structured LLM extraction providers."""

    @abstractmethod
    def generate_extraction(
        self,
        prompt: str,
        system_instruction: str,
        image_bytes: bytes | None = None,
        image_mime: str = "image/png",
    ) -> PageExtraction:
        """Generates a structured PageExtraction from prompt and optional image."""
        pass


class GeminiProvider(LLMProvider):
    """Google Gemini provider using official google-genai SDK with structured output."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-3.6-flash",
        timeout_s: int = 30,
    ) -> None:
        clean_key = api_key.strip()
        if not clean_key:
            raise ValueError("Gemini API key must not be empty")
        self.client = genai.Client(api_key=clean_key)
        self.model = model
        self.timeout_s = timeout_s

    def generate_extraction(
        self,
        prompt: str,
        system_instruction: str,
        image_bytes: bytes | None = None,
        image_mime: str = "image/png",
    ) -> PageExtraction:
        contents: list[Any] = []

        if image_bytes:
            contents.append(types.Part.from_bytes(data=image_bytes, mime_type=image_mime))
        contents.append(prompt)

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=PageExtraction,
            system_instruction=system_instruction,
            temperature=0.0,
            http_options=types.HttpOptions(timeout=int(self.timeout_s * 1000)),
        )

        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=config,
        )

        if response.parsed is not None:
            if isinstance(response.parsed, PageExtraction):
                return response.parsed
            if isinstance(response.parsed, dict):
                return PageExtraction.model_validate(response.parsed)

        if response.text:
            text = response.text.strip()
            if "```" in text:
                match = re.search(
                    r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE
                )
                if match:
                    text = match.group(1).strip()
                else:
                    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
                    text = re.sub(r"\s*```$", "", text)
            return PageExtraction.model_validate_json(text)

        if response.candidates and response.candidates[0].finish_reason:
            reason = response.candidates[0].finish_reason
            raise ValueError(f"Gemini generation blocked or incomplete; finish reason: {reason}")

        raise ValueError("Gemini returned an empty response without text or parsed content")

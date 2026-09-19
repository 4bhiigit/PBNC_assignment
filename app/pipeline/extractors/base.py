from abc import ABC, abstractmethod

from app.pipeline.extractors.schemas import PageContext, PageExtraction


class Extractor(ABC):
    """Abstract base class for all page extractors (Rules, LLM, Mock)."""

    @abstractmethod
    def extract_page(self, ctx: PageContext) -> PageExtraction:
        """Extract structured questions and answer keys from a single page."""
        raise NotImplementedError

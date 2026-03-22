"""Fallback LLM provider: tries Gemini first, falls back to OpenAI."""

import logging
from typing import Dict, Optional

from .base_llm_provider import BaseLLMProvider, LLMProviderError, PatternParsingError

logger = logging.getLogger(__name__)


class FallbackLLMProvider(BaseLLMProvider):
    """Tries Gemini first, falls back to OpenAI on any failure."""

    def __init__(self) -> None:
        self._gemini: Optional[BaseLLMProvider] = None
        self._openai: Optional[BaseLLMProvider] = None

        try:
            from .gemini_provider import GeminiProvider
            self._gemini = GeminiProvider()
            logger.info("FallbackLLMProvider: Gemini ready")
        except Exception as e:
            logger.warning(f"FallbackLLMProvider: Gemini unavailable ({e})")

        try:
            from .openai_provider import OpenAIProvider
            self._openai = OpenAIProvider()
            logger.info("FallbackLLMProvider: OpenAI ready")
        except Exception as e:
            logger.warning(f"FallbackLLMProvider: OpenAI unavailable ({e})")

        if not self._gemini and not self._openai:
            raise LLMProviderError(
                "No LLM providers available. Set GEMINI_API_KEY or OPENAI_API_KEY."
            )

    def generate_patterns(self, email_text: str) -> Dict[str, Optional[str]]:
        """
        Generate patterns using Gemini with OpenAI fallback.

        Tries Gemini first. If it fails for any reason (timeout, API error,
        parse error), falls back to OpenAI.
        """
        if self._gemini:
            try:
                return self._gemini.generate_patterns(email_text)
            except Exception as e:
                logger.warning(f"Gemini failed, falling back to OpenAI: {e}")

        if self._openai:
            try:
                return self._openai.generate_patterns(email_text)
            except Exception as e:
                logger.error(f"OpenAI fallback also failed: {e}")
                raise LLMProviderError(
                    f"All LLM providers failed. Last error: {e}"
                )

        raise LLMProviderError("No LLM providers available.")

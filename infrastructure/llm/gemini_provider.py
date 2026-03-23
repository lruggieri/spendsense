"""Gemini LLM provider implementation for transaction pattern generation."""

import logging
import os
from typing import Dict, Optional

try:
    from google import genai
except ImportError:
    genai = None

from .base_llm_provider import BaseLLMProvider, LLMProviderError, PatternParsingError

logger = logging.getLogger(__name__)


class GeminiProvider(BaseLLMProvider):
    """Gemini LLM provider implementation."""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Gemini provider.

        Args:
            api_key: Gemini API key. If None, loads from environment variable.

        Raises:
            ValueError: If API key not found
            ImportError: If google-genai package not installed
        """
        if genai is None:
            raise ImportError(
                "google-genai package not installed. Install with: pip install google-genai"
            )

        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("Gemini API key not found. Set GEMINI_API_KEY environment variable.")

        self.client = genai.Client(
            api_key=self.api_key,
            http_options=genai.types.HttpOptions(timeout=10_000),  # 10 s (Gemini minimum)
        )
        self.model_name = "gemini-2.5-flash"

    def generate_patterns(self, email_text: str) -> Dict[str, Optional[str]]:
        """Generate regex patterns using Gemini."""
        try:
            prompt = self._build_prompt(email_text)
            response = self.client.models.generate_content(
                model=self.model_name, contents=prompt, config={"temperature": 0}
            )

            if not response.text:
                raise LLMProviderError("Empty response from Gemini")

            return self._parse_response(response.text)

        except Exception as e:
            if isinstance(e, (LLMProviderError, PatternParsingError)):
                raise
            logger.error(f"Gemini API error: {e}")
            raise LLMProviderError(f"Failed to generate patterns: {str(e)}")

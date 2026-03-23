"""OpenAI LLM provider implementation for transaction pattern generation."""

import logging
import os
from typing import Dict, Optional

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore[assignment, misc]

from .base_llm_provider import BaseLLMProvider, LLMProviderError, PatternParsingError

# Suppress OpenAI client debug logs — they dump full request bodies including email content
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseLLMProvider):
    """OpenAI LLM provider implementation."""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize OpenAI provider.

        Args:
            api_key: OpenAI API key. If None, loads from environment variable.

        Raises:
            ValueError: If API key not found
            ImportError: If openai package not installed
        """
        if OpenAI is None:
            raise ImportError(
                "openai package not installed. Install with: pip install openai"
            )

        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key not found. Set OPENAI_API_KEY environment variable.")

        self.client = OpenAI(api_key=self.api_key, timeout=5.0)
        self.model_name = "gpt-4o-mini"

    def generate_patterns(self, email_text: str) -> Dict[str, Optional[str]]:
        """Generate regex patterns using OpenAI."""
        try:
            prompt = self._build_prompt(email_text)
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
            )

            response_text = response.choices[0].message.content
            if not response_text:
                raise LLMProviderError("Empty response from OpenAI")

            return self._parse_response(response_text)

        except Exception as e:
            if isinstance(e, (LLMProviderError, PatternParsingError)):
                raise
            logger.error(f"OpenAI API error: {e}")
            raise LLMProviderError(f"Failed to generate patterns: {str(e)}")

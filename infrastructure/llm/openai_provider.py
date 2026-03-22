"""OpenAI LLM provider implementation for transaction pattern generation."""

import logging
import os
import re
from pathlib import Path
from typing import Dict, Optional

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore[assignment, misc]

from .base_llm_provider import BaseLLMProvider, LLMProviderError, PatternParsingError

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseLLMProvider):
    """OpenAI LLM provider implementation."""

    @staticmethod
    def _build_prompt(email_text: str) -> str:
        """Build the prompt with the email text from external template file."""
        current_dir = Path(__file__).parent
        prompt_file = current_dir / "pattern_generation_prompt.txt"

        try:
            prompt_template = prompt_file.read_text(encoding="utf-8")
            return prompt_template.replace("{email_text}", email_text)
        except FileNotFoundError:
            raise LLMProviderError(f"Prompt template file not found: {prompt_file}")
        except Exception as e:
            raise LLMProviderError(f"Error reading prompt template: {str(e)}")

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
        """
        Generate regex patterns using OpenAI.

        Args:
            email_text: Email body text to analyze

        Returns:
            Dictionary with 'amount_pattern', 'merchant_pattern', 'currency_pattern'

        Raises:
            LLMProviderError: If OpenAI API request fails
            PatternParsingError: If response cannot be parsed
        """
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

    def _parse_response(self, response_text: str) -> Dict[str, Optional[str]]:
        """
        Parse OpenAI response into pattern dictionary.

        Expected format:
        AMOUNT_PATTERN: <regex>
        MERCHANT_PATTERN: <regex>
        CURRENCY_PATTERN: <regex or "None">

        Args:
            response_text: Raw response from OpenAI

        Returns:
            Dictionary with parsed patterns

        Raises:
            PatternParsingError: If patterns cannot be extracted
        """
        patterns: Dict[str, Optional[str]] = {
            "amount_pattern": None,
            "merchant_pattern": None,
            "currency_pattern": None,
        }

        # Extract patterns using regex
        amount_match = re.search(r"AMOUNT_PATTERN:\s*(.+)", response_text)
        merchant_match = re.search(r"MERCHANT_PATTERN:\s*(.+)", response_text)
        currency_match = re.search(r"CURRENCY_PATTERN:\s*(.+)", response_text)

        # Check that all required pattern lines are present in response
        if not amount_match or not merchant_match or not currency_match:
            missing = []
            if not amount_match:
                missing.append("AMOUNT_PATTERN")
            if not merchant_match:
                missing.append("MERCHANT_PATTERN")
            if not currency_match:
                missing.append("CURRENCY_PATTERN")
            raise PatternParsingError(
                f"Incomplete patterns: missing {', '.join(missing)}. Response: {response_text}"
            )

        # Parse pattern values (may be "None")
        amount_str = amount_match.group(1).strip()
        patterns["amount_pattern"] = None if amount_str.lower() == "none" else amount_str

        merchant_str = merchant_match.group(1).strip()
        patterns["merchant_pattern"] = None if merchant_str.lower() == "none" else merchant_str

        currency_str = currency_match.group(1).strip()
        patterns["currency_pattern"] = None if currency_str.lower() == "none" else currency_str

        # Validate pattern combinations
        # Case 1: No transaction data - all patterns are None (valid)
        if patterns["amount_pattern"] is None and patterns["merchant_pattern"] is None:
            return patterns

        # Case 2+3: Partial or full patterns (valid)
        return patterns

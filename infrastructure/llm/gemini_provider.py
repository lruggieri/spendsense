"""Gemini LLM provider implementation for transaction pattern generation."""

import logging
import os
import re
from pathlib import Path
from typing import Dict, Optional

try:
    from google import genai
except ImportError:
    genai = None

from .base_llm_provider import BaseLLMProvider, LLMProviderError, PatternParsingError

logger = logging.getLogger(__name__)


class GeminiProvider(BaseLLMProvider):
    """Gemini LLM provider implementation."""

    @staticmethod
    def _build_prompt(email_text: str) -> str:
        """Build the prompt with the email text from external template file."""
        # Get the directory where this file is located
        current_dir = Path(__file__).parent
        prompt_file = current_dir / "pattern_generation_prompt.txt"

        try:
            prompt_template = prompt_file.read_text(encoding="utf-8")
            # Use replace instead of format() to avoid issues with {} in regex examples
            return prompt_template.replace("{email_text}", email_text)
        except FileNotFoundError:
            raise LLMProviderError(f"Prompt template file not found: {prompt_file}")
        except Exception as e:
            raise LLMProviderError(f"Error reading prompt template: {str(e)}")

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Gemini provider.

        Args:
            api_key: Gemini API key. If None, loads from environment variable.

        Raises:
            ValueError: If API key not found
            ImportError: If google-generativeai package not installed
        """
        if genai is None:
            raise ImportError(
                "google-genai package not installed. " "Install with: pip install google-genai"
            )

        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("Gemini API key not found. Set GEMINI_API_KEY environment variable.")

        self.client = genai.Client(
            api_key=self.api_key,
            http_options=genai.types.HttpOptions(timeout=60_000),  # 30 s (SDK unit: ms)
        )
        self.model_name = "gemini-flash-lite-latest"

    def generate_patterns(self, email_text: str) -> Dict[str, Optional[str]]:
        """
        Generate regex patterns using Gemini.

        Args:
            email_text: Email body text to analyze

        Returns:
            Dictionary with 'amount_pattern', 'merchant_pattern', 'currency_pattern'

        Raises:
            LLMProviderError: If Gemini API request fails
            PatternParsingError: If response cannot be parsed
        """
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

    def _parse_response(self, response_text: str) -> Dict[str, Optional[str]]:
        """
        Parse Gemini response into pattern dictionary.

        Expected format:
        AMOUNT_PATTERN: <regex>
        MERCHANT_PATTERN: <regex>
        CURRENCY_PATTERN: <regex or "None">

        Args:
            response_text: Raw response from Gemini

        Returns:
            Dictionary with parsed patterns

        Raises:
            PatternParsingError: If patterns cannot be extracted
        """
        patterns = {"amount_pattern": None, "merchant_pattern": None, "currency_pattern": None}

        # Extract patterns using regex
        amount_match = re.search(r"AMOUNT_PATTERN:\s*(.+)", response_text)
        merchant_match = re.search(r"MERCHANT_PATTERN:\s*(.+)", response_text)
        currency_match = re.search(r"CURRENCY_PATTERN:\s*(.+)", response_text)

        # Check that all required pattern lines are present in response (even if value is "None")
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
            # This is valid - email contains no transaction data
            return patterns

        # Case 2: Partial patterns - amount OR merchant present (valid)
        # Some emails may have amount but no merchant (e.g., generic debit card notifications)
        # Or merchant but no amount (e.g., subscription renewal notices)
        # Both cases are valid and should be supported

        # Case 3: At least one pattern present (valid)
        return patterns

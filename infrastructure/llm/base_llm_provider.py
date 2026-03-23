"""Abstract base class for LLM providers."""

import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Optional


class LLMProviderError(Exception):
    """Raised when LLM provider request fails."""


class PatternParsingError(Exception):
    """Raised when LLM response cannot be parsed."""


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def generate_patterns(self, email_text: str) -> Dict[str, Optional[str]]:
        """
        Generate regex patterns from email text.

        Args:
            email_text: The email body text to analyze

        Returns:
            Dictionary with keys: 'amount_pattern', 'merchant_pattern', 'currency_pattern'
            Values are regex strings or None for currency_pattern if no currency

        Raises:
            LLMProviderError: If the LLM request fails
            PatternParsingError: If the LLM response cannot be parsed
        """

    @staticmethod
    def _build_prompt(email_text: str) -> str:
        """Build the prompt with the email text from external template file."""
        prompt_file = Path(__file__).parent / "pattern_generation_prompt.txt"

        try:
            prompt_template = prompt_file.read_text(encoding="utf-8")
            return prompt_template.replace("{email_text}", email_text)
        except FileNotFoundError:
            raise LLMProviderError(f"Prompt template file not found: {prompt_file}")
        except Exception as e:
            raise LLMProviderError(f"Error reading prompt template: {str(e)}")

    @staticmethod
    def _parse_response(response_text: str) -> Dict[str, Optional[str]]:
        """
        Parse LLM response into pattern dictionary.

        Expected format:
        AMOUNT_PATTERN: <regex>
        MERCHANT_PATTERN: <regex>
        CURRENCY_PATTERN: <regex or "None">
        """
        patterns: Dict[str, Optional[str]] = {
            "amount_pattern": None,
            "merchant_pattern": None,
            "currency_pattern": None,
        }

        amount_match = re.search(r"AMOUNT_PATTERN:\s*(.+)", response_text)
        merchant_match = re.search(r"MERCHANT_PATTERN:\s*(.+)", response_text)
        currency_match = re.search(r"CURRENCY_PATTERN:\s*(.+)", response_text)

        if not amount_match or not merchant_match or not currency_match:
            missing = []
            if not amount_match:
                missing.append("AMOUNT_PATTERN")
            if not merchant_match:
                missing.append("MERCHANT_PATTERN")
            if not currency_match:
                missing.append("CURRENCY_PATTERN")
            raise PatternParsingError(
                f"Incomplete patterns: missing {', '.join(missing)}"
            )

        amount_str = amount_match.group(1).strip()
        patterns["amount_pattern"] = None if amount_str.lower() == "none" else amount_str

        merchant_str = merchant_match.group(1).strip()
        patterns["merchant_pattern"] = None if merchant_str.lower() == "none" else merchant_str

        currency_str = currency_match.group(1).strip()
        patterns["currency_pattern"] = None if currency_str.lower() == "none" else currency_str

        return patterns

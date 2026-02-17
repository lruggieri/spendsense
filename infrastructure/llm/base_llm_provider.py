"""Abstract base class for LLM providers."""

from abc import ABC, abstractmethod
from typing import Dict, Optional


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
        pass


class LLMProviderError(Exception):
    """Raised when LLM provider request fails."""
    pass


class PatternParsingError(Exception):
    """Raised when LLM response cannot be parsed."""
    pass

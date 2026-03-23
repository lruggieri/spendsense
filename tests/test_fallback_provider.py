"""Tests for FallbackLLMProvider."""

import unittest
from unittest.mock import MagicMock, patch

from infrastructure.llm.base_llm_provider import LLMProviderError, PatternParsingError
from infrastructure.llm.fallback_provider import FallbackLLMProvider


class TestFallbackLLMProvider(unittest.TestCase):
    """Tests for FallbackLLMProvider."""

    @patch("infrastructure.llm.fallback_provider.FallbackLLMProvider.__init__", return_value=None)
    def _make_provider(self, mock_init, gemini=None, openai=None):
        """Helper to create a FallbackLLMProvider with mocked sub-providers."""
        provider = FallbackLLMProvider()
        provider._gemini = gemini
        provider._openai = openai
        return provider

    def test_gemini_success(self):
        """Uses Gemini when it succeeds."""
        gemini = MagicMock()
        gemini.generate_patterns.return_value = {"amount_pattern": "test", "merchant_pattern": None, "currency_pattern": None}
        openai = MagicMock()

        provider = self._make_provider(gemini=gemini, openai=openai)
        result = provider.generate_patterns("email text")

        self.assertEqual(result["amount_pattern"], "test")
        gemini.generate_patterns.assert_called_once_with("email text")
        openai.generate_patterns.assert_not_called()

    def test_falls_back_to_openai_on_gemini_error(self):
        """Falls back to OpenAI when Gemini raises LLMProviderError."""
        gemini = MagicMock()
        gemini.generate_patterns.side_effect = LLMProviderError("timeout")
        openai = MagicMock()
        openai.generate_patterns.return_value = {"amount_pattern": "fallback", "merchant_pattern": None, "currency_pattern": None}

        provider = self._make_provider(gemini=gemini, openai=openai)
        result = provider.generate_patterns("email text")

        self.assertEqual(result["amount_pattern"], "fallback")
        gemini.generate_patterns.assert_called_once()
        openai.generate_patterns.assert_called_once_with("email text")

    def test_falls_back_on_any_exception(self):
        """Falls back to OpenAI on any Gemini exception, not just LLMProviderError."""
        gemini = MagicMock()
        gemini.generate_patterns.side_effect = Exception("unexpected")
        openai = MagicMock()
        openai.generate_patterns.return_value = {"amount_pattern": "ok", "merchant_pattern": None, "currency_pattern": None}

        provider = self._make_provider(gemini=gemini, openai=openai)
        result = provider.generate_patterns("email text")

        self.assertEqual(result["amount_pattern"], "ok")

    def test_raises_when_both_fail(self):
        """Raises LLMProviderError when both providers fail."""
        gemini = MagicMock()
        gemini.generate_patterns.side_effect = LLMProviderError("gemini down")
        openai = MagicMock()
        openai.generate_patterns.side_effect = LLMProviderError("openai down")

        provider = self._make_provider(gemini=gemini, openai=openai)

        with self.assertRaises(LLMProviderError) as ctx:
            provider.generate_patterns("email text")
        self.assertIn("All providers failed", str(ctx.exception))
        self.assertIn("gemini down", str(ctx.exception))
        self.assertIn("openai down", str(ctx.exception))

    def test_openai_only_when_gemini_unavailable(self):
        """Works with OpenAI only when Gemini is None."""
        openai = MagicMock()
        openai.generate_patterns.return_value = {"amount_pattern": "only", "merchant_pattern": None, "currency_pattern": None}

        provider = self._make_provider(gemini=None, openai=openai)
        result = provider.generate_patterns("email text")

        self.assertEqual(result["amount_pattern"], "only")

    def test_gemini_only_when_openai_unavailable(self):
        """Works with Gemini only when OpenAI is None."""
        gemini = MagicMock()
        gemini.generate_patterns.return_value = {"amount_pattern": "gem", "merchant_pattern": None, "currency_pattern": None}

        provider = self._make_provider(gemini=gemini, openai=None)
        result = provider.generate_patterns("email text")

        self.assertEqual(result["amount_pattern"], "gem")

    def test_raises_when_no_providers(self):
        """Raises when both providers are None."""
        provider = self._make_provider(gemini=None, openai=None)

        with self.assertRaises(LLMProviderError) as ctx:
            provider.generate_patterns("email text")
        self.assertIn("No LLM providers available", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

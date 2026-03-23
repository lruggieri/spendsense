"""Tests for LLM provider implementations."""

import os
import unittest
from unittest.mock import MagicMock, Mock, patch

from infrastructure.llm.base_llm_provider import (
    BaseLLMProvider,
    LLMProviderError,
    PatternParsingError,
)
from infrastructure.llm.gemini_provider import GeminiProvider


class TestGeminiProvider(unittest.TestCase):
    """Tests for GeminiProvider class."""

    def setUp(self):
        """Set up test fixtures."""
        # Store original env var
        self.original_api_key = os.environ.get("GEMINI_API_KEY")
        # Set test API key
        os.environ["GEMINI_API_KEY"] = "test-api-key-12345"

    def tearDown(self):
        """Clean up after tests."""
        # Restore original env var
        if self.original_api_key is not None:
            os.environ["GEMINI_API_KEY"] = self.original_api_key
        elif "GEMINI_API_KEY" in os.environ:
            del os.environ["GEMINI_API_KEY"]

    @patch("infrastructure.llm.gemini_provider.genai")
    def test_gemini_provider_initialization(self, mock_genai):
        """Test GeminiProvider initializes correctly with API key."""
        provider = GeminiProvider()

        # Should create Client with API key
        mock_genai.Client.assert_called_once_with(
            api_key="test-api-key-12345",
            http_options=mock_genai.types.HttpOptions(timeout=10_000),
        )

        # Should set model name
        self.assertEqual(provider.model_name, "gemini-2.5-flash")

    @patch("infrastructure.llm.gemini_provider.genai")
    def test_gemini_provider_missing_api_key(self, mock_genai):
        """Test GeminiProvider raises error when API key is missing."""
        # Remove API key from env
        del os.environ["GEMINI_API_KEY"]

        with self.assertRaises(ValueError) as context:
            GeminiProvider()

        self.assertIn("API key not found", str(context.exception))

    @patch("infrastructure.llm.gemini_provider.genai")
    def test_gemini_provider_with_explicit_api_key(self, mock_genai):
        """Test GeminiProvider accepts explicit API key parameter."""
        provider = GeminiProvider(api_key="explicit-key-123")

        mock_genai.Client.assert_called_once_with(
            api_key="explicit-key-123",
            http_options=mock_genai.types.HttpOptions(timeout=10_000),
        )

    @patch("infrastructure.llm.gemini_provider.genai")
    def test_generate_patterns_success(self, mock_genai):
        """Test generate_patterns with valid response."""
        # Mock client and response
        mock_client = Mock()
        mock_response = Mock()
        mock_response.text = r"""AMOUNT_PATTERN: 引落金額：\s*([0-9,]+)円
MERCHANT_PATTERN: 内容\s*[：:]\s*(.+)
CURRENCY_PATTERN: 引落金額：\s*[0-9,]+(円)"""

        mock_client.models.generate_content.return_value = mock_response
        mock_genai.Client.return_value = mock_client

        provider = GeminiProvider()
        email_text = "◆明細１\n引落金額：　1,232円\n内容　　：　水道料"

        result = provider.generate_patterns(email_text)

        # Verify patterns were extracted correctly
        self.assertEqual(result["amount_pattern"], r"引落金額：\s*([0-9,]+)円")
        self.assertEqual(result["merchant_pattern"], r"内容\s*[：:]\s*(.+)")
        self.assertEqual(result["currency_pattern"], r"引落金額：\s*[0-9,]+(円)")

        # Verify generate_content was called
        mock_client.models.generate_content.assert_called_once()
        call_kwargs = mock_client.models.generate_content.call_args[1]
        self.assertEqual(call_kwargs["model"], "gemini-2.5-flash")
        self.assertIn(email_text, call_kwargs["contents"])
        self.assertIn("AMOUNT_PATTERN", call_kwargs["contents"])

    @patch("infrastructure.llm.gemini_provider.genai")
    def test_generate_patterns_with_no_currency(self, mock_genai):
        """Test generate_patterns when currency pattern is 'None'."""
        mock_client = Mock()
        mock_response = Mock()
        mock_response.text = r"""AMOUNT_PATTERN: Transaction amount:\s*([0-9,]+)
MERCHANT_PATTERN: Merchant name:\s*(.+)
CURRENCY_PATTERN: None"""

        mock_client.models.generate_content.return_value = mock_response
        mock_genai.Client.return_value = mock_client

        provider = GeminiProvider()
        result = provider.generate_patterns("Transaction amount: 1500\nMerchant name: ABC Store")

        self.assertEqual(result["amount_pattern"], r"Transaction amount:\s*([0-9,]+)")
        self.assertEqual(result["merchant_pattern"], r"Merchant name:\s*(.+)")
        self.assertIsNone(result["currency_pattern"])

    @patch("infrastructure.llm.gemini_provider.genai")
    def test_generate_patterns_no_transaction_data(self, mock_genai):
        """Test generate_patterns when email has no transaction data."""
        mock_client = Mock()
        mock_response = Mock()
        mock_response.text = """AMOUNT_PATTERN: None
MERCHANT_PATTERN: None
CURRENCY_PATTERN: None"""

        mock_client.models.generate_content.return_value = mock_response
        mock_genai.Client.return_value = mock_client

        provider = GeminiProvider()
        result = provider.generate_patterns("This is a marketing email with no transactions.")

        # All patterns should be None when no transaction data is found
        self.assertIsNone(result["amount_pattern"])
        self.assertIsNone(result["merchant_pattern"])
        self.assertIsNone(result["currency_pattern"])

    @patch("infrastructure.llm.gemini_provider.genai")
    def test_generate_patterns_empty_response(self, mock_genai):
        """Test generate_patterns with empty response raises error."""
        mock_client = Mock()
        mock_response = Mock()
        mock_response.text = ""

        mock_client.models.generate_content.return_value = mock_response
        mock_genai.Client.return_value = mock_client

        provider = GeminiProvider()

        with self.assertRaises(LLMProviderError) as context:
            provider.generate_patterns("test email")

        self.assertIn("Empty response", str(context.exception))

    @patch("infrastructure.llm.gemini_provider.genai")
    def test_generate_patterns_missing_required_pattern(self, mock_genai):
        """Test generate_patterns raises error when required patterns are missing."""
        mock_client = Mock()
        mock_response = Mock()
        mock_response.text = """AMOUNT_PATTERN: ([0-9,]+)
CURRENCY_PATTERN: None"""  # Missing MERCHANT_PATTERN

        mock_client.models.generate_content.return_value = mock_response
        mock_genai.Client.return_value = mock_client

        provider = GeminiProvider()

        with self.assertRaises(PatternParsingError) as context:
            provider.generate_patterns("test email")

        self.assertIn("Incomplete patterns", str(context.exception))

    @patch("infrastructure.llm.gemini_provider.genai")
    def test_generate_patterns_partial_none(self, mock_genai):
        """Test generate_patterns handles partial patterns correctly."""
        # Test Case 1: Amount present but merchant None (e.g., generic debit card notification)
        mock_client = Mock()
        mock_response = Mock()
        mock_response.text = r"""AMOUNT_PATTERN: 金額\s*([0-9,]+)円
MERCHANT_PATTERN: None
CURRENCY_PATTERN: (円)"""

        mock_client.models.generate_content.return_value = mock_response
        mock_genai.Client.return_value = mock_client

        provider = GeminiProvider()
        result = provider.generate_patterns("test email")

        self.assertIsNotNone(result["amount_pattern"])
        self.assertIsNone(result["merchant_pattern"])
        self.assertIsNotNone(result["currency_pattern"])

    @patch("infrastructure.llm.gemini_provider.genai")
    def test_generate_patterns_partial_none_merchant_only(self, mock_genai):
        """Test generate_patterns handles merchant-only pattern correctly."""
        # Test Case 2: Merchant present but amount None (e.g., subscription renewal)
        mock_client = Mock()
        mock_response = Mock()
        mock_response.text = """AMOUNT_PATTERN: None
MERCHANT_PATTERN: subscription to (.+?) has
CURRENCY_PATTERN: None"""

        mock_client.models.generate_content.return_value = mock_response
        mock_genai.Client.return_value = mock_client

        provider = GeminiProvider()
        result = provider.generate_patterns("test email")

        self.assertIsNone(result["amount_pattern"])
        self.assertIsNotNone(result["merchant_pattern"])
        self.assertIsNone(result["currency_pattern"])

    @patch("infrastructure.llm.gemini_provider.genai")
    def test_generate_patterns_api_error(self, mock_genai):
        """Test generate_patterns handles API errors."""
        mock_client = Mock()
        mock_client.models.generate_content.side_effect = Exception("API connection failed")

        mock_genai.Client.return_value = mock_client

        provider = GeminiProvider()

        with self.assertRaises(LLMProviderError) as context:
            provider.generate_patterns("test email")

        self.assertIn("Failed to generate patterns", str(context.exception))

    @patch("infrastructure.llm.gemini_provider.genai")
    def test_parse_response_valid(self, mock_genai):
        """Test _parse_response with valid response text."""
        mock_genai.Client.return_value = Mock()

        provider = GeminiProvider()

        response_text = r"""AMOUNT_PATTERN: ([0-9,]+)
MERCHANT_PATTERN: Merchant:\s*(.+)
CURRENCY_PATTERN: ([A-Z]{3})"""

        result = provider._parse_response(response_text)

        self.assertEqual(result["amount_pattern"], "([0-9,]+)")
        self.assertEqual(result["merchant_pattern"], r"Merchant:\s*(.+)")
        self.assertEqual(result["currency_pattern"], "([A-Z]{3})")

    @patch("infrastructure.llm.gemini_provider.genai")
    def test_parse_response_with_extra_text(self, mock_genai):
        """Test _parse_response ignores extra text in response."""
        mock_genai.Client.return_value = Mock()

        provider = GeminiProvider()

        response_text = r"""Here are the patterns you requested:

AMOUNT_PATTERN: ([0-9,]+)
MERCHANT_PATTERN: Merchant:\s*(.+)
CURRENCY_PATTERN: (JPY|USD)

I hope this helps!"""

        result = provider._parse_response(response_text)

        self.assertEqual(result["amount_pattern"], "([0-9,]+)")
        self.assertEqual(result["merchant_pattern"], r"Merchant:\s*(.+)")
        self.assertEqual(result["currency_pattern"], "(JPY|USD)")

    @patch("infrastructure.llm.gemini_provider.genai", None)
    def test_missing_genai_package(self):
        """Test GeminiProvider raises ImportError when genai is not installed."""
        with self.assertRaises(ImportError) as context:
            GeminiProvider()

        self.assertIn("google-genai package not installed", str(context.exception))


class TestBaseLLMProvider(unittest.TestCase):
    """Tests for BaseLLMProvider abstract class."""

    def test_cannot_instantiate_abstract_class(self):
        """Test that BaseLLMProvider cannot be instantiated directly."""
        with self.assertRaises(TypeError):
            BaseLLMProvider()

    def test_subclass_must_implement_generate_patterns(self):
        """Test that subclasses must implement generate_patterns."""

        class IncompleteProvider(BaseLLMProvider):
            pass

        with self.assertRaises(TypeError):
            IncompleteProvider()

    def test_parse_response_incomplete_does_not_leak_response_text(self):
        """Test that PatternParsingError does not include response text (PII)."""
        with self.assertRaises(PatternParsingError) as context:
            BaseLLMProvider._parse_response("some email content with no patterns")

        error_msg = str(context.exception)
        self.assertIn("Incomplete patterns", error_msg)
        self.assertNotIn("some email content", error_msg)


if __name__ == "__main__":
    unittest.main()

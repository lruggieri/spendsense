"""Tests for OpenAI LLM provider implementation."""

import os
import unittest
from unittest.mock import Mock, patch

from infrastructure.llm.base_llm_provider import (
    LLMProviderError,
    PatternParsingError,
)
from infrastructure.llm.openai_provider import OpenAIProvider


class TestOpenAIProvider(unittest.TestCase):
    """Tests for OpenAIProvider class."""

    def setUp(self):
        """Set up test fixtures."""
        self.original_api_key = os.environ.get("OPENAI_API_KEY")
        os.environ["OPENAI_API_KEY"] = "test-api-key-12345"

    def tearDown(self):
        """Clean up after tests."""
        if self.original_api_key is not None:
            os.environ["OPENAI_API_KEY"] = self.original_api_key
        elif "OPENAI_API_KEY" in os.environ:
            del os.environ["OPENAI_API_KEY"]

    @patch("infrastructure.llm.openai_provider.OpenAI")
    def test_initialization(self, mock_openai_cls):
        """Test OpenAIProvider initializes correctly with API key."""
        provider = OpenAIProvider()

        mock_openai_cls.assert_called_once_with(
            api_key="test-api-key-12345", timeout=5.0
        )
        self.assertEqual(provider.model_name, "gpt-4o-mini")

    @patch("infrastructure.llm.openai_provider.OpenAI")
    def test_missing_api_key(self, mock_openai_cls):
        """Test raises error when API key is missing."""
        del os.environ["OPENAI_API_KEY"]

        with self.assertRaises(ValueError) as context:
            OpenAIProvider()

        self.assertIn("API key not found", str(context.exception))

    @patch("infrastructure.llm.openai_provider.OpenAI")
    def test_with_explicit_api_key(self, mock_openai_cls):
        """Test accepts explicit API key parameter."""
        OpenAIProvider(api_key="explicit-key-123")

        mock_openai_cls.assert_called_once_with(
            api_key="explicit-key-123", timeout=5.0
        )

    @patch("infrastructure.llm.openai_provider.OpenAI")
    def test_generate_patterns_success(self, mock_openai_cls):
        """Test generate_patterns with valid response."""
        mock_client = Mock()
        mock_choice = Mock()
        mock_choice.message.content = r"""AMOUNT_PATTERN: 引落金額：\s*([0-9,]+)円
MERCHANT_PATTERN: 内容\s*[：:]\s*(.+)
CURRENCY_PATTERN: 引落金額：\s*[0-9,]+(円)"""

        mock_response = Mock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_cls.return_value = mock_client

        provider = OpenAIProvider()
        email_text = "◆明細１\n引落金額：　1,232円\n内容　　：　水道料"

        result = provider.generate_patterns(email_text)

        self.assertEqual(result["amount_pattern"], r"引落金額：\s*([0-9,]+)円")
        self.assertEqual(result["merchant_pattern"], r"内容\s*[：:]\s*(.+)")
        self.assertEqual(result["currency_pattern"], r"引落金額：\s*[0-9,]+(円)")

        mock_client.chat.completions.create.assert_called_once()
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        self.assertEqual(call_kwargs["model"], "gpt-4o-mini")
        self.assertEqual(call_kwargs["temperature"], 0)

    @patch("infrastructure.llm.openai_provider.OpenAI")
    def test_generate_patterns_no_currency(self, mock_openai_cls):
        """Test generate_patterns when currency pattern is 'None'."""
        mock_client = Mock()
        mock_choice = Mock()
        mock_choice.message.content = r"""AMOUNT_PATTERN: Transaction amount:\s*([0-9,]+)
MERCHANT_PATTERN: Merchant name:\s*(.+)
CURRENCY_PATTERN: None"""

        mock_response = Mock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_cls.return_value = mock_client

        provider = OpenAIProvider()
        result = provider.generate_patterns("Transaction amount: 1500\nMerchant name: ABC Store")

        self.assertEqual(result["amount_pattern"], r"Transaction amount:\s*([0-9,]+)")
        self.assertEqual(result["merchant_pattern"], r"Merchant name:\s*(.+)")
        self.assertIsNone(result["currency_pattern"])

    @patch("infrastructure.llm.openai_provider.OpenAI")
    def test_generate_patterns_no_transaction_data(self, mock_openai_cls):
        """Test generate_patterns when email has no transaction data."""
        mock_client = Mock()
        mock_choice = Mock()
        mock_choice.message.content = """AMOUNT_PATTERN: None
MERCHANT_PATTERN: None
CURRENCY_PATTERN: None"""

        mock_response = Mock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_cls.return_value = mock_client

        provider = OpenAIProvider()
        result = provider.generate_patterns("This is a marketing email.")

        self.assertIsNone(result["amount_pattern"])
        self.assertIsNone(result["merchant_pattern"])
        self.assertIsNone(result["currency_pattern"])

    @patch("infrastructure.llm.openai_provider.OpenAI")
    def test_generate_patterns_empty_response(self, mock_openai_cls):
        """Test generate_patterns with empty response raises error."""
        mock_client = Mock()
        mock_choice = Mock()
        mock_choice.message.content = ""

        mock_response = Mock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_cls.return_value = mock_client

        provider = OpenAIProvider()

        with self.assertRaises(LLMProviderError) as context:
            provider.generate_patterns("test email")

        self.assertIn("Empty response", str(context.exception))

    @patch("infrastructure.llm.openai_provider.OpenAI")
    def test_generate_patterns_missing_required_pattern(self, mock_openai_cls):
        """Test raises error when required patterns are missing."""
        mock_client = Mock()
        mock_choice = Mock()
        mock_choice.message.content = """AMOUNT_PATTERN: ([0-9,]+)
CURRENCY_PATTERN: None"""

        mock_response = Mock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_cls.return_value = mock_client

        provider = OpenAIProvider()

        with self.assertRaises(PatternParsingError) as context:
            provider.generate_patterns("test email")

        self.assertIn("Incomplete patterns", str(context.exception))

    @patch("infrastructure.llm.openai_provider.OpenAI")
    def test_generate_patterns_partial_none(self, mock_openai_cls):
        """Test handles partial patterns correctly."""
        mock_client = Mock()
        mock_choice = Mock()
        mock_choice.message.content = r"""AMOUNT_PATTERN: 金額\s*([0-9,]+)円
MERCHANT_PATTERN: None
CURRENCY_PATTERN: (円)"""

        mock_response = Mock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_cls.return_value = mock_client

        provider = OpenAIProvider()
        result = provider.generate_patterns("test email")

        self.assertIsNotNone(result["amount_pattern"])
        self.assertIsNone(result["merchant_pattern"])
        self.assertIsNotNone(result["currency_pattern"])

    @patch("infrastructure.llm.openai_provider.OpenAI")
    def test_generate_patterns_api_error(self, mock_openai_cls):
        """Test handles API errors."""
        mock_client = Mock()
        mock_client.chat.completions.create.side_effect = Exception("API connection failed")
        mock_openai_cls.return_value = mock_client

        provider = OpenAIProvider()

        with self.assertRaises(LLMProviderError) as context:
            provider.generate_patterns("test email")

        self.assertIn("Failed to generate patterns", str(context.exception))

    @patch("infrastructure.llm.openai_provider.OpenAI", None)
    def test_missing_openai_package(self):
        """Test raises ImportError when openai is not installed."""
        with self.assertRaises(ImportError) as context:
            OpenAIProvider()

        self.assertIn("openai package not installed", str(context.exception))


if __name__ == "__main__":
    unittest.main()

"""Tests for Gmail utility functions."""

import base64
import unittest

from infrastructure.email.gmail_utils import (
    _transform_charset,
    decode_gmail_ui_message_id,
    get_body_from_message,
    normalize_gmail_message_id,
)


class TestGmailUtilsDecoding(unittest.TestCase):
    """Test Gmail UI message ID decoding."""

    def test_normalize_accepts_api_format(self):
        """Test that API format IDs pass through unchanged."""
        api_id = "18c2a3b4e5f6g7h8"
        result = normalize_gmail_message_id(api_id)
        # Should return as-is since it contains non-consonant chars
        self.assertEqual(result, api_id)

    def test_normalize_handles_whitespace(self):
        """Test that whitespace is stripped."""
        api_id = "  18c2a3b4e5f6g7h8  "
        result = normalize_gmail_message_id(api_id)
        self.assertEqual(result, "18c2a3b4e5f6g7h8")

    def test_decode_ui_message_id(self):
        """Test decoding a UI format message ID."""
        # This is a realistic UI message ID format
        ui_id = "FMfcgzQfBGfsVHzgNPZvccFHwCmhpvCQ"
        result = decode_gmail_ui_message_id(ui_id)

        # The result should be a decoded hexadecimal string (not None)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

        # Result should be a valid hexadecimal string
        try:
            int(result, 16)
            is_hex = True
        except ValueError:
            is_hex = False
        self.assertTrue(is_hex, f"Result '{result}' is not a valid hexadecimal string")

    def test_decode_invalid_input(self):
        """Test that invalid input returns None."""
        invalid_id = "not-valid-123!@#"
        result = decode_gmail_ui_message_id(invalid_id)
        # Should handle gracefully and return None
        self.assertIsNone(result)

    def test_transform_charset_basic(self):
        """Test the character set transformation function."""
        # Simple transformation test
        charset_in = "ABC"
        charset_out = "XYZ"
        token = "A"

        result = _transform_charset(token, charset_in, charset_out)

        # Should produce some output
        self.assertIsNotNone(result)
        self.assertIsInstance(result, str)

    def test_normalize_with_consonant_only_string(self):
        """Test normalization with a string that looks like UI format."""
        # A string with only consonants should trigger decoding attempt
        ui_id = "BcDfGhJkLm"
        result = normalize_gmail_message_id(ui_id)

        # Should attempt to decode or return the original
        self.assertIsNotNone(result)
        self.assertIsInstance(result, str)


class TestGmailUtilsEdgeCases(unittest.TestCase):
    """Test edge cases and error handling."""

    def test_empty_string(self):
        """Test handling of empty string."""
        result = normalize_gmail_message_id("")
        self.assertEqual(result, "")

    def test_decode_empty_string(self):
        """Test decoding empty string."""
        result = decode_gmail_ui_message_id("")
        # Should handle gracefully - empty string is acceptable
        self.assertIn(result, [None, ""])

    def test_mixed_format_prefers_api(self):
        """Test that mixed format strings are treated as API format."""
        mixed_id = "18c2BcDf"
        result = normalize_gmail_message_id(mixed_id)
        # Contains non-consonants, should be treated as API format
        self.assertEqual(result, mixed_id)


class TestGetBodyFromMessage(unittest.TestCase):
    """Test HTML entity decoding in email body extraction."""

    def _create_test_message(self, body_text: str, mime_type: str = "text/html") -> dict:
        """Helper to create a test Gmail message with given body text."""
        encoded_body = base64.urlsafe_b64encode(body_text.encode("utf-8")).decode("utf-8")
        return {"payload": {"mimeType": mime_type, "body": {"data": encoded_body}}}

    def test_decode_named_html_entities(self):
        """Test that named HTML entities are decoded correctly."""
        html_body = "<html><body>Test &amp; Test &lt;tag&gt; &quot;quoted&quot;</body></html>"
        message = self._create_test_message(html_body)

        result = get_body_from_message(message)

        # Should decode all named entities
        self.assertIn("&", result)
        self.assertIn("<tag>", result)
        self.assertIn('"quoted"', result)
        # Should not contain the entity codes
        self.assertNotIn("&amp;", result)
        self.assertNotIn("&lt;", result)
        self.assertNotIn("&gt;", result)
        self.assertNotIn("&quot;", result)

    def test_decode_numeric_html_entities(self):
        """Test that numeric HTML entities are decoded correctly."""
        # &#34; is the numeric entity for double quote
        # &#38; is the numeric entity for ampersand
        html_body = "<html><body>Test &#34;quoted&#34; &#38; value</body></html>"
        message = self._create_test_message(html_body)

        result = get_body_from_message(message)

        # Should decode numeric entities
        self.assertIn('"quoted"', result)
        self.assertIn("& value", result)
        # Should not contain the entity codes
        self.assertNotIn("&#34;", result)
        self.assertNotIn("&#38;", result)

    def test_decode_hex_html_entities(self):
        """Test that hexadecimal HTML entities are decoded correctly."""
        # &#x22; is the hex entity for double quote
        # &#x26; is the hex entity for ampersand
        html_body = "<html><body>Test &#x22;quoted&#x22; &#x26; value</body></html>"
        message = self._create_test_message(html_body)

        result = get_body_from_message(message)

        # Should decode hex entities
        self.assertIn('"quoted"', result)
        self.assertIn("& value", result)
        # Should not contain the entity codes
        self.assertNotIn("&#x22;", result)
        self.assertNotIn("&#x26;", result)

    def test_issue_44_arabic_restaurant_example(self):
        """Test the specific example from issue #44."""
        # This simulates the Gmail message body that contains &amp; instead of &
        html_body = "<html><body>Arabic Restaurant&amp;Cafe Abu Essam</body></html>"
        message = self._create_test_message(html_body)

        result = get_body_from_message(message)

        # Should decode to a single ampersand
        self.assertEqual(result, "Arabic Restaurant&Cafe Abu Essam")
        # Should NOT contain the HTML entity
        self.assertNotIn("&amp;", result)

    def test_no_double_escaping_plain_text(self):
        """Test that plain text with special chars is not double-escaped."""
        # If plain text already contains & it should remain as &
        plain_text = "Restaurant & Cafe"
        message = self._create_test_message(plain_text, mime_type="text/plain")

        result = get_body_from_message(message)

        # Should preserve the single ampersand
        self.assertEqual(result, "Restaurant & Cafe")

    def test_mixed_entities_and_special_chars(self):
        """Test mixed HTML entities and real special characters."""
        html_body = "<html><body>Price: &#36;50 &amp; &#8364;45 (mixed)</body></html>"
        message = self._create_test_message(html_body)

        result = get_body_from_message(message)

        # Should decode all entities correctly
        self.assertIn("$50", result)
        self.assertIn("€45", result)
        self.assertIn("&", result)
        # Should not contain entity codes
        self.assertNotIn("&#36;", result)
        self.assertNotIn("&amp;", result)
        self.assertNotIn("&#8364;", result)

    def test_multipart_message_with_html_entities(self):
        """Test multipart message with HTML entities in text/plain part."""
        # Create a multipart message with HTML entities in plain text
        # Some senders encode entities even in text/plain parts
        plain_text = "Restaurant&amp;Cafe"
        encoded_body = base64.urlsafe_b64encode(plain_text.encode("utf-8")).decode("utf-8")

        message = {
            "payload": {
                "mimeType": "multipart/alternative",
                "parts": [{"mimeType": "text/plain", "body": {"data": encoded_body}}],
            }
        }

        result = get_body_from_message(message)

        # HTML entities should be decoded even in text/plain
        self.assertEqual(result, "Restaurant&Cafe")
        self.assertNotIn("&amp;", result)


if __name__ == "__main__":
    unittest.main()

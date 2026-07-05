"""Tests for shared auth utility functions."""

from presentation.web.auth_utils import safe_next_url


class TestSafeNextUrl:
    def test_none_returns_none(self):
        assert safe_next_url(None) is None

    def test_empty_string_returns_none(self):
        assert safe_next_url("") is None

    def test_relative_path_is_returned(self):
        assert safe_next_url("/mcp-consent?txn=abc123") == "/mcp-consent?txn=abc123"

    def test_absolute_url_rejected(self):
        assert safe_next_url("https://evil.com/phish") is None

    def test_protocol_relative_url_rejected(self):
        assert safe_next_url("//evil.com/phish") is None

    def test_backslash_url_rejected(self):
        assert safe_next_url("/\\evil.com") is None

    def test_path_without_leading_slash_rejected(self):
        assert safe_next_url("evil.com") is None

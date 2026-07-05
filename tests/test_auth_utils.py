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

    def test_embedded_tab_rejected(self):
        """Browsers strip ASCII tab/newline/CR anywhere in a URL before
        parsing (WHATWG URL spec), so "/\t/evil.com" would navigate as
        "//evil.com" despite passing the leading-slash checks literally."""
        assert safe_next_url("/\t/evil.com") is None

    def test_embedded_newline_rejected(self):
        assert safe_next_url("/\n/evil.com") is None

    def test_embedded_carriage_return_rejected(self):
        assert safe_next_url("/\r/evil.com") is None

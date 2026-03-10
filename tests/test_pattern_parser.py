"""Tests for pattern_parser module — regex execution and ReDoS protection."""

import unittest

from infrastructure.email.fetchers.pattern_parser import (
    flatten_regex_results,
    parse_transactions_with_patterns,
)


class TestFlattenRegexResults(unittest.TestCase):
    """Tests for flatten_regex_results helper."""

    def test_empty_list(self):
        self.assertEqual(flatten_regex_results([]), [])

    def test_simple_strings(self):
        self.assertEqual(flatten_regex_results(["100", "200"]), ["100", "200"])

    def test_tuples_from_alternation(self):
        # re.findall with (A|B) returns tuples like ('', '880') or ('3704', '')
        results = [("", "880"), ("3704", "")]
        self.assertEqual(flatten_regex_results(results), ["880", "3704"])

    def test_tuples_all_empty_skipped(self):
        results = [("", ""), ("val", "")]
        self.assertEqual(flatten_regex_results(results), ["val"])


class TestParseTransactionsWithPatterns(unittest.TestCase):
    """Tests for parse_transactions_with_patterns."""

    def test_none_patterns_returns_empty(self):
        result = parse_transactions_with_patterns("email text", None, None, None)
        self.assertEqual(result, [])

    def test_basic_extraction(self):
        email = "Amount: 1,234\nMerchant: Coffee Shop"
        result = parse_transactions_with_patterns(
            email,
            amount_pattern=r"Amount:\s*([0-9,]+)",
            merchant_pattern=r"Merchant:\s*(.+)",
            currency_pattern=None,
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["amount"], "1234")
        self.assertEqual(result[0]["merchant"], "Coffee Shop")
        self.assertIsNone(result[0]["currency"])

    def test_multiple_transactions(self):
        email = "Amount: 100\nMerchant: A\nAmount: 200\nMerchant: B"
        result = parse_transactions_with_patterns(
            email,
            amount_pattern=r"Amount:\s*(\d+)",
            merchant_pattern=r"Merchant:\s*(.+)",
            currency_pattern=None,
        )
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["amount"], "100")
        self.assertEqual(result[1]["amount"], "200")

    def test_negate_amount(self):
        email = "Amount: 500"
        result = parse_transactions_with_patterns(
            email,
            amount_pattern=r"Amount:\s*(\d+)",
            merchant_pattern=None,
            currency_pattern=None,
            negate_amount=True,
        )
        self.assertEqual(result[0]["amount"], "-500")

    def test_global_currency(self):
        email = "Currency: USD\nAmount: 100\nMerchant: A\nAmount: 200\nMerchant: B"
        result = parse_transactions_with_patterns(
            email,
            amount_pattern=r"Amount:\s*(\d+)",
            merchant_pattern=r"Merchant:\s*(.+)",
            currency_pattern=r"Currency:\s*([A-Z]{3})",
        )
        # Single currency match → applied to all transactions
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["currency"], "USD")
        self.assertEqual(result[1]["currency"], "USD")


class TestReDoSProtection(unittest.TestCase):
    """Tests that catastrophic backtracking patterns are terminated."""

    def test_redos_pattern_raises_timeout(self):
        """A classic ReDoS pattern must not hang the server."""
        redos_pattern = r"(a|a)+b"
        evil_input = "a" * 50  # no trailing 'b' → exponential backtracking

        with self.assertRaises(TimeoutError):
            parse_transactions_with_patterns(
                evil_input,
                amount_pattern=redos_pattern,
                merchant_pattern=None,
                currency_pattern=None,
            )

    def test_normal_pattern_does_not_timeout(self):
        """Legitimate patterns should complete without issue."""
        email = "You spent 1,234 JPY at Store."
        result = parse_transactions_with_patterns(
            email,
            amount_pattern=r"spent\s+([0-9,]+)",
            merchant_pattern=r"at\s+(.+?)\.",
            currency_pattern=r"([A-Z]{3})",
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["amount"], "1234")


if __name__ == "__main__":
    unittest.main()

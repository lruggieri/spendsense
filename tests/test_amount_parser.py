"""Tests for the intelligent amount parser."""

import sys
from pathlib import Path

# Add parent directory to path to enable imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from domain.services.amount_parser import _detect_locale, parse_amount


def test_european_format_with_comma_decimal():
    """Test parsing European format where comma is decimal separator."""
    # Simple cases with comma as decimal
    assert parse_amount("5,99") == "5.99", "Failed: 5,99 should parse to 5.99"
    assert parse_amount("12,50") == "12.5", "Failed: 12,50 should parse to 12.5"
    assert parse_amount("0,75") == "0.75", "Failed: 0,75 should parse to 0.75"


def test_us_format_with_dot_decimal():
    """Test parsing US format where dot is decimal separator."""
    # Simple cases with dot as decimal
    assert parse_amount("5.99") == "5.99", "Failed: 5.99 should parse to 5.99"
    assert parse_amount("12.50") == "12.5", "Failed: 12.50 should parse to 12.5"
    assert parse_amount("0.75") == "0.75", "Failed: 0.75 should parse to 0.75"


def test_european_format_with_thousands():
    """Test parsing European format with dot as thousands separator."""
    assert parse_amount("1.234,56") == "1234.56", "Failed: 1.234,56 should parse to 1234.56"
    assert parse_amount("10.000,00") == "10000", "Failed: 10.000,00 should parse to 10000"
    assert parse_amount("123.456,78") == "123456.78", "Failed: 123.456,78 should parse to 123456.78"


def test_us_format_with_thousands():
    """Test parsing US format with comma as thousands separator."""
    assert parse_amount("1,234.56") == "1234.56", "Failed: 1,234.56 should parse to 1234.56"
    assert parse_amount("10,000.00") == "10000", "Failed: 10,000.00 should parse to 10000"
    assert parse_amount("123,456.78") == "123456.78", "Failed: 123,456.78 should parse to 123456.78"


def test_japanese_yen_format():
    """Test parsing Japanese Yen amounts (no decimal places, comma as thousands)."""
    assert parse_amount("1,232") == "1232", "Failed: 1,232 should parse to 1232"
    assert parse_amount("866") == "866", "Failed: 866 should parse to 866"
    assert parse_amount("45,678") == "45678", "Failed: 45,678 should parse to 45678"
    assert parse_amount("184,000") == "184000", "Failed: 184,000 should parse to 184000"


def test_no_separators():
    """Test parsing amounts with no separators."""
    assert parse_amount("1234") == "1234", "Failed: 1234 should parse to 1234"
    assert parse_amount("500") == "500", "Failed: 500 should parse to 500"
    assert parse_amount("99") == "99", "Failed: 99 should parse to 99"


def test_whitespace_handling():
    """Test that whitespace is properly handled."""
    assert parse_amount("  5,99  ") == "5.99", "Failed: whitespace should be stripped"
    assert parse_amount("1 234,56") == "1234.56", "Failed: spaces should be removed"


def test_currency_symbols_removed():
    """Test that currency symbols are stripped."""
    assert parse_amount("$5.99") == "5.99", "Failed: $ symbol should be removed"
    assert parse_amount("€5,99") == "5.99", "Failed: € symbol should be removed"
    assert parse_amount("¥1,234") == "1234", "Failed: ¥ symbol should be removed"


def test_trailing_zeros_removed():
    """Test that trailing zeros after decimal point are removed."""
    assert parse_amount("10.00") == "10", "Failed: 10.00 should parse to 10"
    assert parse_amount("5.50") == "5.5", "Failed: 5.50 should parse to 5.5"
    # Note: 123.100 is ambiguous - could be 123,100 (US thousands) or 123.1 (decimal)
    # Our heuristic treats it as US format with comma thousands separator: 123100
    assert parse_amount("123,100") == "123100", "Failed: 123,100 should parse to 123100"


def test_locale_detection():
    """Test the locale detection heuristic."""
    # European format detection
    assert _detect_locale("5,99") == "de_DE", "Failed: 5,99 should detect as European"
    assert _detect_locale("1.234,56") == "de_DE", "Failed: 1.234,56 should detect as European"

    # US format detection
    assert _detect_locale("5.99") == "en_US", "Failed: 5.99 should detect as US"
    assert _detect_locale("1,234.56") == "en_US", "Failed: 1,234.56 should detect as US"

    # Japanese Yen format (ambiguous, defaults to US)
    assert _detect_locale("1,234") == "en_US", "Failed: 1,234 should default to US format"


def test_edge_cases():
    """Test edge cases and error handling."""
    # Empty or None input
    assert parse_amount("") is None, "Failed: empty string should return None"
    assert parse_amount(None) is None, "Failed: None should return None"

    # Invalid input
    assert parse_amount("abc") is None, "Failed: non-numeric string should return None"
    assert parse_amount("...") is None, "Failed: only separators should return None"


def test_real_world_examples():
    """Test real-world examples from various sources."""
    # SMBC Japanese bank
    assert parse_amount("1,232") == "1232", "Failed: SMBC format"

    # European credit card statement
    assert parse_amount("5,99") == "5.99", "Failed: European CC format"

    # US online shopping
    assert parse_amount("123.45") == "123.45", "Failed: US shopping format"

    # Wise international transfer
    assert parse_amount("1,234.56") == "1234.56", "Failed: Wise US format"
    assert parse_amount("1.234,56") == "1234.56", "Failed: Wise European format"


if __name__ == "__main__":
    print("Running amount parser tests...")

    test_european_format_with_comma_decimal()
    print("✓ European format with comma decimal tests passed")

    test_us_format_with_dot_decimal()
    print("✓ US format with dot decimal tests passed")

    test_european_format_with_thousands()
    print("✓ European format with thousands separator tests passed")

    test_us_format_with_thousands()
    print("✓ US format with thousands separator tests passed")

    test_japanese_yen_format()
    print("✓ Japanese Yen format tests passed")

    test_no_separators()
    print("✓ No separators tests passed")

    test_whitespace_handling()
    print("✓ Whitespace handling tests passed")

    test_currency_symbols_removed()
    print("✓ Currency symbols removal tests passed")

    test_trailing_zeros_removed()
    print("✓ Trailing zeros removal tests passed")

    test_locale_detection()
    print("✓ Locale detection tests passed")

    test_edge_cases()
    print("✓ Edge cases tests passed")

    test_real_world_examples()
    print("✓ Real-world examples tests passed")

    print("\n✅ All amount parser tests passed!")

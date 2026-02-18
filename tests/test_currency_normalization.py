"""
Tests for currency normalization functionality.

This module tests the normalize_currency_code() function which converts
various currency inputs (symbols, names, codes) to ISO 4217 codes.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import normalize_currency_code


def test_iso_codes():
    """Test that ISO codes are returned unchanged (case-insensitive)."""
    assert normalize_currency_code("JPY") == "JPY"
    assert normalize_currency_code("jpy") == "JPY"
    assert normalize_currency_code("USD") == "USD"
    assert normalize_currency_code("usd") == "USD"
    assert normalize_currency_code("EUR") == "EUR"
    assert normalize_currency_code("eur") == "EUR"
    assert normalize_currency_code("GBP") == "GBP"
    assert normalize_currency_code("KRW") == "KRW"
    print("✓ ISO code normalization tests passed")


def test_currency_symbols():
    """Test currency symbol to code mapping."""
    assert normalize_currency_code("¥") == "JPY"
    assert normalize_currency_code("$") == "USD"
    assert normalize_currency_code("€") == "EUR"
    assert normalize_currency_code("£") == "GBP"
    assert normalize_currency_code("₩") == "KRW"
    assert normalize_currency_code("₹") == "INR"
    assert normalize_currency_code("₺") == "TRY"
    assert normalize_currency_code("₱") == "PHP"
    print("✓ Currency symbol normalization tests passed")


def test_currency_kanji():
    """Test Japanese/Chinese currency kanji to code mapping."""
    assert normalize_currency_code("円") == "JPY"
    assert normalize_currency_code("元") == "CNY"
    print("✓ Currency kanji normalization tests passed")


def test_currency_names_full():
    """Test full currency names to code mapping."""
    assert normalize_currency_code("Japanese Yen") == "JPY"
    assert normalize_currency_code("japanese yen") == "JPY"
    assert normalize_currency_code("US Dollar") == "USD"
    assert normalize_currency_code("us dollar") == "USD"
    assert normalize_currency_code("Euro") == "EUR"
    assert normalize_currency_code("euro") == "EUR"
    assert normalize_currency_code("British Pound") == "GBP"
    assert normalize_currency_code("South Korean Won") == "KRW"
    print("✓ Full currency name normalization tests passed")


def test_currency_names_short():
    """Test short currency names (last word) to code mapping."""
    assert normalize_currency_code("Yen") == "JPY"
    assert normalize_currency_code("yen") == "JPY"
    assert normalize_currency_code("Dollar") == "USD"
    assert normalize_currency_code("dollar") == "USD"
    assert normalize_currency_code("Pound") == "GBP"
    assert normalize_currency_code("Won") == "KRW"
    print("✓ Short currency name normalization tests passed")


def test_whitespace_handling():
    """Test that whitespace is properly stripped."""
    assert normalize_currency_code(" JPY ") == "JPY"
    assert normalize_currency_code("  Yen  ") == "JPY"
    assert normalize_currency_code(" 円 ") == "JPY"
    assert normalize_currency_code("  $  ") == "USD"
    print("✓ Whitespace handling tests passed")


def test_unrecognized_inputs():
    """Test that unrecognized inputs are returned unchanged."""
    # These should return the original input with a warning
    result = normalize_currency_code("UNKNOWN")
    assert result == "UNKNOWN"

    result = normalize_currency_code("xyz")
    assert result == "xyz"

    print("✓ Unrecognized input handling tests passed")


def test_empty_inputs():
    """Test edge cases with empty inputs."""
    assert normalize_currency_code("") == ""
    assert normalize_currency_code(None) == None
    print("✓ Empty input handling tests passed")


def test_validation_script_examples():
    """Test the specific cases from the validation script bug."""
    # Bug case 1: "円" should map to "JPY"
    assert normalize_currency_code("円") == "JPY"

    # Bug case 2: "Yen" should map to "JPY"
    assert normalize_currency_code("Yen") == "JPY"

    # Additional verification
    assert normalize_currency_code("yen") == "JPY"
    assert normalize_currency_code("YEN") == "JPY"

    print("✓ Validation script bug case tests passed")


def run_all_tests():
    """Run all currency normalization tests."""
    print("=" * 80)
    print("Currency Normalization Tests")
    print("=" * 80)

    test_iso_codes()
    test_currency_symbols()
    test_currency_kanji()
    test_currency_names_full()
    test_currency_names_short()
    test_whitespace_handling()
    test_unrecognized_inputs()
    test_empty_inputs()
    test_validation_script_examples()

    print("=" * 80)
    print("All currency normalization tests passed! ✓")
    print("=" * 80)


if __name__ == "__main__":
    run_all_tests()

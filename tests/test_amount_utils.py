"""
Tests for logic/amount_utils.py

Tests conversion between major and minor currency units for various currencies.
"""

from decimal import Decimal

import pytest

from domain.services.amount_utils import (
    format_amount,
    parse_and_convert,
    to_major_units,
    to_major_units_float,
    to_minor_units,
    validate_amount,
)


class TestToMinorUnits:
    """Tests for converting major units (string) to minor units (int)."""

    def test_usd_basic(self):
        """Test basic USD conversion."""
        assert to_minor_units("5.99", "USD") == 599
        assert to_minor_units("1.00", "USD") == 100
        assert to_minor_units("0.01", "USD") == 1

    def test_jpy_basic(self):
        """Test JPY (0 decimals)."""
        assert to_minor_units("1234", "JPY") == 1234
        assert to_minor_units("100", "JPY") == 100
        assert to_minor_units("1", "JPY") == 1

    def test_eur_basic(self):
        """Test EUR conversion."""
        assert to_minor_units("10.50", "EUR") == 1050
        assert to_minor_units("99.99", "EUR") == 9999

    def test_rounding_half_up(self):
        """Test that rounding works correctly (ROUND_HALF_UP)."""
        # 5.995 rounds up to 6.00
        assert to_minor_units("5.995", "USD") == 600
        # 5.994 rounds down to 5.99
        assert to_minor_units("5.994", "USD") == 599
        # 5.5 rounds up to 6
        assert to_minor_units("5.5", "USD") == 550

    def test_zero_amount(self):
        """Test zero amounts."""
        assert to_minor_units("0", "USD") == 0
        assert to_minor_units("0.00", "USD") == 0
        assert to_minor_units("0", "JPY") == 0

    def test_large_amounts(self):
        """Test large amounts."""
        assert to_minor_units("999999.99", "USD") == 99999999
        assert to_minor_units("9999999", "JPY") == 9999999

    def test_integer_string(self):
        """Test integer strings without decimals."""
        assert to_minor_units("5", "USD") == 500
        assert to_minor_units("100", "USD") == 10000

    def test_negative_amounts(self):
        """Test negative amounts (for refunds)."""
        assert to_minor_units("-5.99", "USD") == -599
        assert to_minor_units("-100", "JPY") == -100

    def test_krw_zero_decimals(self):
        """Test KRW (another 0 decimal currency)."""
        assert to_minor_units("5000", "KRW") == 5000

    def test_isk_zero_decimals(self):
        """Test ISK (Icelandic Króna, 0 decimals)."""
        assert to_minor_units("1500", "ISK") == 1500

    def test_invalid_string(self):
        """Test that invalid strings raise ValueError."""
        with pytest.raises(ValueError, match="Invalid amount format"):
            to_minor_units("abc", "USD")
        with pytest.raises(ValueError, match="Invalid amount format"):
            to_minor_units("", "USD")

    def test_unknown_currency_defaults_to_2_decimals(self):
        """Test that unknown currencies default to 2 decimal places."""
        # Should log warning but work with 2 decimals
        assert to_minor_units("5.99", "XYZ") == 599


class TestToMajorUnits:
    """Tests for converting minor units (int) to major units (Decimal)."""

    def test_usd_basic(self):
        """Test basic USD conversion."""
        assert to_major_units(599, "USD") == Decimal("5.99")
        assert to_major_units(100, "USD") == Decimal("1.00")
        assert to_major_units(1, "USD") == Decimal("0.01")

    def test_jpy_basic(self):
        """Test JPY (0 decimals)."""
        assert to_major_units(1234, "JPY") == Decimal("1234")
        assert to_major_units(100, "JPY") == Decimal("100")

    def test_zero_amount(self):
        """Test zero amounts."""
        assert to_major_units(0, "USD") == Decimal("0")
        assert to_major_units(0, "JPY") == Decimal("0")

    def test_large_amounts(self):
        """Test large amounts."""
        assert to_major_units(99999999, "USD") == Decimal("999999.99")
        assert to_major_units(9999999, "JPY") == Decimal("9999999")

    def test_negative_amounts(self):
        """Test negative amounts."""
        assert to_major_units(-599, "USD") == Decimal("-5.99")
        assert to_major_units(-100, "JPY") == Decimal("-100")


class TestToMajorUnitsFloat:
    """Tests for converting minor units to float (backward compatibility)."""

    def test_usd_basic(self):
        """Test USD float conversion."""
        assert to_major_units_float(599, "USD") == 5.99
        assert to_major_units_float(100, "USD") == 1.00

    def test_jpy_basic(self):
        """Test JPY float conversion."""
        assert to_major_units_float(1234, "JPY") == 1234.0

    def test_returns_float_type(self):
        """Verify return type is float."""
        result = to_major_units_float(599, "USD")
        assert isinstance(result, float)


class TestFormatAmount:
    """Tests for formatting amounts for display."""

    def test_usd_with_decimals(self):
        """Test USD formatting with decimals."""
        assert format_amount(599, "USD") == "5.99"
        assert format_amount(100, "USD") == "1.00"
        assert format_amount(1, "USD") == "0.01"

    def test_jpy_no_decimals(self):
        """Test JPY formatting (no decimals)."""
        assert format_amount(1234, "JPY") == "1234"
        assert format_amount(100, "JPY") == "100"

    def test_usd_without_decimals_flag(self):
        """Test USD formatting without decimals."""
        assert format_amount(599, "USD", include_decimals=False) == "5"
        assert format_amount(1000, "USD", include_decimals=False) == "10"

    def test_zero_amount(self):
        """Test zero formatting."""
        assert format_amount(0, "USD") == "0.00"
        assert format_amount(0, "JPY") == "0"

    def test_large_amounts(self):
        """Test large amount formatting."""
        assert format_amount(99999999, "USD") == "999999.99"
        assert format_amount(9999999, "JPY") == "9999999"

    def test_negative_amounts(self):
        """Test negative amount formatting."""
        assert format_amount(-599, "USD") == "-5.99"
        assert format_amount(-100, "JPY") == "-100"


class TestValidateAmount:
    """Tests for amount validation."""

    def test_valid_amounts(self):
        """Test that normal amounts are valid."""
        assert validate_amount(599, "USD") == True
        assert validate_amount(1234, "JPY") == True
        assert validate_amount(0, "USD") == True
        assert validate_amount(-100, "USD") == True

    def test_max_sqlite_integer(self):
        """Test maximum SQLite integer."""
        max_val = 2**63 - 1
        assert validate_amount(max_val, "USD") == True
        assert validate_amount(max_val + 1, "USD") == False

    def test_min_sqlite_integer(self):
        """Test minimum SQLite integer."""
        min_val = -(2**63)
        assert validate_amount(min_val, "USD") == True
        assert validate_amount(min_val - 1, "USD") == False


class TestParseAndConvert:
    """Tests for parse_and_convert convenience method."""

    def test_string_input(self):
        """Test string input."""
        assert parse_and_convert("5.99", "USD") == 599

    def test_float_input(self):
        """Test float input."""
        assert parse_and_convert(5.99, "USD") == 599

    def test_int_input(self):
        """Test integer input."""
        assert parse_and_convert(5, "USD") == 500

    def test_jpy_integer(self):
        """Test JPY integer."""
        assert parse_and_convert(1234, "JPY") == 1234


class TestRoundTrip:
    """Tests for round-trip conversions (major → minor → major)."""

    def test_usd_round_trip(self):
        """Test USD round trip."""
        original = "5.99"
        minor = to_minor_units(original, "USD")
        major = format_amount(minor, "USD")
        assert major == original

    def test_jpy_round_trip(self):
        """Test JPY round trip."""
        original = "1234"
        minor = to_minor_units(original, "JPY")
        major = format_amount(minor, "JPY")
        assert major == original

    def test_eur_round_trip(self):
        """Test EUR round trip."""
        original = "10.50"
        minor = to_minor_units(original, "EUR")
        major = format_amount(minor, "EUR")
        assert major == original

    def test_edge_case_one_cent(self):
        """Test one cent round trip."""
        original = "0.01"
        minor = to_minor_units(original, "USD")
        major = format_amount(minor, "USD")
        assert major == original
        assert minor == 1


class TestMultipleCurrencies:
    """Tests for various currency types."""

    def test_all_2_decimal_currencies(self):
        """Test sample of 2-decimal currencies."""
        currencies = ["USD", "EUR", "GBP", "CAD", "AUD", "CHF", "CNY"]
        for currency in currencies:
            assert to_minor_units("5.99", currency) == 599
            assert format_amount(599, currency) == "5.99"

    def test_all_0_decimal_currencies(self):
        """Test all 0-decimal currencies."""
        currencies = ["JPY", "KRW", "ISK"]
        for currency in currencies:
            assert to_minor_units("1234", currency) == 1234
            assert format_amount(1234, currency) == "1234"


class TestPrecisionPreservation:
    """Tests that verify no precision is lost."""

    def test_no_truncation_usd(self):
        """Verify decimals are not truncated for USD."""
        # This was the original bug: int("5.99") would fail or int(5.99) → 5
        amount_str = "5.99"
        minor = to_minor_units(amount_str, "USD")
        assert minor == 599  # Not 5!

        # Verify we can get back the exact value
        major = to_major_units(minor, "USD")
        assert major == Decimal("5.99")

    def test_no_truncation_edge_cases(self):
        """Test edge cases that might cause truncation."""
        test_cases = [
            ("0.99", "USD", 99),
            ("0.01", "USD", 1),
            ("9.99", "USD", 999),
            ("99.99", "USD", 9999),
            ("999.99", "USD", 99999),
        ]
        for amount_str, currency, expected in test_cases:
            assert to_minor_units(amount_str, currency) == expected

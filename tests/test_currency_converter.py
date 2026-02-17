"""
Unit tests for CurrencyConverterService.
"""

import pytest
from datetime import datetime, timezone
from domain.services.currency_converter import CurrencyConverterService


class TestCurrencyConverterService:
    """Test the CurrencyConverterService class."""

    def test_singleton_pattern(self):
        """Test that get_instance returns the same instance."""
        instance1 = CurrencyConverterService.get_instance()
        instance2 = CurrencyConverterService.get_instance()
        assert instance1 is instance2

    def test_convert_same_currency(self):
        """Test that converting same currency returns original amount."""
        converter = CurrencyConverterService.get_instance()
        amount = 1000.0
        date = datetime(2025, 1, 1, tzinfo=timezone.utc)

        result = converter.convert(amount, 'JPY', 'JPY', date)
        assert result == amount

    def test_convert_different_currencies(self):
        """Test conversion between different currencies."""
        converter = CurrencyConverterService.get_instance()
        amount = 100.0
        date = datetime(2025, 1, 1, tzinfo=timezone.utc)

        result = converter.convert(amount, 'USD', 'EUR', date)
        # Result should be different from original (unless rates are exactly 1.0)
        # and should be a positive number
        assert isinstance(result, float)
        assert result > 0

    def test_convert_with_historical_date(self):
        """Test conversion using historical date."""
        converter = CurrencyConverterService.get_instance()
        amount = 100.0
        date = datetime(2023, 6, 15, tzinfo=timezone.utc)

        result = converter.convert(amount, 'USD', 'EUR', date)
        assert isinstance(result, float)
        assert result > 0

    def test_convert_unsupported_currency_from(self):
        """Test conversion with unsupported source currency returns original."""
        converter = CurrencyConverterService.get_instance()
        amount = 100.0
        date = datetime(2025, 1, 1, tzinfo=timezone.utc)

        # Use a clearly unsupported currency code
        result = converter.convert(amount, 'XXX', 'USD', date)
        assert result == amount

    def test_convert_unsupported_currency_to(self):
        """Test conversion with unsupported target currency returns original."""
        converter = CurrencyConverterService.get_instance()
        amount = 100.0
        date = datetime(2025, 1, 1, tzinfo=timezone.utc)

        # Use a clearly unsupported currency code
        result = converter.convert(amount, 'USD', 'XXX', date)
        assert result == amount

    def test_is_supported(self):
        """Test currency support checking."""
        converter = CurrencyConverterService.get_instance()

        # Common currencies should be supported
        assert converter.is_supported('USD')
        assert converter.is_supported('EUR')
        assert converter.is_supported('JPY')
        assert converter.is_supported('GBP')

        # Clearly fake currency should not be supported
        assert not converter.is_supported('XXX')
        assert not converter.is_supported('FAKE')

    def test_convert_with_future_date(self):
        """Test conversion with future date uses fallback."""
        converter = CurrencyConverterService.get_instance()
        amount = 100.0
        future_date = datetime(2030, 1, 1, tzinfo=timezone.utc)

        # Should use fallback_on_wrong_date and return a valid conversion
        result = converter.convert(amount, 'USD', 'EUR', future_date)
        assert isinstance(result, float)
        assert result > 0

    def test_convert_zero_amount(self):
        """Test conversion of zero amount."""
        converter = CurrencyConverterService.get_instance()
        amount = 0.0
        date = datetime(2025, 1, 1, tzinfo=timezone.utc)

        result = converter.convert(amount, 'USD', 'EUR', date)
        assert result == 0.0

    def test_convert_negative_amount(self):
        """Test conversion of negative amount (refunds)."""
        converter = CurrencyConverterService.get_instance()
        amount = -100.0
        date = datetime(2025, 1, 1, tzinfo=timezone.utc)

        result = converter.convert(amount, 'USD', 'EUR', date)
        # Result should be negative and converted
        assert result < 0
        assert isinstance(result, float)

    def test_convert_weekend_date(self):
        """Test conversion with weekend date (Saturday) - should fallback to nearest available."""
        converter = CurrencyConverterService.get_instance()

        # Saturday May 24, 2025
        saturday = datetime(2025, 5, 24, 10, 24, 59, tzinfo=timezone.utc)
        amount = 207000

        # Convert JPY to EUR on a Saturday (ECB doesn't publish on weekends)
        result = converter.convert(amount, 'JPY', 'EUR', saturday)

        # Should successfully convert (fallback to nearest date)
        # Expected result is around 1,280-1,285 EUR
        assert result != amount  # Should be converted, not original
        assert 1200 < result < 1400  # Reasonable range for JPY->EUR conversion
        assert isinstance(result, float)

        # Compare with Friday (should be similar)
        friday = datetime(2025, 5, 23, 10, 24, 59, tzinfo=timezone.utc)
        friday_result = converter.convert(amount, 'JPY', 'EUR', friday)

        # Weekend and weekday results should be within 5% of each other
        assert abs(result - friday_result) / friday_result < 0.05

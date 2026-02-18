"""
Currency conversion service using European Central Bank (ECB) exchange rates.
"""

import logging
import os.path as op
import threading
from datetime import datetime

from currency_converter import CurrencyConverter

from config import get_currency_data_file

logger = logging.getLogger(__name__)


class CurrencyConverterService:
    """
    Singleton service for currency conversion using ECB exchange rates.
    Thread-safe for Flask multi-worker environments.
    """

    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "CurrencyConverterService":
        """Get or create singleton instance (thread-safe)."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def __init__(self):
        """Initialize with CurrencyConverter (ECB data, fallback enabled)."""
        try:
            # Use downloaded data file if available, otherwise use bundled data
            data_file = get_currency_data_file()
            if op.exists(data_file):
                self.converter = CurrencyConverter(
                    data_file, fallback_on_wrong_date=True, fallback_on_missing_rate=True
                )
                logger.info(f"CurrencyConverter initialized with data from {data_file}")
            else:
                self.converter = CurrencyConverter(
                    fallback_on_wrong_date=True, fallback_on_missing_rate=True
                )
                logger.warning(f"Using bundled currency data (file not found: {data_file})")

            self.available_currencies = set(self.converter.currencies)
            logger.info(f"CurrencyConverter loaded {len(self.available_currencies)} currencies")
        except Exception as e:
            logger.error(f"Failed to initialize CurrencyConverter: {e}")
            self.converter = None
            self.available_currencies = set()

    def convert(self, amount: float, from_currency: str, to_currency: str, date: datetime) -> float:
        """
        Convert amount from one currency to another at specific date.

        Args:
            amount: Amount to convert (in from_currency)
            from_currency: ISO 4217 code (e.g., 'JPY')
            to_currency: ISO 4217 code (e.g., 'USD')
            date: Transaction date (timezone-aware datetime)

        Returns:
            Converted amount in to_currency
            Returns original amount if conversion fails

        Behavior:
            - If currencies are same: returns original amount (no conversion)
            - If converter unavailable: logs warning, returns original amount
            - If currency unsupported: logs warning, returns original amount
            - If rate unavailable for date: uses fallback_on_wrong_date (nearest date)
        """
        # Same currency - no conversion needed
        if from_currency == to_currency:
            return float(amount)

        # Converter not available
        if not self.converter:
            logger.warning(
                f"CurrencyConverter unavailable, cannot convert {from_currency} to {to_currency}"
            )
            return float(amount)

        # Check currency support
        if from_currency not in self.available_currencies:
            logger.warning(f"Currency {from_currency} not supported by ECB, cannot convert")
            return float(amount)

        if to_currency not in self.available_currencies:
            logger.warning(f"Currency {to_currency} not supported by ECB, cannot convert")
            return float(amount)

        try:
            # Convert using ECB rates for transaction date
            converted = self.converter.convert(
                amount=float(amount),
                currency=from_currency,
                new_currency=to_currency,
                date=date.date(),  # CurrencyConverter expects date object, not datetime
            )
            # Round to 2 decimal places (cents)
            return round(converted, 2)
        except Exception as e:
            logger.error(
                f"Conversion failed: {amount} {from_currency} -> {to_currency} on {date}: {e}"
            )
            return round(float(amount), 2)

    def is_supported(self, currency_code: str) -> bool:
        """Check if currency is supported by ECB data."""
        return currency_code in self.available_currencies

    @classmethod
    def reload_data(cls, filepath: str):
        """
        Reload converter with fresh data (thread-safe).

        Args:
            filepath: Path to ECB data file (zip or CSV)
        """
        with cls._lock:
            if cls._instance:
                try:
                    cls._instance.converter = CurrencyConverter(
                        filepath, fallback_on_wrong_date=True, fallback_on_missing_rate=True
                    )
                    cls._instance.available_currencies = set(cls._instance.converter.currencies)
                    logger.info(f"Reloaded currency data from {filepath}")
                except Exception as e:
                    logger.error(f"Failed to reload currency data: {e}")

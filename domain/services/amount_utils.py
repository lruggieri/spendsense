"""
Utilities for converting monetary amounts between major and minor currency units.

This module handles the conversion between:
- Major units (dollars, euros, yen) - Human-readable format like "5.99"
- Minor units (cents, etc.) - Integer storage format like 599

Based on ISO 4217 currency standards:
- 0 decimals: JPY, KRW, ISK (no fractional units)
- 2 decimals: USD, EUR, GBP, etc. (most currencies)
- 3 decimals: BHD, KWD, OMR (not currently supported)

Example flows:
- Input: "5.99" USD → Store: 599 cents → Display: "5.99"
- Input: "1234" JPY → Store: 1234 yen → Display: "1,234"
"""

import logging
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Union

from config import get_currency_minor_units

logger = logging.getLogger(__name__)


def to_minor_units(amount_str: str, currency: str) -> int:
    """
    Convert amount string to minor currency units (cents).

    Uses Decimal for precision to avoid floating point errors.
    Rounds to nearest integer using ROUND_HALF_UP (banker's rounding).

    Args:
        amount_str: Amount as string (e.g., "5.99", "1234.567")
        currency: ISO 4217 currency code (e.g., "USD", "JPY")

    Returns:
        Amount in minor units as integer (e.g., 599 cents for "$5.99")

    Raises:
        ValueError: If amount_str cannot be converted to Decimal
        InvalidOperation: If Decimal operation fails

    Examples:
        to_minor_units("5.99", "USD") -> 599
        to_minor_units("5.995", "USD") -> 600 (rounds up)
        to_minor_units("1234", "JPY") -> 1234
        to_minor_units("0.01", "USD") -> 1
        to_minor_units("0", "USD") -> 0
    """
    try:
        # Get number of decimal places for this currency
        minor_units = get_currency_minor_units(currency)

        # Convert string to Decimal for precision
        decimal_amount = Decimal(amount_str)

        # Calculate multiplier (10^minor_units)
        multiplier = Decimal(10 ** minor_units)

        # Multiply and round to nearest integer
        result = (decimal_amount * multiplier).quantize(Decimal('1'), rounding=ROUND_HALF_UP)

        return int(result)

    except (ValueError, InvalidOperation) as e:
        logger.error(f"Failed to convert amount '{amount_str}' for currency {currency}: {e}")
        raise ValueError(f"Invalid amount format: '{amount_str}'") from e


def to_major_units(amount_minor: int, currency: str) -> Decimal:
    """
    Convert minor currency units to major units as Decimal.

    Args:
        amount_minor: Amount in minor units (e.g., 599 cents)
        currency: ISO 4217 currency code (e.g., "USD", "JPY")

    Returns:
        Amount in major units as Decimal (e.g., Decimal('5.99'))

    Examples:
        to_major_units(599, "USD") -> Decimal('5.99')
        to_major_units(1234, "JPY") -> Decimal('1234')
        to_major_units(1, "USD") -> Decimal('0.01')
        to_major_units(0, "USD") -> Decimal('0')
    """
    # Get number of decimal places for this currency
    minor_units = get_currency_minor_units(currency)

    # Calculate divisor (10^minor_units)
    divisor = Decimal(10 ** minor_units)

    # Divide to get major units
    return Decimal(amount_minor) / divisor


def to_major_units_float(amount_minor: int, currency: str) -> float:
    """
    Convert minor currency units to major units as float.

    Convenience method for backward compatibility with code expecting floats.
    For precise calculations, prefer to_major_units() which returns Decimal.

    Args:
        amount_minor: Amount in minor units (e.g., 599 cents)
        currency: ISO 4217 currency code (e.g., "USD", "JPY")

    Returns:
        Amount in major units as float (e.g., 5.99)

    Examples:
        to_major_units_float(599, "USD") -> 5.99
        to_major_units_float(1234, "JPY") -> 1234.0
    """
    return float(to_major_units(amount_minor, currency))


def format_amount(amount_minor: int, currency: str, include_decimals: bool = True, thousands_sep: bool = False) -> str:
    """
    Format amount for display.

    Args:
        amount_minor: Amount in minor units (e.g., 599 cents)
        currency: ISO 4217 currency code (e.g., "USD", "JPY")
        include_decimals: Whether to include decimal places. If False or currency
                         has 0 minor units, returns integer format.
        thousands_sep: Whether to include thousands separators (commas)

    Returns:
        Formatted amount string (e.g., "5.99", "1234", "1,234,567.89")

    Examples:
        format_amount(599, "USD") -> "5.99"
        format_amount(599, "USD", include_decimals=False) -> "5"
        format_amount(1234, "JPY") -> "1234"
        format_amount(1234567, "JPY", thousands_sep=True) -> "1,234,567"
        format_amount(1, "USD") -> "0.01"
        format_amount(99999, "USD") -> "999.99"
        format_amount(99999, "USD", thousands_sep=True) -> "999.99"
        format_amount(123456789, "USD", thousands_sep=True) -> "1,234,567.89"
    """
    # Convert to major units
    major = to_major_units(amount_minor, currency)

    # Get number of decimal places
    minor_units = get_currency_minor_units(currency)

    # If no decimals needed, return as integer
    if not include_decimals or minor_units == 0:
        if thousands_sep:
            return f"{int(major):,}"
        return str(int(major))

    # Format with appropriate decimal places
    if thousands_sep:
        return f"{major:,.{minor_units}f}"
    return f"{major:.{minor_units}f}"


def format_major_amount(amount_major: Union[float, Decimal], currency: str, thousands_sep: bool = False) -> str:
    """
    Format an amount that's already in major units (e.g., from currency conversions).

    This is useful when you have amounts as floats (like after currency conversion)
    rather than amounts in minor units (integers stored in the database).

    Args:
        amount_major: Amount in major units as float or Decimal (e.g., 5.99, 1234.0)
        currency: ISO 4217 currency code (e.g., "USD", "JPY")
        thousands_sep: Whether to include thousands separators (commas)

    Returns:
        Formatted amount string (e.g., "5.99", "1234", "1,234,567")

    Examples:
        format_major_amount(5.99, "USD") -> "5.99"
        format_major_amount(1234.0, "JPY") -> "1234"
        format_major_amount(1234567.0, "JPY", thousands_sep=True) -> "1,234,567"
        format_major_amount(1234567.89, "USD", thousands_sep=True) -> "1,234,567.89"
        format_major_amount(0.01, "USD") -> "0.01"
    """
    # Get number of decimal places for this currency
    minor_units = get_currency_minor_units(currency)

    # If currency has no decimals (JPY, KRW, etc.), round to integer
    if minor_units == 0:
        rounded = int(round(amount_major))
        if thousands_sep:
            return f"{rounded:,}"
        return str(rounded)

    # Format with appropriate decimal places
    if thousands_sep:
        return f"{amount_major:,.{minor_units}f}"
    return f"{amount_major:.{minor_units}f}"


def validate_amount(amount_minor: int, currency: str) -> bool:
    """
    Validate that an amount is within acceptable bounds.

    SQLite INTEGER is signed 64-bit: -2^63 to 2^63-1
    Max safe amount: ~$92 quadrillion (more than sufficient for expenses)

    Args:
        amount_minor: Amount in minor units
        currency: ISO 4217 currency code

    Returns:
        True if amount is valid, False otherwise

    Examples:
        validate_amount(599, "USD") -> True
        validate_amount(2**63, "USD") -> False (overflow)
        validate_amount(-100, "USD") -> True (negative amounts OK for refunds)
    """
    # SQLite INTEGER max value
    MAX_SQLITE_INTEGER = 2**63 - 1
    MIN_SQLITE_INTEGER = -(2**63)

    if amount_minor > MAX_SQLITE_INTEGER:
        logger.error(f"Amount {amount_minor} exceeds maximum SQLite INTEGER value")
        return False

    if amount_minor < MIN_SQLITE_INTEGER:
        logger.error(f"Amount {amount_minor} below minimum SQLite INTEGER value")
        return False

    return True


def parse_and_convert(amount_input: Union[str, int, float], currency: str) -> int:
    """
    Parse various amount formats and convert to minor units.

    Convenience method that handles strings, ints, and floats.

    Args:
        amount_input: Amount in various formats ("5.99", 5.99, 5, etc.)
        currency: ISO 4217 currency code

    Returns:
        Amount in minor units

    Raises:
        ValueError: If amount cannot be parsed

    Examples:
        parse_and_convert("5.99", "USD") -> 599
        parse_and_convert(5.99, "USD") -> 599
        parse_and_convert(5, "USD") -> 500
        parse_and_convert("1234", "JPY") -> 1234
    """
    # Convert to string if not already
    if isinstance(amount_input, (int, float)):
        amount_str = str(amount_input)
    else:
        amount_str = amount_input

    return to_minor_units(amount_str, currency)

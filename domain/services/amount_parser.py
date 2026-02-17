"""
Intelligent amount parser that handles various international number formats.

This module provides utilities to parse monetary amounts from strings,
automatically detecting whether commas are decimal separators or thousands separators.
"""

from decimal import Decimal, InvalidOperation
from typing import Optional
import re


def parse_amount(amount_str: str) -> Optional[str]:
    """
    Parse a monetary amount string intelligently, handling various formats.

    This function automatically detects the number format by analyzing the string:
    - US/UK/Japan format: 1,234.56 (comma as thousands separator, dot as decimal)
    - European format: 1.234,56 (dot as thousands separator, comma as decimal)
    - No separator: 1234 or 1234.56

    Args:
        amount_str: String containing the amount (e.g., "5,99", "1.234,56", "1,234.56")

    Returns:
        String representation of the amount in normalized format (dot as decimal separator),
        or None if parsing fails.

    Examples:
        >>> parse_amount("5,99")  # European: 5.99
        '5.99'
        >>> parse_amount("5.99")  # US: 5.99
        '5.99'
        >>> parse_amount("1,234.56")  # US with thousands separator
        '1234.56'
        >>> parse_amount("1.234,56")  # European with thousands separator
        '1234.56'
        >>> parse_amount("1234")  # No separators
        '1234'
        >>> parse_amount("1,232")  # Japanese Yen (no decimals)
        '1232'
    """
    if not amount_str:
        return None

    # Strip whitespace
    amount_str = amount_str.strip()

    # Check if negative (leading minus sign)
    is_negative = amount_str.startswith('-')

    # Remove any non-digit, non-comma, non-dot characters (except leading minus)
    cleaned = re.sub(r'[^\d,.]', '', amount_str)

    if not cleaned:
        return None

    # Try to use Babel for intelligent parsing if available
    try:
        from babel.numbers import parse_decimal, NumberFormatError

        # Detect format based on pattern analysis
        locale = _detect_locale(cleaned)

        try:
            # Parse using the detected locale
            decimal_value = parse_decimal(cleaned, locale=locale)
            # Return as string with dot as decimal separator
            # Remove trailing zeros and unnecessary decimal point
            result = str(decimal_value)
            if '.' in result:
                # Remove trailing zeros after decimal point
                result = result.rstrip('0').rstrip('.')
            # Apply negative sign if original value was negative
            if is_negative and not result.startswith('-'):
                result = '-' + result
            return result
        except NumberFormatError:
            # Fall back to heuristic approach
            pass
    except ImportError:
        # Babel not available, use heuristic approach
        pass

    # Fallback: Use heuristic detection
    result = _parse_amount_heuristic(cleaned)
    # Apply negative sign if original value was negative
    if result and is_negative and not result.startswith('-'):
        result = '-' + result
    return result


def _detect_locale(amount_str: str) -> str:
    """
    Detect the locale based on the format of the number string.

    Args:
        amount_str: Cleaned amount string containing only digits, commas, and dots

    Returns:
        Locale string ('en_US' for US format, 'de_DE' for European format)
    """
    # Count commas and dots
    comma_count = amount_str.count(',')
    dot_count = amount_str.count('.')

    # Find positions of last comma and last dot
    last_comma_pos = amount_str.rfind(',')
    last_dot_pos = amount_str.rfind('.')

    # Pattern analysis:
    # If there's only one separator and it has exactly 2 digits after it, it's likely a decimal separator
    if comma_count == 1 and dot_count == 0:
        # Only comma present
        if last_comma_pos > 0 and len(amount_str) - last_comma_pos - 1 == 2:
            # Format: X,XX - European decimal separator (e.g., "5,99")
            return 'de_DE'
        else:
            # Format: X,XXX - US thousands separator (e.g., "1,234")
            return 'en_US'

    if dot_count == 1 and comma_count == 0:
        # Only dot present
        if last_dot_pos > 0 and len(amount_str) - last_dot_pos - 1 <= 2:
            # Format: X.XX - US decimal separator (e.g., "5.99")
            return 'en_US'
        else:
            # Format: X.XXX - European thousands separator (e.g., "1.234")
            return 'de_DE'

    # Both separators present - the one that appears last is the decimal separator
    if comma_count > 0 and dot_count > 0:
        if last_comma_pos > last_dot_pos:
            # Comma is after dot: European format (e.g., "1.234,56")
            return 'de_DE'
        else:
            # Dot is after comma: US format (e.g., "1,234.56")
            return 'en_US'

    # Default to US format
    return 'en_US'


def _parse_amount_heuristic(amount_str: str) -> Optional[str]:
    """
    Parse amount using heuristic rules (fallback when Babel is not available).

    Args:
        amount_str: Cleaned amount string containing only digits, commas, and dots

    Returns:
        String representation of the amount with dot as decimal separator, or None if parsing fails
    """
    # Detect locale using our heuristic
    locale = _detect_locale(amount_str)

    try:
        if locale == 'de_DE':
            # European format: dot is thousands separator, comma is decimal separator
            # Remove dots (thousands separators) and replace comma with dot
            normalized = amount_str.replace('.', '').replace(',', '.')
        else:
            # US format: comma is thousands separator, dot is decimal separator
            # Remove commas (thousands separators)
            normalized = amount_str.replace(',', '')

        # Parse as decimal
        decimal_value = Decimal(normalized)

        # Return as string with dot as decimal separator
        result = str(decimal_value)
        if '.' in result:
            # Remove trailing zeros after decimal point
            result = result.rstrip('0').rstrip('.')
        return result

    except (InvalidOperation, ValueError):
        return None


# For backwards compatibility with existing code
def clean_amount(amount_str: str) -> Optional[str]:
    """
    Clean and parse an amount string (legacy function name).

    This is a wrapper around parse_amount() for backwards compatibility.

    Args:
        amount_str: String containing the amount

    Returns:
        String representation of the amount in cents
    """
    return parse_amount(amount_str)

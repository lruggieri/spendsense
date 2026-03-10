"""
Shared utilities for parsing transactions from email text using regex patterns.

This module provides reusable functions for extracting transaction data
(amounts, merchants, currencies) from email bodies using regex patterns.
Used by both DBFetcherAdapter and the web UI for pattern testing.
"""

from typing import List, Optional

import regex

from config import normalize_currency_code
from domain.services.amount_parser import parse_amount

_REGEX_FLAGS = regex.MULTILINE | regex.DOTALL
_REGEX_TIMEOUT = 5  # seconds per findall call


def flatten_regex_results(results: list) -> list:
    """
    Flatten regex results that may contain tuples from alternation patterns.

    When using patterns with alternation (A|B), re.findall returns tuples:
    - [('', '880')] or [('3704', '')]

    This function flattens them to just the non-empty value:
    - ['880'] or ['3704']

    Args:
        results: Output from regex.findall() - could be list of strings or list of tuples

    Returns:
        List of strings with alternation tuples flattened
    """
    if not results:
        return []

    # Check if results are tuples (from alternation patterns)
    if results and isinstance(results[0], tuple):
        flattened = []
        for item in results:
            # Find first non-empty value in tuple
            for val in item:
                if val:
                    flattened.append(val)
                    break
        return flattened
    else:
        return results


def parse_transactions_with_patterns(
    email_text: str,
    amount_pattern: Optional[str],
    merchant_pattern: Optional[str],
    currency_pattern: Optional[str],
    negate_amount: bool = False,
) -> List[dict]:
    """
    Parse transactions from email using regex patterns.

    Args:
        email_text: Email body text
        amount_pattern: Regex pattern for amounts (or None if no transaction data)
        merchant_pattern: Regex pattern for merchants (or None if no transaction data)
        currency_pattern: Regex pattern for currency (or None)
        negate_amount: If True, negate amounts (for income/refunds)

    Returns:
        List of transaction dictionaries with amount, merchant, currency keys
        Returns empty list if patterns are None (no transaction data detected)
    """
    # Check if patterns are None/empty (no transaction data detected)
    if not amount_pattern and not merchant_pattern:
        return []

    # Extract amounts (if pattern available)
    amounts = []
    if amount_pattern:
        amounts_raw = regex.findall(amount_pattern, email_text, _REGEX_FLAGS, timeout=_REGEX_TIMEOUT)
        amounts = flatten_regex_results(amounts_raw)

    # Extract merchants (if pattern available)
    merchants = []
    if merchant_pattern:
        merchants_raw = regex.findall(merchant_pattern, email_text, _REGEX_FLAGS, timeout=_REGEX_TIMEOUT)
        merchants = flatten_regex_results(merchants_raw)

    # Extract currencies (may be empty, one, or N)
    currencies = []
    if currency_pattern:
        currencies_raw = regex.findall(currency_pattern, email_text, _REGEX_FLAGS, timeout=_REGEX_TIMEOUT)
        currencies = flatten_regex_results(currencies_raw)

    # Build transaction list
    transactions = []

    # Handle partial patterns: loop over whichever has more entries
    max_transactions = max(len(amounts), len(merchants)) if (amounts or merchants) else 0

    for i in range(max_transactions):
        # Parse amount intelligently
        amount = parse_amount(amounts[i]) if i < len(amounts) else None

        # Apply negation if requested
        if amount and negate_amount:
            amount = "-" + amount

        # Get merchant
        merchant = merchants[i].strip() if i < len(merchants) else None

        # Get currency
        if len(currencies) == 0:
            currency = None
        elif len(currencies) == 1:
            currency = currencies[0]  # Global currency
        elif i < len(currencies):
            currency = currencies[i]  # Per-transaction currency
        else:
            currency = None

        # Normalize currency symbol/name to ISO code (e.g., 円 → JPY)
        if currency:
            currency = normalize_currency_code(currency)

        transactions.append({"amount": amount, "merchant": merchant, "currency": currency})

    return transactions

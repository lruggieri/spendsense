"""
Database Fetcher Adapter.

Wraps a database Fetcher entity to provide Gmail fetching functionality
using regex patterns stored in the database.
"""

from typing import List, Tuple, Optional

from infrastructure.email.fetchers.pattern_parser import parse_transactions_with_patterns
from domain.entities.fetcher import Fetcher
from infrastructure.email.gmail_utils import get_body_from_message


class DBFetcherAdapter:
    """
    Adapter that wraps a database Fetcher entity.

    Provides methods to build Gmail filters and parse transactions
    using regex patterns stored in the database.
    """

    def __init__(self, fetcher: Fetcher):
        """
        Initialize adapter with a database Fetcher entity.

        Args:
            fetcher: Database Fetcher entity with regex patterns
        """
        self._fetcher = fetcher

    @property
    def name(self) -> str:
        return self._fetcher.name

    @property
    def description(self) -> str:
        """Build description from fetcher configuration."""
        emails = ', '.join(self._fetcher.from_emails[:2])
        if len(self._fetcher.from_emails) > 2:
            emails += '...'
        return f"Fetches transactions from {emails}"

    @property
    def enabled(self) -> bool:
        return self._fetcher.enabled

    @property
    def default_currency(self) -> str:
        return self._fetcher.default_currency

    @property
    def id(self) -> str:
        """Return the database fetcher ID."""
        return self._fetcher.id

    def get_gmail_filter(self, after_date: str) -> str:
        """
        Build Gmail query filter from fetcher configuration.

        Args:
            after_date: Date string to filter emails (e.g., '2025-06-01')

        Returns:
            Gmail query string
        """
        # Build from: filter (multiple emails use OR)
        from_emails = self._fetcher.from_emails
        if len(from_emails) == 1:
            from_filter = f"from:{from_emails[0]}"
        else:
            # Multiple emails: (from:a OR from:b OR from:c)
            from_parts = [f"from:{email}" for email in from_emails]
            from_filter = f"({' OR '.join(from_parts)})"

        # Build subject filter if present
        subject_filter = ""
        if self._fetcher.subject_filter:
            subject_filter = f" subject:{self._fetcher.subject_filter}"

        return f"{from_filter}{subject_filter} after:{after_date}"

    def parse_transaction(self, message: dict) -> List[Tuple[Optional[str], Optional[str], Optional[str]]]:
        """
        Parse transaction from email using regex patterns.

        Args:
            message: Gmail API message object

        Returns:
            List of (amount, merchant, currency) tuples
        """
        body = get_body_from_message(message)
        if not body:
            return []

        # Parse using stored regex patterns
        transactions = parse_transactions_with_patterns(
            body,
            self._fetcher.amount_pattern,
            self._fetcher.merchant_pattern,
            self._fetcher.currency_pattern,
            self._fetcher.negate_amount
        )

        # Convert to tuple format expected by fetch pipeline
        result = []
        for tx in transactions:
            amount = tx.get('amount')
            merchant = tx.get('merchant')
            currency = tx.get('currency')
            if amount:  # Only include if we found an amount
                result.append((amount, merchant, currency))

        return result

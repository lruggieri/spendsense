"""
Fetcher entity.

Defines the Fetcher domain object for email transaction fetchers.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class Fetcher:
    """
    Domain entity for email transaction fetchers.

    Represents configuration for parsing transactions from specific email sources.
    Used for Gmail-based transaction fetching with customizable regex patterns.

    Versioning: Fetchers use immutability semantics - edits create new versions
    rather than modifying existing records. All versions share the same group_id.
    """
    id: str
    user_id: str
    name: str                           # Display name (e.g., "Chase Credit Card")
    from_emails: List[str]              # Email addresses to filter by
    subject_filter: str = ''            # Optional subject line filter
    amount_pattern: str = ''            # Regex pattern for extracting amount
    merchant_pattern: Optional[str] = None   # Regex pattern for extracting merchant
    currency_pattern: Optional[str] = None   # Regex pattern for extracting currency
    default_currency: str = 'USD'       # Fallback currency if not extracted
    negate_amount: bool = False         # If True, negate amounts (for income/refunds)
    enabled: bool = True                # Whether fetcher is active
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    group_id: Optional[str] = None      # UUID grouping all versions of this fetcher
    version: int = 1                    # Version number within the group

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional

ENCRYPTED_PLACEHOLDER = "[Encrypted]"


class CategorySource(Enum):
    """Source of the category assignment."""

    REGEXP = "regexp"
    MANUAL = "manual"
    SIMILARITY = "similarity"


@dataclass
class Transaction:
    id: str
    date: datetime
    amount: int
    description: str
    category: str
    source: str  # Source of the transaction (e.g., "Sony Bank", "Amazon", "PayPay (IFTTT)")
    currency: str = "JPY"  # ISO 4217 currency code (e.g., JPY, USD, EUR)
    category_source: Optional[CategorySource] = None
    mail_id: Optional[str] = None  # Gmail message ID (for email-fetched transactions)
    comment: str = ""  # User-added comment for this transaction
    groups: List[str] = field(default_factory=list)  # List of group IDs this transaction belongs to
    updated_at: Optional[datetime] = None  # Last update timestamp
    created_at: Optional[datetime] = (
        None  # Immutable timestamp of when transaction was fetched/created (auto-set if None)
    )
    fetcher_id: Optional[str] = None  # ID of the fetcher version that created this transaction
    encrypted: bool = False  # Whether this transaction's fields are stored encrypted at rest

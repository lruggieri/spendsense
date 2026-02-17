"""
User settings entity.

Defines the UserSettings domain object with business-friendly field names,
separate from database column names for clean architecture.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class UserSettings:
    """
    Domain entity for user settings.
    Uses business-friendly field names (not tied to DB schema).
    """

    user_id: str
    language: str = "en"  # ISO 639-1 code
    currency: str = "USD"  # ISO 4217 code
    browser_settings: Dict[str, Any] = field(
        default_factory=dict
    )  # Browser-specific settings (JSON)
    llm_call_timestamps: List[datetime] = field(
        default_factory=list
    )  # Timestamps of LLM API calls for rate limiting
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


def get_default_settings(user_id: str) -> UserSettings:
    """Factory function to create default settings."""
    return UserSettings(
        user_id=user_id, language="en", currency="USD", browser_settings={}, llm_call_timestamps=[]
    )

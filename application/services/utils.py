"""
Shared utilities for the services module.
"""

from datetime import datetime, timezone


def parse_date(date_str: str) -> datetime:
    """
    Parse date string into timezone-aware datetime object in UTC.

    Supports:
    - ISO 8601 with timezone: 2025-12-19T15:30:00Z or 2025-12-19T15:30:00+09:00
    - Simple date string: 2025-12-19 (interpreted as midnight UTC)

    Args:
        date_str: Date string to parse

    Returns:
        Timezone-aware datetime in UTC

    Raises:
        ValueError: If date string cannot be parsed
    """
    # Try ISO 8601 format first
    if "T" in date_str:
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt
        except (ValueError, AttributeError):
            pass

    # Try simple date format (YYYY-MM-DD) - interpret as midnight UTC
    if len(date_str) == 10 and date_str.count("-") == 2:
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    raise ValueError(f"Unable to parse date '{date_str}': expected 'YYYY-MM-DD' or ISO 8601 format")

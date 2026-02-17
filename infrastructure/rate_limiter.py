"""
Rate limiter for LLM API calls.

Limits the number of LLM calls per user within a rolling 24-hour window.
"""

from datetime import datetime, timezone, timedelta
from typing import Tuple, Dict, Any

from domain.repositories.user_settings_repository import UserSettingsRepository


class LLMRateLimiter:
    """
    Rate limiter for LLM API calls using a rolling 24-hour window.

    Stores timestamps in user settings and performs lazy cleanup of old timestamps
    on each check.
    """

    MAX_CALLS = 50
    WINDOW_HOURS = 24

    def __init__(self, datasource: UserSettingsRepository):
        """
        Initialize the rate limiter.

        Args:
            datasource: User settings datasource for the current user
        """
        self.datasource = datasource

    def _cleanup_old_timestamps(self, timestamps: list) -> list:
        """
        Remove timestamps older than the rolling window.

        Args:
            timestamps: List of datetime objects

        Returns:
            List of datetime objects within the rolling window
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.WINDOW_HOURS)
        return [ts for ts in timestamps if ts > cutoff]

    def _get_reset_time(self, timestamps: list) -> datetime:
        """
        Calculate when the rate limit will reset (oldest timestamp + 24h).

        Args:
            timestamps: List of datetime objects (assumed to be within window)

        Returns:
            Datetime when the oldest call expires from the window
        """
        if not timestamps:
            return datetime.now(timezone.utc)

        oldest = min(timestamps)
        return oldest + timedelta(hours=self.WINDOW_HOURS)

    def check_rate_limit(self) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if the user can make another LLM call.

        Performs lazy cleanup of old timestamps.

        Returns:
            Tuple of (allowed: bool, info: dict)
            info contains: limit, remaining, calls_made, and optionally reset_at
        """
        timestamps = self.datasource.get_llm_call_timestamps()
        timestamps = self._cleanup_old_timestamps(timestamps)

        calls_made = len(timestamps)
        remaining = max(0, self.MAX_CALLS - calls_made)
        allowed = calls_made < self.MAX_CALLS

        info = {
            'limit': self.MAX_CALLS,
            'remaining': remaining,
            'calls_made': calls_made
        }

        if not allowed:
            info['reset_at'] = self._get_reset_time(timestamps).strftime('%Y-%m-%dT%H:%M:%SZ')

        return allowed, info

    def record_call(self) -> bool:
        """
        Record a new LLM call timestamp.

        Also performs lazy cleanup of old timestamps.

        Returns:
            True if the timestamp was recorded successfully, False otherwise
        """
        timestamps = self.datasource.get_llm_call_timestamps()
        timestamps = self._cleanup_old_timestamps(timestamps)
        timestamps.append(datetime.now(timezone.utc))

        return self.datasource.update_llm_call_timestamps(timestamps)

    def get_rate_limit_info(self) -> Dict[str, Any]:
        """
        Get current rate limit info without modifying state.

        Returns:
            Dict with limit, remaining, and calls_made
        """
        _, info = self.check_rate_limit()
        return info

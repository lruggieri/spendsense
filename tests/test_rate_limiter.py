"""Tests for LLMRateLimiter."""
import unittest
import tempfile
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch

from infrastructure.persistence.sqlite.repositories.user_settings_repository import SQLiteUserSettingsDataSource
from infrastructure.rate_limiter import LLMRateLimiter


class TestLLMRateLimiter(unittest.TestCase):
    def setUp(self):
        """Create temporary database for each test."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.db_path = self.temp_db.name
        self.temp_db.close()
        self.user_id = "test_user@example.com"
        self.datasource = SQLiteUserSettingsDataSource(self.db_path, self.user_id)
        self.rate_limiter = LLMRateLimiter(self.datasource)

    def tearDown(self):
        """Clean up temporary database."""
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_allows_first_call(self):
        """Should allow the first LLM call."""
        allowed, info = self.rate_limiter.check_rate_limit()

        self.assertTrue(allowed)
        self.assertEqual(info['limit'], 50)
        self.assertEqual(info['remaining'], 50)
        self.assertEqual(info['calls_made'], 0)
        self.assertNotIn('reset_at', info)

    def test_allows_up_to_max_calls(self):
        """Should allow up to MAX_CALLS (50) calls."""
        # Record 49 calls
        for _ in range(49):
            self.rate_limiter.record_call()

        allowed, info = self.rate_limiter.check_rate_limit()

        self.assertTrue(allowed)
        self.assertEqual(info['remaining'], 1)
        self.assertEqual(info['calls_made'], 49)

    def test_blocks_after_max_calls(self):
        """Should block the 51st call."""
        # Record 50 calls
        for _ in range(50):
            self.rate_limiter.record_call()

        allowed, info = self.rate_limiter.check_rate_limit()

        self.assertFalse(allowed)
        self.assertEqual(info['remaining'], 0)
        self.assertEqual(info['calls_made'], 50)
        self.assertIn('reset_at', info)

    def test_cleanup_removes_old_timestamps(self):
        """Should remove timestamps older than 24 hours."""
        # Manually insert old timestamps
        old_time = datetime.now(timezone.utc) - timedelta(hours=25)
        recent_time = datetime.now(timezone.utc) - timedelta(hours=1)

        timestamps = [old_time, recent_time]
        self.datasource.update_llm_call_timestamps(timestamps)

        # Check rate limit (should clean up old timestamps)
        allowed, info = self.rate_limiter.check_rate_limit()

        self.assertTrue(allowed)
        self.assertEqual(info['calls_made'], 1)  # Only the recent one
        self.assertEqual(info['remaining'], 49)

    def test_allows_call_after_oldest_expires(self):
        """Should allow a call after the oldest timestamp expires from the window."""
        # Create timestamps: one very old (expired), rest recent
        old_time = datetime.now(timezone.utc) - timedelta(hours=25)
        recent_times = [datetime.now(timezone.utc) - timedelta(minutes=i) for i in range(49)]

        timestamps = [old_time] + recent_times
        self.datasource.update_llm_call_timestamps(timestamps)

        # Should be allowed because old timestamp is cleaned up
        allowed, info = self.rate_limiter.check_rate_limit()

        self.assertTrue(allowed)
        self.assertEqual(info['calls_made'], 49)  # Old one cleaned up
        self.assertEqual(info['remaining'], 1)

    def test_multi_user_isolation(self):
        """Should isolate rate limits per user."""
        user1_id = "user1@example.com"
        user2_id = "user2@example.com"

        datasource1 = SQLiteUserSettingsDataSource(self.db_path, user1_id)
        datasource2 = SQLiteUserSettingsDataSource(self.db_path, user2_id)

        rate_limiter1 = LLMRateLimiter(datasource1)
        rate_limiter2 = LLMRateLimiter(datasource2)

        # User 1 makes 50 calls
        for _ in range(50):
            rate_limiter1.record_call()

        # User 1 should be blocked
        allowed1, info1 = rate_limiter1.check_rate_limit()
        self.assertFalse(allowed1)
        self.assertEqual(info1['calls_made'], 50)

        # User 2 should still be allowed
        allowed2, info2 = rate_limiter2.check_rate_limit()
        self.assertTrue(allowed2)
        self.assertEqual(info2['calls_made'], 0)

    def test_record_call_returns_true_on_success(self):
        """Should return True when recording a call succeeds."""
        result = self.rate_limiter.record_call()
        self.assertTrue(result)

    def test_reset_at_is_oldest_timestamp_plus_24h(self):
        """Should calculate reset_at as oldest timestamp + 24 hours."""
        # Record 50 calls with known timestamps
        base_time = datetime.now(timezone.utc) - timedelta(hours=12)
        timestamps = [base_time + timedelta(minutes=i) for i in range(50)]
        self.datasource.update_llm_call_timestamps(timestamps)

        allowed, info = self.rate_limiter.check_rate_limit()

        self.assertFalse(allowed)
        self.assertIn('reset_at', info)

        # Parse reset_at and verify it's oldest + 24h
        reset_at = datetime.fromisoformat(info['reset_at'].rstrip('Z')).replace(tzinfo=timezone.utc)
        expected_reset = base_time + timedelta(hours=24)

        # Allow 1 second tolerance
        diff = abs((reset_at - expected_reset).total_seconds())
        self.assertLess(diff, 1.0)

    def test_get_rate_limit_info_returns_correct_structure(self):
        """Should return rate limit info with correct structure."""
        info = self.rate_limiter.get_rate_limit_info()

        self.assertIn('limit', info)
        self.assertIn('remaining', info)
        self.assertIn('calls_made', info)
        self.assertEqual(info['limit'], 50)

    def test_cleanup_preserves_boundary_timestamps(self):
        """Should preserve timestamps exactly at the 24-hour boundary."""
        # Create a timestamp exactly 23h59m ago (should be kept)
        almost_expired = datetime.now(timezone.utc) - timedelta(hours=23, minutes=59)
        timestamps = [almost_expired]
        self.datasource.update_llm_call_timestamps(timestamps)

        allowed, info = self.rate_limiter.check_rate_limit()

        self.assertTrue(allowed)
        self.assertEqual(info['calls_made'], 1)  # Should still be counted


class TestLLMRateLimiterConstants(unittest.TestCase):
    """Test rate limiter constants."""

    def test_max_calls_is_50(self):
        """MAX_CALLS should be 50."""
        self.assertEqual(LLMRateLimiter.MAX_CALLS, 50)

    def test_window_hours_is_24(self):
        """WINDOW_HOURS should be 24."""
        self.assertEqual(LLMRateLimiter.WINDOW_HOURS, 24)


if __name__ == '__main__':
    unittest.main()

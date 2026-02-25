"""Tests for the SQLite session repository."""

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from infrastructure.persistence.sqlite.repositories.session_repository import (
    SQLiteSessionDataSource,
)


class TestSQLiteSessionRepository(unittest.TestCase):
    """Tests for SQLiteSessionDataSource session management."""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.db_path = self.temp_db.name
        self.temp_db.close()

        # SQLiteSessionDataSource creates its own table via _ensure_table_exists,
        # so we just instantiate it.
        self.ds = SQLiteSessionDataSource(self.db_path)
        self.user_id = "test@example.com"
        self.profile = {"user_name": "Test User", "user_picture": "https://pic.example.com/p.jpg"}

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_create_session(self):
        """create_session should return a session token string."""
        expiration = datetime.now(timezone.utc) + timedelta(days=7)
        token = self.ds.create_session(self.user_id, self.profile, expiration)

        self.assertIsInstance(token, str)
        self.assertTrue(len(token) > 0)

    def test_get_session_valid(self):
        """get_session should return a Session for a valid, non-expired token."""
        expiration = datetime.now(timezone.utc) + timedelta(days=7)
        token = self.ds.create_session(self.user_id, self.profile, expiration)

        session = self.ds.get_session(token)
        self.assertIsNotNone(session)
        self.assertEqual(session.user_id, self.user_id)
        self.assertEqual(session.session_token, token)
        self.assertEqual(session.user_profile, self.profile)

    def test_get_session_expired(self):
        """get_session should return None for an expired session and clean it up."""
        import sqlite3

        expiration = datetime.now(timezone.utc) - timedelta(hours=1)
        token = self.ds.create_session(self.user_id, self.profile, expiration)

        session = self.ds.get_session(token)
        self.assertIsNone(session)

        # Verify it was cleaned up
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sessions WHERE session_token = ?", (token,))
        count = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(count, 0)

    def test_get_session_not_found(self):
        """get_session should return None for a non-existent token."""
        session = self.ds.get_session("nonexistent_token")
        self.assertIsNone(session)

    def test_delete_session(self):
        """delete_session should remove the session and return True."""
        expiration = datetime.now(timezone.utc) + timedelta(days=7)
        token = self.ds.create_session(self.user_id, self.profile, expiration)

        result = self.ds.delete_session(token)
        self.assertTrue(result)

        # Verify it's gone
        session = self.ds.get_session(token)
        self.assertIsNone(session)

    def test_delete_session_not_found(self):
        """delete_session should return False for a non-existent token."""
        result = self.ds.delete_session("nonexistent")
        self.assertFalse(result)

    def test_delete_user_sessions(self):
        """delete_user_sessions should remove all sessions for a user."""
        import sqlite3

        expiration = datetime.now(timezone.utc) + timedelta(days=7)
        self.ds.create_session(self.user_id, {"user_name": "A", "user_picture": ""}, expiration)
        self.ds.create_session(self.user_id, {"user_name": "B", "user_picture": ""}, expiration)
        self.ds.create_session(
            "other@example.com", {"user_name": "C", "user_picture": ""}, expiration
        )

        deleted = self.ds.delete_user_sessions(self.user_id)
        self.assertEqual(deleted, 2)

        # Other user's session should still exist
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sessions")
        count = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(count, 1)

    def test_cleanup_expired_sessions(self):
        """cleanup_expired_sessions should remove all expired sessions."""
        import sqlite3

        future = datetime.now(timezone.utc) + timedelta(days=7)
        past = datetime.now(timezone.utc) - timedelta(hours=1)

        self.ds.create_session(self.user_id, {"user_name": "valid", "user_picture": ""}, future)
        self.ds.create_session(self.user_id, {"user_name": "exp1", "user_picture": ""}, past)
        self.ds.create_session(
            "other@example.com", {"user_name": "exp2", "user_picture": ""}, past
        )

        deleted = self.ds.cleanup_expired_sessions()
        self.assertEqual(deleted, 2)

        # Only the valid session should remain
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sessions")
        count = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(count, 1)

    def test_update_session_expiration(self):
        """update_session_expiration should extend the session lifetime."""
        expiration = datetime.now(timezone.utc) + timedelta(days=1)
        token = self.ds.create_session(self.user_id, self.profile, expiration)

        new_expiration = datetime.now(timezone.utc) + timedelta(days=30)
        result = self.ds.update_session_expiration(token, new_expiration)
        self.assertTrue(result)

        session = self.ds.get_session(token)
        self.assertIsNotNone(session)
        # Expiration should be extended (roughly 30 days from now)
        self.assertTrue(session.expiration > datetime.now(timezone.utc) + timedelta(days=28))

    def test_update_session_expiration_not_found(self):
        """update_session_expiration should return False for a non-existent session."""
        new_expiration = datetime.now(timezone.utc) + timedelta(days=30)
        result = self.ds.update_session_expiration("nonexistent", new_expiration)
        self.assertFalse(result)

    def test_no_encryption_version_column(self):
        """The sessions table should NOT have an encryption_version column."""
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(sessions)")
        columns = [row[1] for row in cursor.fetchall()]
        conn.close()
        self.assertNotIn("encryption_version", columns)

    def test_has_user_profile_column(self):
        """The sessions table should have a user_profile column (not google_token)."""
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(sessions)")
        columns = [row[1] for row in cursor.fetchall()]
        conn.close()
        self.assertIn("user_profile", columns)
        self.assertNotIn("google_token", columns)


if __name__ == "__main__":
    unittest.main()

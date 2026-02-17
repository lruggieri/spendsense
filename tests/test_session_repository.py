"""Tests for the SQLite session repository."""
import base64
import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from infrastructure.persistence.sqlite.repositories.session_repository import SQLiteSessionDataSource


class TestSQLiteSessionRepository(unittest.TestCase):
    """Tests for SQLiteSessionDataSource session management."""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.db_path = self.temp_db.name
        self.temp_db.close()

        # SQLiteSessionDataSource creates its own table via _ensure_table_exists,
        # so we just instantiate it.
        self.ds = SQLiteSessionDataSource(self.db_path)
        self.user_id = "test@example.com"

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_create_session(self):
        """create_session should return a session token string."""
        expiration = datetime.now(timezone.utc) + timedelta(days=7)
        google_token = {"access_token": "tok123", "refresh_token": "ref456"}
        token = self.ds.create_session(self.user_id, google_token, expiration)

        self.assertIsInstance(token, str)
        self.assertTrue(len(token) > 0)

    def test_get_session_valid(self):
        """get_session should return a Session for a valid, non-expired token."""
        expiration = datetime.now(timezone.utc) + timedelta(days=7)
        google_token = {"access_token": "tok123"}
        token = self.ds.create_session(self.user_id, google_token, expiration)

        session = self.ds.get_session(token)
        self.assertIsNotNone(session)
        self.assertEqual(session.user_id, self.user_id)
        self.assertEqual(session.session_token, token)
        self.assertEqual(session.google_token, google_token)

    def test_get_session_expired(self):
        """get_session should return None for an expired session and clean it up."""
        expiration = datetime.now(timezone.utc) - timedelta(hours=1)
        google_token = {"access_token": "expired_tok"}
        token = self.ds.create_session(self.user_id, google_token, expiration)

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
        token = self.ds.create_session(self.user_id, {"access_token": "t"}, expiration)

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
        expiration = datetime.now(timezone.utc) + timedelta(days=7)
        self.ds.create_session(self.user_id, {"t": "1"}, expiration)
        self.ds.create_session(self.user_id, {"t": "2"}, expiration)
        self.ds.create_session("other@example.com", {"t": "3"}, expiration)

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
        future = datetime.now(timezone.utc) + timedelta(days=7)
        past = datetime.now(timezone.utc) - timedelta(hours=1)

        self.ds.create_session(self.user_id, {"t": "valid"}, future)
        self.ds.create_session(self.user_id, {"t": "expired1"}, past)
        self.ds.create_session("other@example.com", {"t": "expired2"}, past)

        deleted = self.ds.cleanup_expired_sessions()
        self.assertEqual(deleted, 2)

        # Only the valid session should remain
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sessions")
        count = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(count, 1)

    def test_update_google_token(self):
        """update_google_token should update the token for an existing session."""
        expiration = datetime.now(timezone.utc) + timedelta(days=7)
        token = self.ds.create_session(self.user_id, {"access_token": "old"}, expiration)

        new_google_token = {"access_token": "refreshed", "refresh_token": "new_ref"}
        result = self.ds.update_google_token(token, new_google_token)
        self.assertTrue(result)

        session = self.ds.get_session(token)
        self.assertEqual(session.google_token, new_google_token)

    def test_update_google_token_not_found(self):
        """update_google_token should return False for a non-existent session."""
        result = self.ds.update_google_token("nonexistent", {"access_token": "new"})
        self.assertFalse(result)

    def test_update_session_expiration(self):
        """update_session_expiration should extend the session lifetime."""
        expiration = datetime.now(timezone.utc) + timedelta(days=1)
        token = self.ds.create_session(self.user_id, {"t": "1"}, expiration)

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


def _generate_test_key() -> str:
    """Generate a base64-encoded 256-bit key for testing."""
    return base64.b64encode(os.urandom(32)).decode('ascii')


class TestEncryptedSessions(unittest.TestCase):
    """Tests for google_token encryption in sessions."""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.db_path = self.temp_db.name
        self.temp_db.close()
        self.ds = SQLiteSessionDataSource(self.db_path)
        self.user_id = "test@example.com"
        self.key = _generate_test_key()

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_create_session_encrypted(self):
        """Create session with encryption, retrieve with key — roundtrip."""
        expiration = datetime.now(timezone.utc) + timedelta(days=7)
        google_token = {"access_token": "tok123", "refresh_token": "ref456"}
        token = self.ds.create_session(self.user_id, google_token, expiration, encryption_key=self.key)

        session = self.ds.get_session(token, encryption_key=self.key)
        self.assertIsNotNone(session)
        self.assertEqual(session.google_token, google_token)

    def test_get_session_encrypted_without_key(self):
        """Get encrypted session without key — fallback to user_id/empty picture."""
        expiration = datetime.now(timezone.utc) + timedelta(days=7)
        google_token = {"access_token": "tok123", "user_name": "John Doe", "user_picture": "http://pic"}
        token = self.ds.create_session(self.user_id, google_token, expiration, encryption_key=self.key)

        session = self.ds.get_session(token)  # no key
        self.assertIsNotNone(session)
        self.assertEqual(session.google_token['user_name'], self.user_id)
        self.assertEqual(session.google_token['user_picture'], '')

    def test_update_google_token_encrypted(self):
        """Update token with encryption — preserves encryption."""
        expiration = datetime.now(timezone.utc) + timedelta(days=7)
        token = self.ds.create_session(self.user_id, {"access_token": "old"}, expiration, encryption_key=self.key)

        new_token = {"access_token": "refreshed", "refresh_token": "new_ref"}
        result = self.ds.update_google_token(token, new_token, encryption_key=self.key)
        self.assertTrue(result)

        session = self.ds.get_session(token, encryption_key=self.key)
        self.assertEqual(session.google_token, new_token)

    def test_encrypt_google_token_migration(self):
        """Encrypt existing plaintext session token."""
        expiration = datetime.now(timezone.utc) + timedelta(days=7)
        google_token = {"access_token": "tok", "user_name": "Test"}
        token = self.ds.create_session(self.user_id, google_token, expiration)  # plaintext

        result = self.ds.encrypt_google_token(token, self.key)
        self.assertTrue(result)

        # Should be readable with key
        session = self.ds.get_session(token, encryption_key=self.key)
        self.assertEqual(session.google_token, google_token)

        # Without key should get fallback
        session_no_key = self.ds.get_session(token)
        self.assertEqual(session_no_key.google_token['user_name'], self.user_id)

    def test_decrypt_google_token_migration(self):
        """Decrypt encrypted session token back to plaintext."""
        expiration = datetime.now(timezone.utc) + timedelta(days=7)
        google_token = {"access_token": "tok", "user_name": "Test"}
        token = self.ds.create_session(self.user_id, google_token, expiration, encryption_key=self.key)

        result = self.ds.decrypt_google_token(token, self.key)
        self.assertTrue(result)

        # Should be readable without key now
        session = self.ds.get_session(token)
        self.assertEqual(session.google_token, google_token)

    def test_no_key_plaintext_unchanged(self):
        """Creating and reading without key should work exactly as before."""
        expiration = datetime.now(timezone.utc) + timedelta(days=7)
        google_token = {"access_token": "tok123"}
        token = self.ds.create_session(self.user_id, google_token, expiration)

        session = self.ds.get_session(token)
        self.assertIsNotNone(session)
        self.assertEqual(session.google_token, google_token)

    def test_encrypt_already_encrypted_noop(self):
        """encrypt_google_token on already-encrypted row returns False."""
        expiration = datetime.now(timezone.utc) + timedelta(days=7)
        token = self.ds.create_session(self.user_id, {"t": "1"}, expiration, encryption_key=self.key)

        result = self.ds.encrypt_google_token(token, self.key)
        self.assertFalse(result)

    def test_decrypt_already_plaintext_noop(self):
        """decrypt_google_token on plaintext row returns False."""
        expiration = datetime.now(timezone.utc) + timedelta(days=7)
        token = self.ds.create_session(self.user_id, {"t": "1"}, expiration)

        result = self.ds.decrypt_google_token(token, self.key)
        self.assertFalse(result)

    def test_encryption_version_column_exists(self):
        """Ensure the encryption_version column was created."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(sessions)")
        columns = [row[1] for row in cursor.fetchall()]
        conn.close()
        self.assertIn('encryption_version', columns)


if __name__ == '__main__':
    unittest.main()

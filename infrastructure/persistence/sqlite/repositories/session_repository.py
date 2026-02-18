"""
SQLite implementation for session management.

Stores user sessions with:
- user_id (TEXT) - Google user email or ID
- session_token (TEXT PRIMARY KEY) - Unique session identifier
- session_token_expiration (TEXT) - ISO format expiration datetime
- google_token (TEXT) - JSON-encoded Google OAuth token
- created_at (TEXT) - Session creation timestamp
- encryption_version (INTEGER) - 0=plaintext, 1=encrypted
"""

import binascii
import json
import logging
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Dict, Optional

from cryptography.exceptions import InvalidTag

from domain.entities.session import Session
from domain.repositories.session_repository import SessionRepository
from infrastructure.crypto.encryption import decrypt_field, encrypt_field
from infrastructure.db_query_logger import get_logging_cursor

logger = logging.getLogger(__name__)


class SQLiteSessionDataSource(SessionRepository):
    """SQLite-based session storage implementation."""

    def __init__(self, db_filepath: str):
        """
        Initialize SQLite session datasource.

        Args:
            db_filepath: Path to the SQLite database file
        """
        self.db_filepath = db_filepath
        self._ensure_table_exists()

    def _ensure_table_exists(self):
        """Create sessions table if it doesn't exist."""
        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                session_token_expiration TEXT NOT NULL,
                google_token TEXT NOT NULL,
                created_at TEXT NOT NULL,
                encryption_version INTEGER NOT NULL DEFAULT 0
            )
        """)

        # Create index on user_id for faster user session lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_session_user_id ON sessions(user_id)
        """)

        # Create index on expiration for cleanup queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_session_expiration ON sessions(session_token_expiration)
        """)

        # Add encryption_version column if missing (for existing databases)
        cursor.execute("PRAGMA table_info(sessions)")
        columns = [row[1] for row in cursor.fetchall()]
        if "encryption_version" not in columns:
            cursor.execute("""
                ALTER TABLE sessions
                ADD COLUMN encryption_version INTEGER NOT NULL DEFAULT 0
            """)

        conn.commit()
        conn.close()

    def _format_datetime(self, dt: datetime) -> str:
        """Format datetime object for storage as ISO 8601 UTC."""
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc)
        # Return ISO 8601 format with Z suffix
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    def _parse_datetime(self, dt_str: str) -> datetime:
        """
        Parse datetime string from storage (assumed to be UTC).
        Expects ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ
        """
        dt_str_clean = dt_str.rstrip("Z")
        dt = datetime.fromisoformat(dt_str_clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    def create_session(
        self,
        user_id: str,
        google_token: Dict,
        expiration: datetime,
        encryption_key: Optional[str] = None,
    ) -> str:
        """
        Create a new session for a user.

        Args:
            user_id: User identifier (email or Google ID)
            google_token: Google OAuth token dictionary
            expiration: Session expiration datetime
            encryption_key: Optional base64-encoded key to encrypt google_token

        Returns:
            Session token string
        """
        # Generate secure random session token
        session_token = secrets.token_urlsafe(32)

        token_json = json.dumps(google_token)
        if encryption_key:
            token_value = encrypt_field(token_json, encryption_key)
            enc_version = 1
        else:
            token_value = token_json
            enc_version = 0

        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute(
                """
                INSERT INTO sessions (session_token, user_id, session_token_expiration, google_token, created_at, encryption_version)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    session_token,
                    user_id,
                    self._format_datetime(expiration),
                    token_value,
                    self._format_datetime(datetime.now(timezone.utc)),
                    enc_version,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        return session_token

    def get_session(
        self, session_token: str, encryption_key: Optional[str] = None
    ) -> Optional[Session]:
        """
        Get session data by token.

        Args:
            session_token: Session token to lookup
            encryption_key: Optional key to decrypt google_token

        Returns:
            Session object or None if not found/expired
        """
        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        cursor.execute(
            """
            SELECT user_id, session_token_expiration, google_token, created_at, encryption_version
            FROM sessions
            WHERE session_token = ?
        """,
            (session_token,),
        )

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        expiration = self._parse_datetime(row[1])

        # Check if session is expired
        if expiration < datetime.now(timezone.utc):
            # Clean up expired session
            self.delete_session(session_token)
            return None

        user_id = row[0]
        enc_version = row[4] if len(row) > 4 else 0

        if enc_version > 0 and encryption_key:
            try:
                token_json = decrypt_field(str(row[2]), encryption_key)
                google_token = json.loads(token_json)
            except (InvalidTag, ValueError, binascii.Error) as e:
                logger.warning("Failed to decrypt google_token: %s", e)
                google_token = {"user_name": user_id, "user_picture": ""}
        elif enc_version > 0:
            # Encrypted but no key — return fallback with user_id as name
            google_token = {"user_name": user_id, "user_picture": ""}
        else:
            google_token = json.loads(row[2])

        return Session(
            session_token=session_token,
            user_id=user_id,
            expiration=expiration,
            google_token=google_token,
            created_at=self._parse_datetime(row[3]),
        )

    def delete_session(self, session_token: str) -> bool:
        """
        Delete a session.

        Args:
            session_token: Session token to delete

        Returns:
            True if session was deleted, False otherwise
        """
        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute("DELETE FROM sessions WHERE session_token = ?", (session_token,))
            conn.commit()
            deleted = cursor.rowcount > 0
        finally:
            conn.close()

        return deleted

    def delete_user_sessions(self, user_id: str) -> int:
        """
        Delete all sessions for a user.

        Args:
            user_id: User identifier

        Returns:
            Number of sessions deleted
        """
        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            conn.commit()
            deleted = cursor.rowcount
        finally:
            conn.close()

        return deleted

    def cleanup_expired_sessions(self) -> int:
        """
        Delete all expired sessions.

        Returns:
            Number of sessions deleted
        """
        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute(
                "DELETE FROM sessions WHERE session_token_expiration < ?",
                (self._format_datetime(datetime.now(timezone.utc)),),
            )
            conn.commit()
            deleted = cursor.rowcount
        finally:
            conn.close()

        return deleted

    def update_session_expiration(self, session_token: str, new_expiration: datetime) -> bool:
        """
        Update session expiration time.

        Args:
            session_token: Session token to update
            new_expiration: New expiration datetime

        Returns:
            True if updated, False otherwise
        """
        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute(
                """
                UPDATE sessions
                SET session_token_expiration = ?
                WHERE session_token = ?
            """,
                (self._format_datetime(new_expiration), session_token),
            )
            conn.commit()
            updated = cursor.rowcount > 0
        finally:
            conn.close()

        return updated

    def update_google_token(
        self, session_token: str, google_token: Dict, encryption_key: Optional[str] = None
    ) -> bool:
        """
        Update the Google OAuth token for a session (e.g., after token refresh).

        Args:
            session_token: Session token to update
            google_token: New Google token dictionary
            encryption_key: Optional key to encrypt the token

        Returns:
            True if updated, False otherwise
        """
        token_json = json.dumps(google_token)
        if encryption_key:
            token_value = encrypt_field(token_json, encryption_key)
            enc_version = 1
        else:
            token_value = token_json
            enc_version = 0

        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute(
                """
                UPDATE sessions
                SET google_token = ?, encryption_version = ?
                WHERE session_token = ?
            """,
                (token_value, enc_version, session_token),
            )
            conn.commit()
            updated = cursor.rowcount > 0
        finally:
            conn.close()

        return updated

    def encrypt_google_token(self, session_token: str, encryption_key: str) -> bool:
        """
        Encrypt an existing plaintext google_token in-place.

        Args:
            session_token: Session token to update
            encryption_key: Base64-encoded encryption key

        Returns:
            True if encrypted, False otherwise
        """
        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute(
                """
                SELECT google_token, encryption_version
                FROM sessions
                WHERE session_token = ?
            """,
                (session_token,),
            )
            row = cursor.fetchone()
            if not row or row[1] != 0:
                return False

            encrypted_token = encrypt_field(row[0], encryption_key)
            cursor.execute(
                """
                UPDATE sessions
                SET google_token = ?, encryption_version = 1
                WHERE session_token = ?
            """,
                (encrypted_token, session_token),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def decrypt_google_token(self, session_token: str, encryption_key: str) -> bool:
        """
        Decrypt an encrypted google_token back to plaintext.

        Args:
            session_token: Session token to update
            encryption_key: Base64-encoded encryption key (needed to decrypt)

        Returns:
            True if decrypted, False otherwise
        """
        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute(
                """
                SELECT google_token, encryption_version
                FROM sessions
                WHERE session_token = ?
            """,
                (session_token,),
            )
            row = cursor.fetchone()
            if not row or row[1] != 1:
                return False

            try:
                plaintext_json = decrypt_field(str(row[0]), encryption_key)
            except (InvalidTag, ValueError, binascii.Error) as e:
                logger.warning("Failed to decrypt google_token for migration: %s", e)
                return False

            cursor.execute(
                """
                UPDATE sessions
                SET google_token = ?, encryption_version = 0
                WHERE session_token = ?
            """,
                (plaintext_json, session_token),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

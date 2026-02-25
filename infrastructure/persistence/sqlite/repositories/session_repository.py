"""
SQLite implementation for session management.

Stores user sessions with:
- user_id (TEXT) - Google user email or ID
- session_token (TEXT PRIMARY KEY) - Unique session identifier
- session_token_expiration (TEXT) - ISO format expiration datetime
- user_profile (TEXT) - JSON: {"user_name": "...", "user_picture": "..."}
- created_at (TEXT) - Session creation timestamp
"""

import json
import logging
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Dict, Optional

from domain.entities.session import Session
from domain.repositories.session_repository import SessionRepository
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
                user_profile TEXT NOT NULL,
                created_at TEXT NOT NULL
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
        user_profile: Dict,
        expiration: datetime,
    ) -> str:
        """
        Create a new session for a user.

        Args:
            user_id: User identifier (email or Google ID)
            user_profile: User profile dict with user_name and user_picture
            expiration: Session expiration datetime

        Returns:
            Session token string
        """
        # Generate secure random session token
        session_token = secrets.token_urlsafe(32)

        profile_json = json.dumps(user_profile)

        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute(
                """
                INSERT INTO sessions (session_token, user_id, session_token_expiration, user_profile, created_at)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    session_token,
                    user_id,
                    self._format_datetime(expiration),
                    profile_json,
                    self._format_datetime(datetime.now(timezone.utc)),
                ),
            )
            conn.commit()
        finally:
            conn.close()

        return session_token

    def get_session(self, session_token: str) -> Optional[Session]:
        """
        Get session data by token.

        Args:
            session_token: Session token to lookup

        Returns:
            Session object or None if not found/expired
        """
        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        cursor.execute(
            """
            SELECT user_id, session_token_expiration, user_profile, created_at
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
        user_profile = json.loads(row[2])

        return Session(
            session_token=session_token,
            user_id=user_id,
            expiration=expiration,
            user_profile=user_profile,
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

"""
SQLite implementation for user settings storage.

Maps between UserSettings entity (with business-friendly field names like 'language')
and database columns (like 'display_language').
"""

import json
import sqlite3
from datetime import datetime, timezone
from typing import Tuple
from infrastructure.db_query_logger import get_logging_cursor
from domain.entities.user_settings import UserSettings, get_default_settings
from domain.repositories.user_settings_repository import UserSettingsRepository


class SQLiteUserSettingsDataSource(UserSettingsRepository):
    """SQLite datasource for user settings. Maps between DB and UserSettings entity."""

    def __init__(self, db_path: str, user_id: str):
        """
        Initialize SQLite user settings datasource.

        Args:
            db_path: Path to the SQLite database file
            user_id: User ID for multi-tenancy filtering
        """
        self.db_path = db_path
        self.user_id = user_id
        self._ensure_table_exists()

    def _ensure_table_exists(self):
        """Create user_settings table if it doesn't exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id TEXT PRIMARY KEY,
                display_language TEXT NOT NULL DEFAULT 'en',
                default_currency TEXT NOT NULL DEFAULT 'USD',
                browser_settings TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')

        # Create index on user_id for faster lookups (though PRIMARY KEY already indexes)
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_user_settings_user_id ON user_settings(user_id)
        ''')

        # Add llm_call_timestamps column if it doesn't exist
        cursor.execute("PRAGMA table_info(user_settings)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'llm_call_timestamps' not in columns:
            cursor.execute('''
                ALTER TABLE user_settings ADD COLUMN llm_call_timestamps TEXT DEFAULT '[]'
            ''')

        conn.commit()
        conn.close()

    def _format_datetime(self, dt: datetime) -> str:
        """Format datetime object for storage as ISO 8601 UTC."""
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc)
        # Return ISO 8601 format with Z suffix
        return dt.strftime('%Y-%m-%dT%H:%M:%SZ')

    def _parse_datetime(self, dt_str: str) -> datetime:
        """
        Parse datetime string from storage (assumed to be UTC).
        Expects ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ
        """
        dt_str_clean = dt_str.rstrip('Z')
        dt = datetime.fromisoformat(dt_str_clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    def _row_to_settings(self, row: tuple) -> UserSettings:
        """
        Convert database row to UserSettings entity.
        Maps: display_language -> language, default_currency -> currency

        Args:
            row: Database row tuple with columns:
                (user_id, display_language, default_currency, created_at, updated_at, browser_settings, llm_call_timestamps)

        Returns:
            UserSettings entity
        """
        # Parse browser_settings JSON (default to empty dict if None or invalid)
        browser_settings = {}
        if len(row) > 5 and row[5]:
            try:
                browser_settings = json.loads(row[5])
            except (json.JSONDecodeError, TypeError):
                browser_settings = {}

        # Parse llm_call_timestamps JSON (default to empty list if None or invalid)
        llm_call_timestamps = []
        if len(row) > 6 and row[6]:
            try:
                timestamps_raw = json.loads(row[6])
                llm_call_timestamps = [self._parse_datetime(ts) for ts in timestamps_raw]
            except (json.JSONDecodeError, TypeError):
                llm_call_timestamps = []

        return UserSettings(
            user_id=row[0],
            language=row[1],        # DB: display_language -> Entity: language
            currency=row[2],        # DB: default_currency -> Entity: currency
            browser_settings=browser_settings,
            llm_call_timestamps=llm_call_timestamps,
            created_at=self._parse_datetime(row[3]),
            updated_at=self._parse_datetime(row[4])
        )

    def get_settings(self) -> UserSettings:
        """
        Get user settings entity.

        Returns defaults if no record exists for this user.

        Returns:
            UserSettings entity with current or default values
        """
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        cursor.execute('''
            SELECT user_id, display_language, default_currency, created_at, updated_at, browser_settings, llm_call_timestamps
            FROM user_settings
            WHERE user_id = ?
        ''', (self.user_id,))

        row = cursor.fetchone()
        conn.close()

        if row:
            return self._row_to_settings(row)
        else:
            return get_default_settings(self.user_id)

    def update_settings(self, settings: UserSettings) -> Tuple[bool, str]:
        """
        Update user settings entity.
        Maps entity fields to DB columns before storing.

        Args:
            settings: UserSettings entity to save

        Returns:
            Tuple of (success: bool, error_message: str)
        """
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            now = self._format_datetime(datetime.now(timezone.utc))

            # Serialize browser_settings to JSON
            browser_settings_json = json.dumps(settings.browser_settings or {})

            # Serialize llm_call_timestamps to JSON (list of ISO 8601 strings)
            llm_timestamps_json = json.dumps([
                self._format_datetime(ts) for ts in (settings.llm_call_timestamps or [])
            ])

            # Check if settings exist
            cursor.execute('SELECT 1 FROM user_settings WHERE user_id = ?', (self.user_id,))
            exists = cursor.fetchone() is not None

            if exists:
                # UPDATE existing settings
                cursor.execute('''
                    UPDATE user_settings
                    SET display_language = ?, default_currency = ?, browser_settings = ?, llm_call_timestamps = ?, updated_at = ?
                    WHERE user_id = ?
                ''', (settings.language, settings.currency, browser_settings_json, llm_timestamps_json, now, self.user_id))
            else:
                # INSERT new settings
                cursor.execute('''
                    INSERT INTO user_settings
                    (user_id, display_language, default_currency, browser_settings, llm_call_timestamps, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (self.user_id, settings.language, settings.currency, browser_settings_json, llm_timestamps_json, now, now))

            conn.commit()
            return True, ""
        except sqlite3.Error as e:
            conn.rollback()
            return False, str(e)
        finally:
            conn.close()

    def get_llm_call_timestamps(self) -> list:
        """
        Get LLM call timestamps for the current user.

        Returns:
            List of datetime objects representing when LLM calls were made
        """
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        cursor.execute('''
            SELECT llm_call_timestamps
            FROM user_settings
            WHERE user_id = ?
        ''', (self.user_id,))

        row = cursor.fetchone()
        conn.close()

        if row and row[0]:
            try:
                timestamps_raw = json.loads(row[0])
                return [self._parse_datetime(ts) for ts in timestamps_raw]
            except (json.JSONDecodeError, TypeError):
                return []
        return []

    def update_llm_call_timestamps(self, timestamps: list) -> bool:
        """
        Update LLM call timestamps for the current user.

        Args:
            timestamps: List of datetime objects to store

        Returns:
            True if update was successful, False otherwise
        """
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            now = self._format_datetime(datetime.now(timezone.utc))

            # Serialize timestamps to JSON
            timestamps_json = json.dumps([
                self._format_datetime(ts) for ts in timestamps
            ])

            # Check if settings exist
            cursor.execute('SELECT 1 FROM user_settings WHERE user_id = ?', (self.user_id,))
            exists = cursor.fetchone() is not None

            if exists:
                cursor.execute('''
                    UPDATE user_settings
                    SET llm_call_timestamps = ?, updated_at = ?
                    WHERE user_id = ?
                ''', (timestamps_json, now, self.user_id))
            else:
                # Create a new record with default values
                cursor.execute('''
                    INSERT INTO user_settings
                    (user_id, display_language, default_currency, browser_settings, llm_call_timestamps, created_at, updated_at)
                    VALUES (?, 'en', 'USD', '{}', ?, ?, ?)
                ''', (self.user_id, timestamps_json, now, now))

            conn.commit()
            return True
        except sqlite3.Error:
            conn.rollback()
            return False
        finally:
            conn.close()

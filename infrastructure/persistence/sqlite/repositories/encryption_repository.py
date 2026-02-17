"""
SQLite repository for encryption keys and WebAuthn credentials.

Manages two tables:
- encryption_keys: Wrapped DEKs per user/credential pair
- webauthn_credentials: WebAuthn credential storage for passkey authentication
"""

import sqlite3
from datetime import datetime, timezone
from typing import List, Optional

from domain.repositories.encryption_repository import EncryptionRepository
from infrastructure.db_query_logger import get_logging_cursor


class SQLiteEncryptionRepository(EncryptionRepository):
    """Manages encryption_keys and webauthn_credentials tables."""

    def __init__(self, db_filepath: str):
        self.db_filepath = db_filepath
        self._ensure_table_exists()

    def _ensure_table_exists(self):
        """Create encryption_keys and webauthn_credentials tables if they don't exist."""
        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS encryption_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                credential_id TEXT NOT NULL,
                wrapped_dek BLOB NOT NULL,
                prf_salt TEXT NOT NULL,
                wrapper_type TEXT DEFAULT 'prf',
                created_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_encryption_keys_user_credential
            ON encryption_keys (user_id, credential_id)
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS webauthn_credentials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                credential_id TEXT NOT NULL UNIQUE,
                public_key BLOB NOT NULL,
                sign_count INTEGER DEFAULT 0,
                device_name TEXT,
                created_at TEXT NOT NULL
            )
        """)

        conn.commit()
        conn.close()

    # =========================================================================
    # Encryption keys (wrapped DEKs)
    # =========================================================================

    def store_wrapped_dek(
        self,
        user_id: str,
        credential_id: str,
        wrapped_dek: bytes,
        prf_salt: str,
        wrapper_type: str = "prf",
    ) -> None:
        """Store a wrapped DEK for a user/credential pair."""
        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        cursor.execute(
            """
            INSERT INTO encryption_keys (user_id, credential_id, wrapped_dek, prf_salt, wrapper_type, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (user_id, credential_id, wrapped_dek, prf_salt, wrapper_type, now),
        )

        conn.commit()
        conn.close()

    def get_wrapped_dek(self, user_id: str, credential_id: str) -> Optional[bytes]:
        """Get the wrapped DEK for a specific user/credential pair."""
        conn = sqlite3.connect(self.db_filepath)
        conn.row_factory = sqlite3.Row
        cursor = get_logging_cursor(conn)

        cursor.execute(
            """
            SELECT wrapped_dek FROM encryption_keys
            WHERE user_id = ? AND credential_id = ?
        """,
            (user_id, credential_id),
        )

        row = cursor.fetchone()
        conn.close()
        return bytes(row["wrapped_dek"]) if row else None

    def get_wrapped_deks_for_user(self, user_id: str) -> List[dict]:
        """Get all wrapped DEKs for a user."""
        conn = sqlite3.connect(self.db_filepath)
        conn.row_factory = sqlite3.Row
        cursor = get_logging_cursor(conn)

        cursor.execute(
            """
            SELECT credential_id, wrapped_dek, prf_salt, wrapper_type, created_at
            FROM encryption_keys WHERE user_id = ?
        """,
            (user_id,),
        )

        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def delete_wrapped_dek(self, user_id: str, credential_id: str) -> None:
        """Delete a wrapped DEK for a user/credential pair."""
        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        cursor.execute(
            """
            DELETE FROM encryption_keys WHERE user_id = ? AND credential_id = ?
        """,
            (user_id, credential_id),
        )

        conn.commit()
        conn.close()

    def get_prf_salt(self, user_id: str, credential_id: str) -> Optional[str]:
        """Get the PRF salt for a user/credential pair."""
        conn = sqlite3.connect(self.db_filepath)
        conn.row_factory = sqlite3.Row
        cursor = get_logging_cursor(conn)

        cursor.execute(
            """
            SELECT prf_salt FROM encryption_keys
            WHERE user_id = ? AND credential_id = ?
        """,
            (user_id, credential_id),
        )

        row = cursor.fetchone()
        conn.close()
        return row["prf_salt"] if row else None

    # =========================================================================
    # WebAuthn credentials
    # =========================================================================

    def store_credential(
        self,
        user_id: str,
        credential_id: str,
        public_key: bytes,
        sign_count: int,
        device_name: Optional[str] = None,
    ) -> None:
        """Store a WebAuthn credential."""
        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        cursor.execute(
            """
            INSERT INTO webauthn_credentials
            (user_id, credential_id, public_key, sign_count, device_name, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (user_id, credential_id, public_key, sign_count, device_name, now),
        )

        conn.commit()
        conn.close()

    def get_credential(self, credential_id: str) -> Optional[dict]:
        """Get a WebAuthn credential by credential_id."""
        conn = sqlite3.connect(self.db_filepath)
        conn.row_factory = sqlite3.Row
        cursor = get_logging_cursor(conn)

        cursor.execute(
            """
            SELECT user_id, credential_id, public_key, sign_count, device_name, created_at
            FROM webauthn_credentials WHERE credential_id = ?
        """,
            (credential_id,),
        )

        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_credentials_for_user(self, user_id: str) -> List[dict]:
        """Get all WebAuthn credentials for a user."""
        conn = sqlite3.connect(self.db_filepath)
        conn.row_factory = sqlite3.Row
        cursor = get_logging_cursor(conn)

        cursor.execute(
            """
            SELECT credential_id, public_key, sign_count, device_name, created_at
            FROM webauthn_credentials WHERE user_id = ?
        """,
            (user_id,),
        )

        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def update_sign_count(self, credential_id: str, sign_count: int) -> None:
        """Update the sign count for a credential after authentication."""
        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        cursor.execute(
            """
            UPDATE webauthn_credentials SET sign_count = ? WHERE credential_id = ?
        """,
            (sign_count, credential_id),
        )

        conn.commit()
        conn.close()

    def delete_credential(self, credential_id: str) -> None:
        """Delete a WebAuthn credential."""
        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        cursor.execute(
            """
            DELETE FROM webauthn_credentials WHERE credential_id = ?
        """,
            (credential_id,),
        )

        conn.commit()
        conn.close()

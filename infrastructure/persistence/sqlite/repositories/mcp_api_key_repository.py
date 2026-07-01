"""SQLite implementation of the MCP API key repository."""
from typing import List, Optional

from domain.repositories.mcp_api_key_repository import MCPApiKeyRepository
from infrastructure.persistence.sqlite.connection import get_connection


class SQLiteMCPApiKeyRepository(MCPApiKeyRepository):
    def __init__(self, db_filepath: str):
        self.db_filepath = db_filepath
        self._ensure_table()

    def _ensure_table(self) -> None:
        conn = get_connection(self.db_filepath)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mcp_api_keys (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    scope TEXT NOT NULL,
                    label TEXT,
                    created_at TEXT NOT NULL,
                    expires_at TEXT,
                    last_used_at TEXT,
                    revoked INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_mcp_api_keys_token_hash "
                "ON mcp_api_keys(token_hash)"
            )
            conn.commit()
        finally:
            conn.close()

    def create(self, key_id: str, user_id: str, token_hash: str, scope: str,
               label: str, created_at: str, expires_at: Optional[str]) -> None:
        conn = get_connection(self.db_filepath)
        try:
            conn.execute(
                "INSERT INTO mcp_api_keys "
                "(id, user_id, token_hash, scope, label, created_at, expires_at, revoked) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
                (key_id, user_id, token_hash, scope, label, created_at, expires_at),
            )
            conn.commit()
        finally:
            conn.close()

    def _row_to_dict(self, row) -> dict:
        return {
            "id": row[0], "user_id": row[1], "token_hash": row[2], "scope": row[3],
            "label": row[4], "created_at": row[5], "expires_at": row[6],
            "last_used_at": row[7], "revoked": row[8],
        }

    def get_by_token_hash(self, token_hash: str) -> Optional[dict]:
        conn = get_connection(self.db_filepath)
        try:
            row = conn.execute(
                "SELECT id, user_id, token_hash, scope, label, created_at, "
                "expires_at, last_used_at, revoked FROM mcp_api_keys WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
            return self._row_to_dict(row) if row else None
        finally:
            conn.close()

    def list_for_user(self, user_id: str) -> List[dict]:
        conn = get_connection(self.db_filepath)
        try:
            rows = conn.execute(
                "SELECT id, user_id, token_hash, scope, label, created_at, "
                "expires_at, last_used_at, revoked FROM mcp_api_keys "
                "WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def touch_last_used(self, key_id: str, when_iso: str) -> None:
        conn = get_connection(self.db_filepath)
        try:
            conn.execute(
                "UPDATE mcp_api_keys SET last_used_at = ? WHERE id = ?",
                (when_iso, key_id),
            )
            conn.commit()
        finally:
            conn.close()

    def revoke(self, user_id: str, key_id: str) -> bool:
        conn = get_connection(self.db_filepath)
        try:
            cur = conn.execute(
                "UPDATE mcp_api_keys SET revoked = 1 WHERE id = ? AND user_id = ?",
                (key_id, user_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

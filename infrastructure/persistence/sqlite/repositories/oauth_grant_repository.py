"""SQLite implementation of the OAuth grant repository (access/refresh token pairs)."""
from typing import Optional

from domain.repositories.oauth_repository import OAuthGrantRepository
from infrastructure.persistence.sqlite.connection import get_connection

_SELECT_COLUMNS = (
    "grant_id, user_id, client_id, scope, at_hash, at_salt, at_expires_at, "
    "rt_hash, rt_salt, rt_expires_at, prev_rt_hash, prev_rt_expires_at, "
    "revoked, created_at"
)


class SQLiteOAuthGrantRepository(OAuthGrantRepository):
    def __init__(self, db_filepath: str):
        self.db_filepath = db_filepath
        self._ensure_table()

    def _ensure_table(self) -> None:
        conn = get_connection(self.db_filepath)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS oauth_grants (
                    grant_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    client_id TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    at_hash TEXT NOT NULL,
                    at_salt TEXT NOT NULL,
                    at_expires_at TEXT NOT NULL,
                    rt_hash TEXT NOT NULL,
                    rt_salt TEXT NOT NULL,
                    rt_expires_at TEXT NOT NULL,
                    prev_rt_hash TEXT,
                    prev_rt_expires_at TEXT,
                    revoked INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_oauth_grants_at ON oauth_grants(at_hash)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_oauth_grants_rt ON oauth_grants(rt_hash)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_oauth_grants_prev_rt "
                "ON oauth_grants(prev_rt_hash)"
            )
            conn.commit()
        finally:
            conn.close()

    def create(self, grant_id: str, user_id: str, client_id: str, scope: str,
               at_hash: str, at_salt: str, at_expires_at: str,
               rt_hash: str, rt_salt: str, rt_expires_at: str,
               created_at: str) -> None:
        conn = get_connection(self.db_filepath)
        try:
            conn.execute(
                "INSERT INTO oauth_grants "
                "(grant_id, user_id, client_id, scope, at_hash, at_salt, at_expires_at, "
                "rt_hash, rt_salt, rt_expires_at, prev_rt_hash, prev_rt_expires_at, "
                "revoked, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, 0, ?)",
                (grant_id, user_id, client_id, scope, at_hash, at_salt, at_expires_at,
                 rt_hash, rt_salt, rt_expires_at, created_at),
            )
            conn.commit()
        finally:
            conn.close()

    def _row_to_dict(self, row) -> dict:
        return {
            "grant_id": row[0],
            "user_id": row[1],
            "client_id": row[2],
            "scope": row[3],
            "at_hash": row[4],
            "at_salt": row[5],
            "at_expires_at": row[6],
            "rt_hash": row[7],
            "rt_salt": row[8],
            "rt_expires_at": row[9],
            "prev_rt_hash": row[10],
            "prev_rt_expires_at": row[11],
            "revoked": row[12],
            "created_at": row[13],
        }

    def get_by_at_hash(self, at_hash: str) -> Optional[dict]:
        conn = get_connection(self.db_filepath)
        try:
            row = conn.execute(
                f"SELECT {_SELECT_COLUMNS} FROM oauth_grants "
                "WHERE at_hash = ? AND revoked = 0",
                (at_hash,),
            ).fetchone()
            return self._row_to_dict(row) if row else None
        finally:
            conn.close()

    def get_by_rt_hash(self, rt_hash: str) -> Optional[dict]:
        conn = get_connection(self.db_filepath)
        try:
            row = conn.execute(
                f"SELECT {_SELECT_COLUMNS} FROM oauth_grants "
                "WHERE revoked = 0 AND (rt_hash = ? OR prev_rt_hash = ?)",
                (rt_hash, rt_hash),
            ).fetchone()
            return self._row_to_dict(row) if row else None
        finally:
            conn.close()

    def rotate(self, grant_id: str, at_hash: str, at_salt: str, at_expires_at: str,
               rt_hash: str, rt_salt: str, rt_expires_at: str,
               prev_rt_hash: str, prev_rt_expires_at: str) -> None:
        conn = get_connection(self.db_filepath)
        try:
            conn.execute(
                "UPDATE oauth_grants SET "
                "at_hash = ?, at_salt = ?, at_expires_at = ?, "
                "rt_hash = ?, rt_salt = ?, rt_expires_at = ?, "
                "prev_rt_hash = ?, prev_rt_expires_at = ? "
                "WHERE grant_id = ?",
                (at_hash, at_salt, at_expires_at, rt_hash, rt_salt, rt_expires_at,
                 prev_rt_hash, prev_rt_expires_at, grant_id),
            )
            conn.commit()
        finally:
            conn.close()

    def revoke_by_grant_id(self, grant_id: str) -> None:
        conn = get_connection(self.db_filepath)
        try:
            conn.execute(
                "UPDATE oauth_grants SET revoked = 1 WHERE grant_id = ?",
                (grant_id,),
            )
            conn.commit()
        finally:
            conn.close()

    def revoke_by_at_hash(self, at_hash: str) -> None:
        conn = get_connection(self.db_filepath)
        try:
            conn.execute(
                "UPDATE oauth_grants SET revoked = 1 WHERE at_hash = ?",
                (at_hash,),
            )
            conn.commit()
        finally:
            conn.close()

    def revoke_by_rt_hash(self, rt_hash: str) -> None:
        conn = get_connection(self.db_filepath)
        try:
            conn.execute(
                "UPDATE oauth_grants SET revoked = 1 "
                "WHERE rt_hash = ? OR prev_rt_hash = ?",
                (rt_hash, rt_hash),
            )
            conn.commit()
        finally:
            conn.close()

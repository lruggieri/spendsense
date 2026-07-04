"""SQLite implementation of the OAuth authorization repository (pending auth + codes)."""
from typing import Optional

from domain.repositories.oauth_repository import OAuthAuthorizationRepository
from infrastructure.persistence.sqlite.connection import get_connection


class SQLiteOAuthAuthorizationRepository(OAuthAuthorizationRepository):
    def __init__(self, db_filepath: str):
        self.db_filepath = db_filepath
        self._ensure_table()

    def _ensure_table(self) -> None:
        conn = get_connection(self.db_filepath)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS oauth_pending_auth (
                    txn_id TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL,
                    params TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS oauth_codes (
                    code_hash TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    scopes TEXT NOT NULL,
                    code_challenge TEXT NOT NULL,
                    redirect_uri TEXT NOT NULL,
                    redirect_uri_explicit INTEGER NOT NULL,
                    resource TEXT,
                    expires_at TEXT NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    # -- pending authorization transactions --

    def create_pending(self, txn_id: str, client_id: str, params_json: str,
                        created_at: str, expires_at: str) -> None:
        conn = get_connection(self.db_filepath)
        try:
            conn.execute(
                "INSERT INTO oauth_pending_auth "
                "(txn_id, client_id, params, created_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (txn_id, client_id, params_json, created_at, expires_at),
            )
            conn.commit()
        finally:
            conn.close()

    def _pending_row_to_dict(self, row) -> dict:
        return {
            "txn_id": row[0],
            "client_id": row[1],
            "params": row[2],
            "created_at": row[3],
            "expires_at": row[4],
        }

    def get_pending(self, txn_id: str) -> Optional[dict]:
        conn = get_connection(self.db_filepath)
        try:
            row = conn.execute(
                "SELECT txn_id, client_id, params, created_at, expires_at "
                "FROM oauth_pending_auth WHERE txn_id = ?",
                (txn_id,),
            ).fetchone()
            return self._pending_row_to_dict(row) if row else None
        finally:
            conn.close()

    def delete_pending(self, txn_id: str) -> None:
        conn = get_connection(self.db_filepath)
        try:
            conn.execute("DELETE FROM oauth_pending_auth WHERE txn_id = ?", (txn_id,))
            conn.commit()
        finally:
            conn.close()

    # -- authorization codes --

    def create_code(self, code_hash: str, client_id: str, user_id: str, scopes_json: str,
                     code_challenge: str, redirect_uri: str, redirect_uri_explicit: int,
                     resource: Optional[str], expires_at: str) -> None:
        conn = get_connection(self.db_filepath)
        try:
            conn.execute(
                "INSERT INTO oauth_codes "
                "(code_hash, client_id, user_id, scopes, code_challenge, redirect_uri, "
                "redirect_uri_explicit, resource, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (code_hash, client_id, user_id, scopes_json, code_challenge, redirect_uri,
                 redirect_uri_explicit, resource, expires_at),
            )
            conn.commit()
        finally:
            conn.close()

    def _code_row_to_dict(self, row) -> dict:
        return {
            "code_hash": row[0],
            "client_id": row[1],
            "user_id": row[2],
            "scopes": row[3],
            "code_challenge": row[4],
            "redirect_uri": row[5],
            "redirect_uri_explicit": row[6],
            "resource": row[7],
            "expires_at": row[8],
        }

    def get_code(self, code_hash: str) -> Optional[dict]:
        conn = get_connection(self.db_filepath)
        try:
            row = conn.execute(
                "SELECT code_hash, client_id, user_id, scopes, code_challenge, redirect_uri, "
                "redirect_uri_explicit, resource, expires_at "
                "FROM oauth_codes WHERE code_hash = ?",
                (code_hash,),
            ).fetchone()
            return self._code_row_to_dict(row) if row else None
        finally:
            conn.close()

    def delete_code(self, code_hash: str) -> None:
        conn = get_connection(self.db_filepath)
        try:
            conn.execute("DELETE FROM oauth_codes WHERE code_hash = ?", (code_hash,))
            conn.commit()
        finally:
            conn.close()

"""SQLite implementation of the OAuth client repository."""
import json
from typing import List, Optional

from domain.repositories.oauth_repository import OAuthClientRepository
from infrastructure.persistence.sqlite.connection import get_connection


class SQLiteOAuthClientRepository(OAuthClientRepository):
    def __init__(self, db_filepath: str):
        self.db_filepath = db_filepath
        self._ensure_table()

    def _ensure_table(self) -> None:
        conn = get_connection(self.db_filepath)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS oauth_clients (
                    client_id TEXT PRIMARY KEY,
                    redirect_uris TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def upsert(self, client_id: str, redirect_uris: List[str], metadata_json: str,
               created_at: str) -> None:
        conn = get_connection(self.db_filepath)
        try:
            conn.execute(
                "INSERT INTO oauth_clients (client_id, redirect_uris, metadata, created_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(client_id) DO UPDATE SET "
                "redirect_uris = excluded.redirect_uris, "
                "metadata = excluded.metadata",
                (client_id, json.dumps(redirect_uris), metadata_json, created_at),
            )
            conn.commit()
        finally:
            conn.close()

    def _row_to_dict(self, row) -> dict:
        return {
            "client_id": row[0],
            "redirect_uris": json.loads(row[1]),
            "metadata": row[2],
            "created_at": row[3],
        }

    def get(self, client_id: str) -> Optional[dict]:
        conn = get_connection(self.db_filepath)
        try:
            row = conn.execute(
                "SELECT client_id, redirect_uris, metadata, created_at "
                "FROM oauth_clients WHERE client_id = ?",
                (client_id,),
            ).fetchone()
            return self._row_to_dict(row) if row else None
        finally:
            conn.close()

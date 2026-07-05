"""SQLite implementation of the OAuth grant repository (access/refresh token pairs)."""
from datetime import datetime, timezone
from typing import Optional

from domain.repositories.oauth_repository import OAuthEnvelopeRewrite, OAuthGrantRepository
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
                f"SELECT {_SELECT_COLUMNS} FROM oauth_grants "  # nosec B608 - column list is a fixed constant, not user input
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
                f"SELECT {_SELECT_COLUMNS} FROM oauth_grants "  # nosec B608 - column list is a fixed constant, not user input
                "WHERE revoked = 0 AND (rt_hash = ? OR prev_rt_hash = ?)",
                (rt_hash, rt_hash),
            ).fetchone()
            return self._row_to_dict(row) if row else None
        finally:
            conn.close()

    def rotate(self, grant_id: str, at_hash: str, at_salt: str, at_expires_at: str,
               rt_hash: str, rt_salt: str, rt_expires_at: str,
               prev_rt_hash: str, prev_rt_expires_at: str) -> bool:
        """Single atomic UPDATE, guarded by `rt_hash = prev_rt_hash` (see the
        docstring on the abstract method for why `prev_rt_hash` doubles as an
        optimistic-concurrency check). This is the serialization point for
        concurrent refreshes: only the first of two racing callers that
        observed the same current `rt_hash` can have its UPDATE match a row;
        the second's WHERE clause no longer matches (the row was already
        moved on) and it updates zero rows.
        """
        conn = get_connection(self.db_filepath)
        try:
            cursor = conn.execute(
                "UPDATE oauth_grants SET "
                "at_hash = ?, at_salt = ?, at_expires_at = ?, "
                "rt_hash = ?, rt_salt = ?, rt_expires_at = ?, "
                "prev_rt_hash = ?, prev_rt_expires_at = ? "
                "WHERE grant_id = ? AND rt_hash = ?",
                (at_hash, at_salt, at_expires_at, rt_hash, rt_salt, rt_expires_at,
                 prev_rt_hash, prev_rt_expires_at, grant_id, prev_rt_hash),
            )
            conn.commit()
            return cursor.rowcount == 1
        finally:
            conn.close()

    def rotate_with_envelopes(
        self, grant_id: str, at_hash: str, at_salt: str, at_expires_at: str,
        rt_hash: str, rt_salt: str, rt_expires_at: str,
        prev_rt_hash: str, prev_rt_expires_at: str,
        envelopes: Optional[OAuthEnvelopeRewrite] = None,
    ) -> bool:
        """Cross-process-atomic rotation of the grant row + DEK envelopes.

        This method - not `rotate()` - is what `OAuthService.refresh()` uses.
        `rotate()` alone is safe on its own (a single atomic UPDATE), but the
        DEK envelope rewrite historically happened as several *separate*,
        unprotected reads/writes against `encryption_keys` (the now-removed
        `EncryptionService.oauth_rewrap_for_rotation`), each opening and
        committing its own connection. Two racing processes could interleave
        those envelope writes independently of which one's grants-row CAS
        ultimately "won", producing a live grant row whose envelope no
        longer contains the DEK wrapped under the tokens that row claims are
        current - a silent, unrecoverable-DEK bug, not just an auth failure.

        The fix used here: do EVERYTHING - the grants-table CAS and all
        envelope writes - inside one `BEGIN IMMEDIATE` transaction on one
        connection. `BEGIN IMMEDIATE` acquires SQLite's RESERVED lock
        up front, so a second process's `BEGIN IMMEDIATE` against the same
        file genuinely blocks (until this transaction commits or rolls
        back, or its own `busy_timeout` elapses) rather than being merely a
        best-effort compare-and-swap that a differently-ordered writer could
        still race past. Because the grants-table CAS and the envelope
        writes share this one transaction, there is no way for one process's
        envelope writes to land while a *different* process's grants-row
        update is the one that ends up committed: whichever transaction
        commits first serializes completely (envelopes AND grant row) before
        the second transaction's own CAS re-reads the row and (correctly)
        finds it changed.

        The `encryption_keys` table lives in the same SQLite file as
        `oauth_grants` (both repositories are constructed from the same
        `db_filepath` by `OAuthService`), so a single connection can span
        both without any cross-database coordination. Raw SQL against
        `encryption_keys` is used directly here (mirroring
        `SQLiteEncryptionRepository`'s schema/queries) rather than calling
        through `EncryptionRepository`, because that repository's methods
        each open and commit their own connection - exactly the pattern
        this method exists to avoid.
        """
        conn = get_connection(self.db_filepath)
        try:
            conn.execute("BEGIN IMMEDIATE")

            cursor = conn.execute(
                "UPDATE oauth_grants SET "
                "at_hash = ?, at_salt = ?, at_expires_at = ?, "
                "rt_hash = ?, rt_salt = ?, rt_expires_at = ?, "
                "prev_rt_hash = ?, prev_rt_expires_at = ? "
                "WHERE grant_id = ? AND rt_hash = ?",
                (at_hash, at_salt, at_expires_at, rt_hash, rt_salt, rt_expires_at,
                 prev_rt_hash, prev_rt_expires_at, grant_id, prev_rt_hash),
            )
            if cursor.rowcount != 1:
                # Lost the race (or grant_id/rt_hash simply doesn't match
                # any row): roll back so nothing - not even envelope writes,
                # which haven't happened yet at this point - persists.
                conn.rollback()
                return False

            if envelopes is not None:
                user_id = envelopes.user_id
                created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

                def _replace(credential_id: str, wrapped_dek: bytes, prf_salt: str,
                             wrapper_type: str) -> None:
                    conn.execute(
                        "DELETE FROM encryption_keys "
                        "WHERE user_id = ? AND credential_id = ?",
                        (user_id, credential_id),
                    )
                    conn.execute(
                        "INSERT INTO encryption_keys "
                        "(user_id, credential_id, wrapped_dek, prf_salt, wrapper_type, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (user_id, credential_id, wrapped_dek, prf_salt, wrapper_type, created_at),
                    )

                # Preserve whatever the CURRENT oauthrt envelope is - read
                # fresh, inside this same exclusive transaction, so it
                # reflects the true latest committed state - under ":prev"
                # before it gets overwritten below.
                current_rt = conn.execute(
                    "SELECT wrapped_dek, prf_salt FROM encryption_keys "
                    "WHERE user_id = ? AND credential_id = ?",
                    (user_id, f"oauthrt:{grant_id}"),
                ).fetchone()
                if current_rt is not None:
                    _replace(
                        f"oauthrt:{grant_id}:prev",
                        bytes(current_rt[0]), current_rt[1], "oauth_rt_prev",
                    )

                _replace(
                    f"oauthat:{grant_id}",
                    envelopes.new_at_wrapped, envelopes.new_at_salt_b64, "oauth_at",
                )
                _replace(
                    f"oauthrt:{grant_id}",
                    envelopes.new_rt_wrapped, envelopes.new_rt_salt_b64, "oauth_rt",
                )

            conn.commit()
            return True
        except BaseException:
            conn.rollback()
            raise
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

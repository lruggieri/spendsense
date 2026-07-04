"""Shared SQLite connection factory.

Applies WAL journal mode (persists on the database file) and a per-connection
busy_timeout so concurrent writers wait briefly instead of failing with
"database is locked". Every repository should obtain connections via this helper.
"""

import sqlite3


def get_connection(db_path: str, *, timeout_ms: int = 5000) -> sqlite3.Connection:
    """Open a SQLite connection with WAL mode and a busy timeout."""
    conn = sqlite3.connect(db_path, timeout=timeout_ms / 1000)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(f"PRAGMA busy_timeout={timeout_ms};")
    return conn

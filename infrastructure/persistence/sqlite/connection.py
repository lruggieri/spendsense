"""Shared SQLite connection factory.

Applies WAL journal mode (persists on the database file) and a per-connection
busy_timeout so concurrent writers wait briefly instead of failing with
"database is locked". Every repository should obtain connections via this helper.
"""

import os
import sqlite3


def get_connection(db_path: str, *, timeout_ms: int = 5000) -> sqlite3.Connection:
    """Open a SQLite connection with WAL mode and a busy timeout.

    Creates the parent directory first if it doesn't exist yet - sqlite3
    can't create the db file itself if its containing directory is missing
    (e.g. a fresh checkout with no `data/` dir yet, before anything has
    written to the default database path).
    """
    dirname = os.path.dirname(db_path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=timeout_ms / 1000)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(f"PRAGMA busy_timeout={timeout_ms};")
    return conn

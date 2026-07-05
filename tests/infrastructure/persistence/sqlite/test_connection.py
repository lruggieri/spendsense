import os
import tempfile
from infrastructure.persistence.sqlite.connection import get_connection


def test_get_connection_sets_wal_and_busy_timeout():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        conn = get_connection(path)
        try:
            mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
            busy = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
            assert mode.lower() == "wal"
            assert busy == 5000
        finally:
            conn.close()
    finally:
        os.remove(path)


def test_get_connection_creates_missing_parent_directory():
    """A fresh checkout has no `data/` dir yet - the first connection to the
    default database path must create it rather than raising
    'unable to open database file'."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "nested", "sub", "transactions.db")
        conn = get_connection(db_path)
        try:
            assert os.path.isdir(os.path.dirname(db_path))
            assert os.path.exists(db_path)
        finally:
            conn.close()


def test_get_connection_handles_memory_database():
    conn = get_connection(":memory:")
    try:
        assert conn.execute("SELECT 1").fetchone()[0] == 1
    finally:
        conn.close()

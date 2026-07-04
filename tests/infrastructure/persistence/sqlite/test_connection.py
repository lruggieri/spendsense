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

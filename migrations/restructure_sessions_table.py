"""
Migration: restructure sessions table for client-side Gmail OAuth.

The server no longer stores Gmail OAuth tokens.  The only user data still
needed at the session level is user_name and user_picture for the UI.

Changes:
  - Wipe all existing sessions (users must re-login; new sessions carry no
    OAuth tokens)
  - Rename google_token → user_profile (stores only {user_name, user_picture})
  - Drop encryption_version column (no sensitive data left to encrypt)
"""

import sqlite3
import sys


def run(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. Wipe all existing sessions.
    #    Users must re-login. New sessions will carry no OAuth tokens.
    cursor.execute("DELETE FROM sessions")

    # 2. Recreate sessions table:
    #    - rename google_token → user_profile  (stores only {user_name, user_picture})
    #    - drop encryption_version             (no sensitive data left to encrypt)
    #    SQLite pre-3.35.0 safe approach (recreate table).
    cursor.execute("""
        CREATE TABLE sessions_new (
            session_token            TEXT PRIMARY KEY,
            user_id                  TEXT NOT NULL,
            session_token_expiration TEXT NOT NULL,
            user_profile             TEXT NOT NULL,
            created_at               TEXT NOT NULL
        )
    """)

    # No data to migrate — table was wiped above.
    cursor.execute("DROP TABLE sessions")
    cursor.execute("ALTER TABLE sessions_new RENAME TO sessions")

    # Recreate indexes on the new table
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_user_id ON sessions(user_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_expiration ON sessions(session_token_expiration)"
    )

    conn.commit()
    conn.close()
    print(f"Migration complete: sessions table restructured in {db_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <db_path>")
        sys.exit(1)
    run(sys.argv[1])

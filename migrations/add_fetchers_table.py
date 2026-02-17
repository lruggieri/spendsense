#!/usr/bin/env python3
"""
Migration: Add Fetchers Table

Creates fetchers table for storing user-defined email transaction fetchers.

Usage:
    python3 migrations/add_fetchers_table.py [--database-path PATH]
"""

import sqlite3
import sys
import os
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_database_path


def check_table_exists(cursor: sqlite3.Cursor, table: str) -> bool:
    """Check if a table exists."""
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,)
    )
    return cursor.fetchone() is not None


def migrate(database_path: str) -> None:
    """Run the migration."""
    print(f"Running migration on database: {database_path}")

    if not os.path.exists(database_path):
        print(f"ERROR: Database not found at {database_path}")
        sys.exit(1)

    conn = sqlite3.connect(database_path)
    cursor = conn.cursor()

    try:
        # Start transaction
        cursor.execute("BEGIN TRANSACTION")

        # Check if fetchers table exists
        if check_table_exists(cursor, "fetchers"):
            print("⊘ Table 'fetchers' already exists, skipping")
        else:
            print("Creating 'fetchers' table...")
            cursor.execute("""
                CREATE TABLE fetchers (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    from_emails TEXT NOT NULL,
                    subject_filter TEXT DEFAULT '',
                    amount_pattern TEXT NOT NULL,
                    merchant_pattern TEXT,
                    currency_pattern TEXT,
                    default_currency TEXT DEFAULT 'USD',
                    enabled INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            print("✓ Created 'fetchers' table")

            # Create indexes
            print("Creating indexes...")
            cursor.execute("""
                CREATE INDEX idx_fetchers_user_id ON fetchers(user_id)
            """)
            cursor.execute("""
                CREATE INDEX idx_fetchers_enabled ON fetchers(user_id, enabled)
            """)
            print("✓ Created indexes")

        # Commit transaction
        conn.commit()
        print("\n✓ Migration completed successfully!")

    except Exception as e:
        # Rollback on error
        conn.rollback()
        print(f"\n✗ Migration failed: {e}")
        sys.exit(1)

    finally:
        conn.close()


def main():
    """Main entry point."""
    # Allow custom database path via command line argument
    if len(sys.argv) > 2 and sys.argv[1] == "--database-path":
        database_path = sys.argv[2]
    else:
        database_path = get_database_path()

    print("=" * 60)
    print("Migration: Add Fetchers Table")
    print("=" * 60)
    print()

    migrate(database_path)


if __name__ == "__main__":
    main()

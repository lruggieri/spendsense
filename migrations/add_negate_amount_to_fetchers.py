#!/usr/bin/env python3
"""
Migration: Add negate_amount Column to Fetchers Table

Adds negate_amount column to support income/refund transactions.

Usage:
    python3 migrations/add_negate_amount_to_fetchers.py [--database-path PATH]
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


def check_column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    """Check if a column exists in a table."""
    cursor.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in cursor.fetchall()]
    return column in columns


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
        if not check_table_exists(cursor, "fetchers"):
            print("⊘ Table 'fetchers' does not exist, skipping migration")
            print("  Run 'add_fetchers_table.py' migration first")
        else:
            # Check if negate_amount column already exists
            if check_column_exists(cursor, "fetchers", "negate_amount"):
                print("⊘ Column 'negate_amount' already exists, skipping")
            else:
                print("Adding 'negate_amount' column to 'fetchers' table...")
                cursor.execute("""
                    ALTER TABLE fetchers
                    ADD COLUMN negate_amount INTEGER DEFAULT 0
                """)
                print("✓ Added 'negate_amount' column")

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
    print("Migration: Add negate_amount Column to Fetchers")
    print("=" * 60)
    print()

    migrate(database_path)


if __name__ == "__main__":
    main()

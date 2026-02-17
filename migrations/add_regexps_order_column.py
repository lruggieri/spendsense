#!/usr/bin/env python3
"""
Migration: Add Regexps Order Column

This migration adds:
1. `order_index` column to regexps table for explicit ordering (drag-and-drop)
2. Index on regexps(user_id, order_index) for efficient queries
3. Initializes order_index for existing rows based on rowid

Usage:
    python3 migrations/add_regexps_order_column.py [--database-path PATH]
"""

import sqlite3
import sys
import os
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_database_path


def check_column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    """Check if a column exists in a table."""
    cursor.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in cursor.fetchall()]
    return column in columns


def check_table_exists(cursor: sqlite3.Cursor, table: str) -> bool:
    """Check if a table exists."""
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,)
    )
    return cursor.fetchone() is not None


def check_index_exists(cursor: sqlite3.Cursor, index: str) -> bool:
    """Check if an index exists."""
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
        (index,)
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

        # 1. Check if regexps table exists
        if not check_table_exists(cursor, "regexps"):
            print("⚠ 'regexps' table does not exist. Creating it...")
            cursor.execute("""
                CREATE TABLE regexps (
                    id TEXT PRIMARY KEY,
                    raw TEXT NOT NULL,
                    description TEXT NOT NULL,
                    internal_category TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    order_index INTEGER NOT NULL DEFAULT 0
                )
            """)
            print("✓ Created 'regexps' table with order_index column")
        else:
            print("✓ 'regexps' table exists")

            # 2. Add order_index column if it doesn't exist
            if not check_column_exists(cursor, "regexps", "order_index"):
                print("Adding 'order_index' column to regexps table...")
                cursor.execute("""
                    ALTER TABLE regexps
                    ADD COLUMN order_index INTEGER NOT NULL DEFAULT 0
                """)
                print("✓ Added 'order_index' column to regexps table")

                # Initialize order_index for existing rows based on rowid
                print("Initializing order_index for existing rows...")
                cursor.execute("""
                    UPDATE regexps
                    SET order_index = rowid
                """)
                rows_updated = cursor.rowcount
                print(f"✓ Initialized order_index for {rows_updated} existing rows")
            else:
                print("⊘ Column 'order_index' already exists in regexps table, skipping")

        # 3. Create index on regexps(user_id, order_index) if it doesn't exist
        if not check_index_exists(cursor, "idx_regexps_order"):
            print("Creating index on regexps(user_id, order_index)...")
            cursor.execute("""
                CREATE INDEX idx_regexps_order ON regexps(user_id, order_index)
            """)
            print("✓ Created index 'idx_regexps_order'")
        else:
            print("⊘ Index 'idx_regexps_order' already exists, skipping")

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
    print("Migration: Add Regexps Order Column")
    print("=" * 60)
    print()

    migrate(database_path)


if __name__ == "__main__":
    main()

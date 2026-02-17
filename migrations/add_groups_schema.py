#!/usr/bin/env python3
"""
Migration: Add Groups Schema

This migration adds:
1. `groups` table with id, name, and user_id columns
2. Index on groups.user_id for efficient queries
3. `groups` column to transactions table (JSON array of group IDs)

Usage:
    python3 migrations/add_groups_schema.py [--database-path PATH]
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

        # 1. Create groups table if it doesn't exist
        if not check_table_exists(cursor, "groups"):
            print("Creating 'groups' table...")
            cursor.execute("""
                CREATE TABLE groups (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    user_id TEXT NOT NULL
                )
            """)
            print("✓ Created 'groups' table")
        else:
            print("⊘ 'groups' table already exists, skipping")

        # 2. Create index on groups.user_id if it doesn't exist
        if not check_index_exists(cursor, "idx_groups_user_id"):
            print("Creating index on groups.user_id...")
            cursor.execute("CREATE INDEX idx_groups_user_id ON groups(user_id)")
            print("✓ Created index 'idx_groups_user_id'")
        else:
            print("⊘ Index 'idx_groups_user_id' already exists, skipping")

        # 3. Add groups column to transactions table if it doesn't exist
        if not check_column_exists(cursor, "transactions", "groups"):
            print("Adding 'groups' column to transactions table...")
            cursor.execute("""
                ALTER TABLE transactions
                ADD COLUMN groups TEXT DEFAULT '[]'
            """)
            print("✓ Added 'groups' column to transactions table")
        else:
            print("⊘ Column 'groups' already exists in transactions table, skipping")

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
    print("Migration: Add Groups Schema")
    print("=" * 60)
    print()

    migrate(database_path)


if __name__ == "__main__":
    main()

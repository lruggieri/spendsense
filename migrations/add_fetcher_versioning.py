#!/usr/bin/env python3
"""
Migration: Add Fetcher Versioning and Link Transactions to Fetchers

Adds versioning support to fetchers with immutability semantics:
- group_id: UUID grouping all versions of a fetcher together
- version: Version number within the group

Also links transactions to specific fetcher versions:
- fetcher_id: Links transaction to the fetcher version that created it

Usage:
    python3 migrations/add_fetcher_versioning.py [--database-path PATH]
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


def check_index_exists(cursor: sqlite3.Cursor, index_name: str) -> bool:
    """Check if an index exists."""
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
        (index_name,)
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

        # === PART 1: Fetchers table versioning columns ===

        if not check_table_exists(cursor, "fetchers"):
            print("⊘ Table 'fetchers' does not exist, skipping fetcher versioning")
            print("  Run 'add_fetchers_table.py' migration first")
        else:
            # Add group_id column
            if check_column_exists(cursor, "fetchers", "group_id"):
                print("⊘ Column 'group_id' already exists in 'fetchers', skipping")
            else:
                print("Adding 'group_id' column to 'fetchers' table...")
                cursor.execute("""
                    ALTER TABLE fetchers
                    ADD COLUMN group_id TEXT
                """)
                print("✓ Added 'group_id' column")

                # Backfill: set group_id = id for existing fetchers
                print("Backfilling 'group_id' with existing fetcher IDs...")
                cursor.execute("""
                    UPDATE fetchers
                    SET group_id = id
                    WHERE group_id IS NULL
                """)
                backfilled_count = cursor.rowcount
                print(f"✓ Backfilled {backfilled_count} fetcher(s)")

            # Add version column
            if check_column_exists(cursor, "fetchers", "version"):
                print("⊘ Column 'version' already exists in 'fetchers', skipping")
            else:
                print("Adding 'version' column to 'fetchers' table...")
                cursor.execute("""
                    ALTER TABLE fetchers
                    ADD COLUMN version INTEGER DEFAULT 1
                """)
                print("✓ Added 'version' column")

            # Create index for group_id + version queries
            if check_index_exists(cursor, "idx_fetchers_group_version"):
                print("⊘ Index 'idx_fetchers_group_version' already exists, skipping")
            else:
                print("Creating index 'idx_fetchers_group_version'...")
                cursor.execute("""
                    CREATE INDEX idx_fetchers_group_version
                    ON fetchers(user_id, group_id, version)
                """)
                print("✓ Created index 'idx_fetchers_group_version'")

            # Create partial unique index to enforce one enabled version per group
            # Note: SQLite supports partial indexes with WHERE clause
            if check_index_exists(cursor, "idx_fetchers_enabled_per_group"):
                print("⊘ Index 'idx_fetchers_enabled_per_group' already exists, skipping")
            else:
                print("Creating unique index 'idx_fetchers_enabled_per_group'...")
                cursor.execute("""
                    CREATE UNIQUE INDEX idx_fetchers_enabled_per_group
                    ON fetchers(group_id, user_id)
                    WHERE enabled = 1
                """)
                print("✓ Created unique index 'idx_fetchers_enabled_per_group'")

        # === PART 2: Transactions table fetcher_id column ===

        if not check_table_exists(cursor, "transactions"):
            print("⊘ Table 'transactions' does not exist, skipping fetcher_id column")
        else:
            # Add fetcher_id column
            if check_column_exists(cursor, "transactions", "fetcher_id"):
                print("⊘ Column 'fetcher_id' already exists in 'transactions', skipping")
            else:
                print("Adding 'fetcher_id' column to 'transactions' table...")
                cursor.execute("""
                    ALTER TABLE transactions
                    ADD COLUMN fetcher_id TEXT
                """)
                print("✓ Added 'fetcher_id' column")

            # Create index for fetcher_id queries
            if check_index_exists(cursor, "idx_transactions_fetcher_id"):
                print("⊘ Index 'idx_transactions_fetcher_id' already exists, skipping")
            else:
                print("Creating index 'idx_transactions_fetcher_id'...")
                cursor.execute("""
                    CREATE INDEX idx_transactions_fetcher_id
                    ON transactions(fetcher_id)
                """)
                print("✓ Created index 'idx_transactions_fetcher_id'")

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
    print("Migration: Add Fetcher Versioning")
    print("=" * 60)
    print()

    migrate(database_path)


if __name__ == "__main__":
    main()

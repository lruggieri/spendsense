#!/usr/bin/env python3
"""
Migration: Add Created At Timestamp to Transactions

This migration adds:
1. `created_at` column to transactions table (immutable timestamp of when transaction was fetched/created)
2. Backfills all existing transactions with `updated_at` value (best approximation available)
3. Creates an index on `created_at` for query performance

Usage:
    python3 migrations/add_created_at_to_transactions.py [--database-path PATH]
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


def migrate(database_path: str) -> None:
    """Run the migration."""
    print(f"Running migration on database: {database_path}")

    if not os.path.exists(database_path):
        print(f"ERROR: Database not found at {database_path}")
        sys.exit(1)

    conn = sqlite3.connect(database_path, timeout=30.0)  # 30 second timeout
    cursor = conn.cursor()

    try:
        # Start transaction with IMMEDIATE lock to handle concurrent access
        cursor.execute("BEGIN IMMEDIATE TRANSACTION")

        # Add created_at column to transactions table if it doesn't exist
        if not check_column_exists(cursor, "transactions", "created_at"):
            print("[1/4] Adding 'created_at' column to transactions table...")
            # Note: ALTER TABLE ADD COLUMN doesn't support function defaults in SQLite
            # So we add it without NOT NULL first, then backfill
            cursor.execute("""
                ALTER TABLE transactions
                ADD COLUMN created_at TEXT
            """)
            print("✓ Added 'created_at' column to transactions table")

            # Backfill existing rows with updated_at value
            print("[2/4] Backfilling existing transactions with 'updated_at' values...")
            cursor.execute("""
                UPDATE transactions
                SET created_at = updated_at
                WHERE created_at IS NULL
            """)
            cursor.execute("SELECT COUNT(*) FROM transactions")
            count = cursor.fetchone()[0]
            print(f"✓ Backfilled {count} existing transactions")

            # Create index on created_at
            print("[3/4] Creating index on 'created_at' column...")
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_created_at ON transactions(created_at)
            """)
            print("✓ Created index 'idx_created_at' on transactions table")
        else:
            print("⊘ Column 'created_at' already exists in transactions table, skipping")

        # Verify the migration
        cursor.execute("SELECT created_at FROM transactions LIMIT 1")
        result = cursor.fetchone()
        if result:
            print(f"[4/4] Verification: Sample transaction has created_at='{result[0]}'")
        else:
            print("[4/4] No transactions found (empty table)")

        # Verify no NULL values
        cursor.execute("SELECT COUNT(*) FROM transactions WHERE created_at IS NULL")
        null_count = cursor.fetchone()[0]
        if null_count > 0:
            raise Exception(f"Found {null_count} transactions with NULL created_at")
        print(f"✓ Verified all transactions have created_at values (no NULLs)")

        # Commit transaction
        conn.commit()
        print("\n✓ Migration completed successfully!")
        print(f"All existing transactions now have created_at timestamps")

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
    print("Migration: Add Created At Timestamp to Transactions")
    print("=" * 60)
    print()

    migrate(database_path)


if __name__ == "__main__":
    main()

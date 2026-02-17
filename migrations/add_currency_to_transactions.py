#!/usr/bin/env python3
"""
Migration: Add Currency to Transactions

This migration adds:
1. `currency` column to transactions table (ISO 4217 currency code)
2. Backfills all existing transactions with 'JPY' as default currency

Usage:
    python3 migrations/add_currency_to_transactions.py [--database-path PATH]
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

    conn = sqlite3.connect(database_path)
    cursor = conn.cursor()

    try:
        # Start transaction
        cursor.execute("BEGIN TRANSACTION")

        # Add currency column to transactions table if it doesn't exist
        if not check_column_exists(cursor, "transactions", "currency"):
            print("[1/2] Adding 'currency' column to transactions table...")
            cursor.execute("""
                ALTER TABLE transactions
                ADD COLUMN currency TEXT NOT NULL DEFAULT 'JPY'
            """)
            print("✓ Added 'currency' column to transactions table")

            # Count transactions that were backfilled
            cursor.execute("SELECT COUNT(*) FROM transactions")
            count = cursor.fetchone()[0]
            print(f"✓ Backfilled {count} existing transactions with 'JPY'")
        else:
            print("⊘ Column 'currency' already exists in transactions table, skipping")

        # Verify the migration
        cursor.execute("SELECT currency FROM transactions LIMIT 1")
        result = cursor.fetchone()
        if result:
            print(f"[2/2] Verification: Sample transaction has currency='{result[0]}'")
        else:
            print("[2/2] No transactions found (empty table)")

        # Commit transaction
        conn.commit()
        print("\n✓ Migration completed successfully!")
        print(f"All existing transactions now have currency='JPY'")

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
    print("Migration: Add Currency to Transactions")
    print("=" * 60)
    print()

    migrate(database_path)


if __name__ == "__main__":
    main()

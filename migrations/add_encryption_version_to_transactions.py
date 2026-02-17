#!/usr/bin/env python3
"""
Migration: Add encryption_version column to transactions table.

This migration adds:
1. `encryption_version` column (0=plaintext, 1=encrypted) to support transparent field encryption.

All existing rows default to 0 (plaintext). No backfill needed.

Usage:
    python3 migrations/add_encryption_version_to_transactions.py [--database-path PATH]
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

    conn = sqlite3.connect(database_path, timeout=30.0)
    cursor = conn.cursor()

    try:
        cursor.execute("BEGIN IMMEDIATE TRANSACTION")

        if not check_column_exists(cursor, "transactions", "encryption_version"):
            print("[1/2] Adding 'encryption_version' column to transactions table...")
            cursor.execute("""
                ALTER TABLE transactions
                ADD COLUMN encryption_version INTEGER NOT NULL DEFAULT 0
            """)
            print("  Added 'encryption_version' column")

            # Verify
            print("[2/2] Verifying migration...")
            cursor.execute("SELECT COUNT(*) FROM transactions WHERE encryption_version = 0")
            count = cursor.fetchone()[0]
            print(f"  All {count} existing transactions have encryption_version=0 (plaintext)")
        else:
            print("  Column 'encryption_version' already exists, skipping")

        conn.commit()
        print("\nMigration completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"\nMigration failed: {e}")
        sys.exit(1)

    finally:
        conn.close()


def main():
    """Main entry point."""
    if len(sys.argv) > 2 and sys.argv[1] == "--database-path":
        database_path = sys.argv[2]
    else:
        database_path = get_database_path()

    print("=" * 60)
    print("Migration: Add encryption_version to transactions")
    print("=" * 60)
    print()

    migrate(database_path)


if __name__ == "__main__":
    main()

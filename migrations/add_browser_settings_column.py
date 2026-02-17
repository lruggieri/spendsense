#!/usr/bin/env python3
"""
Migration: Add Browser Settings Column

This migration adds:
1. `browser_settings` column to user_settings table for browser-specific preferences (JSON)
2. Initializes browser_settings with empty JSON object '{}' for existing rows

Usage:
    python3 migrations/add_browser_settings_column.py [--database-path PATH]
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

        # 1. Check if user_settings table exists
        if not check_table_exists(cursor, "user_settings"):
            print("⚠ 'user_settings' table does not exist. Creating it...")
            cursor.execute("""
                CREATE TABLE user_settings (
                    user_id TEXT PRIMARY KEY,
                    display_language TEXT NOT NULL DEFAULT 'en',
                    default_currency TEXT NOT NULL DEFAULT 'USD',
                    browser_settings TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            print("✓ Created 'user_settings' table with browser_settings column")
        else:
            print("✓ 'user_settings' table exists")

            # 2. Add browser_settings column if it doesn't exist
            if not check_column_exists(cursor, "user_settings", "browser_settings"):
                print("Adding 'browser_settings' column to user_settings table...")
                cursor.execute("""
                    ALTER TABLE user_settings
                    ADD COLUMN browser_settings TEXT DEFAULT '{}'
                """)
                print("✓ Added 'browser_settings' column to user_settings table")

                # Initialize browser_settings for existing rows with empty JSON
                print("Initializing browser_settings for existing rows...")
                cursor.execute("""
                    UPDATE user_settings
                    SET browser_settings = '{}'
                    WHERE browser_settings IS NULL
                """)
                rows_updated = cursor.rowcount
                print(f"✓ Initialized browser_settings for {rows_updated} existing rows")
            else:
                print("⊘ Column 'browser_settings' already exists in user_settings table, skipping")

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
    print("Migration: Add Browser Settings Column")
    print("=" * 60)
    print()

    migrate(database_path)


if __name__ == "__main__":
    main()

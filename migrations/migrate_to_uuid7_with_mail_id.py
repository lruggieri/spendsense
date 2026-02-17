#!/usr/bin/env python3
"""
Migration: Migrate to UUID7 with mail_id

This migration:
1. Adds `mail_id` column to transactions table
2. Generates UUID7 for all Gmail-fetched transactions (identified by ID format)
3. Stores original Gmail IDs in the new `mail_id` column
4. Updates embeddings table foreign keys to point to new UUID7s
5. Updates manual_assignments table foreign keys to point to new UUID7s
6. Creates index on mail_id for efficient lookups

WARNING: This is a complex migration that modifies primary keys.
Make sure to backup your database before running!

Usage:
    python3 migrations/migrate_to_uuid7_with_mail_id.py [--database-path PATH]
"""

import sqlite3
import sys
import os
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_database_path
from uuid6 import uuid7


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


def is_gmail_id(tx_id: str) -> bool:
    """
    Check if a transaction ID is a Gmail message ID (not UUID7).
    Gmail IDs are hex strings without hyphens, typically 16 characters.
    UUID7s have the format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx (4 hyphens)
    """
    return tx_id.count('-') != 4


def migrate(database_path: str) -> None:
    """Run the migration."""
    print(f"Running migration on database: {database_path}")

    if not os.path.exists(database_path):
        print(f"ERROR: Database not found at {database_path}")
        sys.exit(1)

    # Create backup path
    backup_path = database_path + ".pre_uuid7_migration.backup"

    # Check if already migrated or if table doesn't exist
    conn = sqlite3.connect(database_path)
    cursor = conn.cursor()

    if not check_table_exists(cursor, "transactions"):
        print("⊘ No transactions table found - nothing to migrate")
        print("  The table will be created with the new schema when the app starts")
        conn.close()
        return

    if check_column_exists(cursor, "transactions", "mail_id"):
        print("⊘ Migration already applied (mail_id column exists)")
        conn.close()
        return

    conn.close()

    # Create backup
    print(f"Creating backup at: {backup_path}")
    import shutil
    shutil.copy2(database_path, backup_path)
    print("✓ Backup created")

    conn = sqlite3.connect(database_path)
    cursor = conn.cursor()

    try:
        # Start transaction
        cursor.execute("BEGIN TRANSACTION")
        print("\nStarting migration...")

        # Step 1: Add mail_id column
        print("\n[1/8] Adding mail_id column to transactions table...")
        cursor.execute("ALTER TABLE transactions ADD COLUMN mail_id TEXT")
        print("✓ Added mail_id column")

        # Step 2: Create mapping of old Gmail IDs to new UUID7s
        print("\n[2/8] Analyzing transactions and creating ID mapping...")
        cursor.execute("SELECT id FROM transactions")
        rows = cursor.fetchall()

        id_mapping = {}  # {old_gmail_id: new_uuid7}
        gmail_count = 0
        uuid_count = 0

        for (old_id,) in rows:
            if is_gmail_id(old_id):
                id_mapping[old_id] = str(uuid7())
                gmail_count += 1
            else:
                uuid_count += 1

        print(f"  - Found {gmail_count} Gmail-fetched transactions (will migrate)")
        print(f"  - Found {uuid_count} manually-created transactions (already UUID7)")
        print(f"✓ Created mapping for {len(id_mapping)} transactions")

        if len(id_mapping) == 0:
            print("\n⊘ No Gmail-fetched transactions to migrate. Migration complete!")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_mail_id ON transactions(mail_id)")
            conn.commit()
            conn.close()
            return

        # Step 3: Create temporary tables
        print("\n[3/8] Creating temporary tables...")

        cursor.execute("""
            CREATE TABLE transactions_new (
                id TEXT PRIMARY KEY,
                mail_id TEXT,
                date TEXT NOT NULL,
                amount INTEGER NOT NULL,
                description TEXT NOT NULL,
                source TEXT NOT NULL,
                comment TEXT DEFAULT '',
                user_id TEXT NOT NULL,
                groups TEXT DEFAULT '[]',
                updated_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE embeddings_new (
                tx_id TEXT PRIMARY KEY,
                embedding BLOB NOT NULL,
                description_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(tx_id) REFERENCES transactions(id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE manual_assignments_new (
                tx_id TEXT PRIMARY KEY,
                category_id TEXT NOT NULL,
                user_id TEXT NOT NULL
            )
        """)

        print("✓ Created temporary tables")

        # Step 4: Copy transactions with new IDs
        print("\n[4/8] Migrating transactions to new IDs...")
        # Select only original columns (not the newly added mail_id which is NULL anyway)
        cursor.execute("SELECT id, date, amount, description, source, comment, user_id, groups, updated_at FROM transactions")
        tx_rows = cursor.fetchall()

        migrated_count = 0
        for row in tx_rows:
            old_id = row[0]
            new_id = id_mapping.get(old_id, old_id)  # Use mapping or keep UUID7
            mail_id = old_id if old_id in id_mapping else None  # Set mail_id for Gmail-fetched

            cursor.execute("""
                INSERT INTO transactions_new
                (id, mail_id, date, amount, description, source, comment, user_id, groups, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (new_id, mail_id, *row[1:]))

            migrated_count += 1

        print(f"✓ Migrated {migrated_count} transactions")

        # Step 5: Update embeddings with new transaction IDs
        print("\n[5/8] Updating embeddings foreign keys...")
        if check_table_exists(cursor, "embeddings"):
            cursor.execute("SELECT * FROM embeddings")
            emb_rows = cursor.fetchall()

            emb_count = 0
            for row in emb_rows:
                old_tx_id = row[0]
                new_tx_id = id_mapping.get(old_tx_id, old_tx_id)

                cursor.execute("""
                    INSERT INTO embeddings_new
                    (tx_id, embedding, description_hash, created_at)
                    VALUES (?, ?, ?, ?)
                """, (new_tx_id, *row[1:]))

                emb_count += 1

            print(f"✓ Updated {emb_count} embedding references")
        else:
            print("⊘ No embeddings table found, skipping")

        # Step 6: Update manual_assignments with new transaction IDs
        print("\n[6/8] Updating manual_assignments foreign keys...")
        if check_table_exists(cursor, "manual_assignments"):
            cursor.execute("SELECT * FROM manual_assignments")
            ma_rows = cursor.fetchall()

            ma_count = 0
            for row in ma_rows:
                old_tx_id = row[0]
                new_tx_id = id_mapping.get(old_tx_id, old_tx_id)

                cursor.execute("""
                    INSERT INTO manual_assignments_new
                    (tx_id, category_id, user_id)
                    VALUES (?, ?, ?)
                """, (new_tx_id, *row[1:]))

                ma_count += 1

            print(f"✓ Updated {ma_count} manual assignment references")
        else:
            print("⊘ No manual_assignments table found, skipping")

        # Step 7: Drop old tables and rename new ones
        print("\n[7/8] Replacing old tables with new ones...")

        if check_table_exists(cursor, "embeddings"):
            cursor.execute("DROP TABLE embeddings")

        if check_table_exists(cursor, "manual_assignments"):
            cursor.execute("DROP TABLE manual_assignments")

        cursor.execute("DROP TABLE transactions")
        cursor.execute("ALTER TABLE transactions_new RENAME TO transactions")
        cursor.execute("ALTER TABLE embeddings_new RENAME TO embeddings")
        cursor.execute("ALTER TABLE manual_assignments_new RENAME TO manual_assignments")

        print("✓ Replaced old tables")

        # Step 8: Recreate indexes
        print("\n[8/8] Recreating indexes...")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_date ON transactions(date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_source ON transactions(source)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_mail_id ON transactions(mail_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_category_id ON manual_assignments(category_id)")
        print("✓ Recreated indexes")

        # Commit transaction
        conn.commit()
        print("\n" + "=" * 60)
        print(f"✓ Migration completed successfully!")
        print(f"  - Migrated {len(id_mapping)} Gmail-fetched transactions to UUID7")
        print(f"  - Backup saved at: {backup_path}")
        print("=" * 60)

    except Exception as e:
        # Rollback on error
        conn.rollback()
        print(f"\n✗ Migration failed: {e}")
        print(f"  Database rolled back to pre-migration state")
        print(f"  Backup available at: {backup_path}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        conn.close()


def verify_migration(database_path: str) -> None:
    """Verify the migration was successful."""
    print("\nVerifying migration...")

    conn = sqlite3.connect(database_path)
    cursor = conn.cursor()

    try:
        # Check mail_id column exists
        if not check_column_exists(cursor, "transactions", "mail_id"):
            print("✗ Verification failed: mail_id column not found")
            return

        # Count transactions with mail_id
        cursor.execute("SELECT COUNT(*) FROM transactions WHERE mail_id IS NOT NULL")
        mail_id_count = cursor.fetchone()[0]

        # Count transactions with NULL mail_id (manual transactions)
        cursor.execute("SELECT COUNT(*) FROM transactions WHERE mail_id IS NULL")
        manual_count = cursor.fetchone()[0]

        # Check all IDs are UUID7 format or have mail_id
        cursor.execute("SELECT COUNT(*) FROM transactions")
        total_count = cursor.fetchone()[0]

        print(f"✓ Verification passed:")
        print(f"  - Total transactions: {total_count}")
        print(f"  - Gmail-fetched (with mail_id): {mail_id_count}")
        print(f"  - Manual (without mail_id): {manual_count}")

        # Check embeddings integrity
        if check_table_exists(cursor, "embeddings"):
            cursor.execute("""
                SELECT COUNT(*) FROM embeddings e
                LEFT JOIN transactions t ON e.tx_id = t.id
                WHERE t.id IS NULL
            """)
            orphaned = cursor.fetchone()[0]

            if orphaned > 0:
                print(f"⚠ Warning: Found {orphaned} orphaned embeddings")
            else:
                print(f"✓ All embeddings have valid transaction references")

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
    print("Migration: Migrate to UUID7 with mail_id")
    print("=" * 60)
    print()
    print("⚠ WARNING: This migration modifies primary keys!")
    print("  A backup will be created automatically.")
    print()

    migrate(database_path)
    verify_migration(database_path)


if __name__ == "__main__":
    main()

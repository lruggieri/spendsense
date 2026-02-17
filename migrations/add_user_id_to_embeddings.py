#!/usr/bin/env python3
"""
Migration: Add user_id to embeddings table

This migration:
1. Checks if user_id column exists in embeddings table
2. If not, creates a new embeddings table with user_id
3. Migrates existing embeddings data, pulling user_id from transactions table
4. Replaces old table with new table
5. Creates index on user_id for efficient lookups

WARNING: This migration modifies the embeddings table structure.
Make sure to backup your database before running!

Usage:
    python3 migrations/add_user_id_to_embeddings.py [--database-path PATH]
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

    # Create backup path
    backup_path = database_path + ".pre_embeddings_user_id.backup"

    # Check if already migrated or if table doesn't exist
    conn = sqlite3.connect(database_path)
    cursor = conn.cursor()

    if not check_table_exists(cursor, "embeddings"):
        print("⊘ No embeddings table found - nothing to migrate")
        print("  The table will be created with the new schema when the app starts")
        conn.close()
        return

    if check_column_exists(cursor, "embeddings", "user_id"):
        print("⊘ Migration already applied (user_id column exists)")
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

        # Step 1: Check if we have any embeddings to migrate
        print("\n[1/5] Analyzing embeddings table...")
        cursor.execute("SELECT COUNT(*) FROM embeddings")
        embedding_count = cursor.fetchone()[0]
        print(f"  - Found {embedding_count} embeddings to migrate")

        if embedding_count == 0:
            print("\n⊘ No embeddings to migrate. Adding user_id column...")
            cursor.execute("ALTER TABLE embeddings ADD COLUMN user_id TEXT NOT NULL DEFAULT ''")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_embeddings_user_id ON embeddings(user_id)")
            conn.commit()
            print("✓ Migration complete!")
            conn.close()
            return

        # Step 2: Create new embeddings table with user_id
        print("\n[2/5] Creating new embeddings table with user_id...")
        cursor.execute("""
            CREATE TABLE embeddings_new (
                tx_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                embedding BLOB NOT NULL,
                description_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(tx_id) REFERENCES transactions(id) ON DELETE CASCADE
            )
        """)
        print("✓ Created new table")

        # Step 3: Copy embeddings with user_id from transactions
        print("\n[3/5] Migrating embeddings with user_id from transactions...")
        cursor.execute("""
            INSERT INTO embeddings_new (tx_id, user_id, embedding, description_hash, created_at)
            SELECT e.tx_id, t.user_id, e.embedding, e.description_hash, e.created_at
            FROM embeddings e
            INNER JOIN transactions t ON e.tx_id = t.id
        """)
        migrated_count = cursor.rowcount
        print(f"✓ Migrated {migrated_count} embeddings")

        # Step 4: Drop old table and rename new one
        print("\n[4/5] Replacing old table with new one...")
        cursor.execute("DROP TABLE embeddings")
        cursor.execute("ALTER TABLE embeddings_new RENAME TO embeddings")
        print("✓ Replaced old table")

        # Step 5: Create indexes
        print("\n[5/5] Creating indexes...")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_embeddings_user_id ON embeddings(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_embeddings_hash ON embeddings(description_hash)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_embeddings_created_at ON embeddings(created_at)")
        print("✓ Created indexes")

        # Commit transaction
        conn.commit()
        print("\n" + "=" * 60)
        print(f"✓ Migration completed successfully!")
        print(f"  - Migrated {migrated_count} embeddings")
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
        # Check user_id column exists
        if not check_column_exists(cursor, "embeddings", "user_id"):
            print("✗ Verification failed: user_id column not found")
            return

        # Count embeddings
        cursor.execute("SELECT COUNT(*) FROM embeddings")
        total_embeddings = cursor.fetchone()[0]

        # Count embeddings with user_id
        cursor.execute("SELECT COUNT(*) FROM embeddings WHERE user_id IS NOT NULL AND user_id != ''")
        with_user_id = cursor.fetchone()[0]

        print(f"✓ Verification passed:")
        print(f"  - Total embeddings: {total_embeddings}")
        print(f"  - Embeddings with user_id: {with_user_id}")

        # Check index exists
        if check_index_exists(cursor, "idx_embeddings_user_id"):
            print(f"✓ Index idx_embeddings_user_id exists")
        else:
            print(f"⚠ Warning: Index idx_embeddings_user_id not found")

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
    print("Migration: Add user_id to embeddings table")
    print("=" * 60)
    print()
    print("⚠ WARNING: This migration modifies the embeddings table!")
    print("  A backup will be created automatically.")
    print()

    migrate(database_path)
    verify_migration(database_path)


if __name__ == "__main__":
    main()

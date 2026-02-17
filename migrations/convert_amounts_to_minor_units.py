#!/usr/bin/env python3
"""
Migration: Convert Amounts to Minor Currency Units

This migration converts all transaction amounts from major currency units (e.g., dollars)
to minor currency units (e.g., cents) to preserve decimal precision.

Background:
- Current system stores amounts as INTEGER but loses decimal precision (e.g., $5.99 becomes $5)
- New system stores amounts as INTEGER in minor units (e.g., $5.99 becomes 599 cents)
- Based on ISO 4217 standard:
  * 0 decimals: JPY, KRW, ISK (multiply by 1)
  * 2 decimals: USD, EUR, GBP, etc. (multiply by 100)

Safety Features:
- Creates automatic backup before migration
- Shows preview of changes before confirming
- Wrapped in transaction (rollback on error)
- Validates results after migration

Usage:
    python3 migrations/convert_amounts_to_minor_units.py [--database-path PATH] [--yes]

Options:
    --database-path PATH    Path to database file (default: from config)
    --yes                   Skip confirmation prompt (use with caution!)

WARNING:
- This migration cannot be easily undone - backup is created automatically
- Existing data may already have precision loss from previous bugs
- Review backup file before proceeding with production data
"""

import sqlite3
import sys
import os
import shutil
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_database_path, get_currency_minor_units


def create_backup(database_path: str) -> str:
    """Create a backup of the database file."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{database_path}.pre_minor_units_migration_{timestamp}.backup"

    print(f"Creating backup: {backup_path}")
    shutil.copy2(database_path, backup_path)
    print(f"✓ Backup created successfully\n")

    return backup_path


def analyze_transactions(cursor: sqlite3.Cursor) -> dict:
    """Analyze what will be changed."""
    cursor.execute("SELECT currency, COUNT(*) FROM transactions GROUP BY currency")
    results = cursor.fetchall()

    analysis = {}
    for currency, count in results:
        minor_units = get_currency_minor_units(currency)
        multiplier = 10 ** minor_units
        analysis[currency] = {
            'count': count,
            'minor_units': minor_units,
            'multiplier': multiplier
        }

    return analysis


def show_preview(analysis: dict) -> None:
    """Show what will be changed."""
    print("Migration Preview")
    print("=" * 60)
    print(f"{'Currency':<10} {'Transactions':<15} {'Decimals':<10} {'Multiplier':<12}")
    print("-" * 60)

    total_transactions = 0
    for currency, data in sorted(analysis.items()):
        print(f"{currency:<10} {data['count']:<15} {data['minor_units']:<10} {data['multiplier']:<12}")
        total_transactions += data['count']

    print("-" * 60)
    print(f"{'TOTAL':<10} {total_transactions:<15}")
    print("=" * 60)
    print()

    # Show examples
    print("Example transformations:")
    for currency, data in sorted(analysis.items()):
        if data['minor_units'] == 0:
            print(f"  {currency}: 1234 → 1234 (no change)")
        elif data['minor_units'] == 2:
            print(f"  {currency}: 1234 → 123400 (×100)")
    print()


def verify_sample_transactions(cursor: sqlite3.Cursor, currency: str, expected_multiplier: int) -> bool:
    """Verify a sample of transactions were migrated correctly."""
    cursor.execute("""
        SELECT id, amount FROM transactions
        WHERE currency = ?
        LIMIT 5
    """, (currency,))

    samples = cursor.fetchall()
    if not samples:
        return True

    # Check if amounts look like they've been multiplied
    # For example, if multiplier is 100, amounts should be multiples of 100 (or at least much larger)
    # This is a basic sanity check
    for tx_id, amount in samples:
        if expected_multiplier > 1 and amount < 10:
            print(f"  WARNING: Transaction {tx_id} has suspiciously small amount: {amount}")
            return False

    return True


def migrate(database_path: str, skip_confirmation: bool = False) -> None:
    """Run the migration."""
    print(f"Database: {database_path}\n")

    if not os.path.exists(database_path):
        print(f"ERROR: Database not found at {database_path}")
        sys.exit(1)

    # Create backup first
    backup_path = create_backup(database_path)

    conn = sqlite3.connect(database_path)
    cursor = conn.cursor()

    try:
        # Analyze current state
        print("Analyzing current transactions...")
        analysis = analyze_transactions(cursor)

        if not analysis:
            print("No transactions found - nothing to migrate")
            return

        show_preview(analysis)

        # Confirmation
        if not skip_confirmation:
            print("IMPORTANT: This will modify all transaction amounts in the database.")
            print(f"Backup created at: {backup_path}\n")
            response = input("Type 'yes' to proceed with migration: ")

            if response.lower() != 'yes':
                print("\nMigration cancelled")
                sys.exit(0)
            print()

        # Start transaction
        cursor.execute("BEGIN TRANSACTION")

        # Migrate each currency
        total_updated = 0
        for currency, data in sorted(analysis.items()):
            multiplier = data['multiplier']
            count = data['count']

            print(f"[{currency}] Updating {count} transactions (×{multiplier})...")

            # Update all transactions for this currency
            cursor.execute("""
                UPDATE transactions
                SET amount = amount * ?
                WHERE currency = ?
            """, (multiplier, currency))

            updated = cursor.rowcount
            total_updated += updated

            print(f"✓ Updated {updated} {currency} transactions")

            # Verify sample transactions
            if not verify_sample_transactions(cursor, currency, multiplier):
                raise Exception(f"Verification failed for {currency} transactions")

        print()
        print("Verifying migration...")

        # Final verification: check that no amounts are 0 where they shouldn't be
        cursor.execute("SELECT COUNT(*) FROM transactions WHERE amount = 0")
        zero_count = cursor.fetchone()[0]
        if zero_count > 0:
            print(f"  Note: {zero_count} transactions have amount = 0 (may be refunds or valid)")

        # Check sample of each currency
        for currency in analysis.keys():
            cursor.execute("""
                SELECT amount FROM transactions
                WHERE currency = ?
                ORDER BY RANDOM()
                LIMIT 3
            """, (currency,))
            samples = [row[0] for row in cursor.fetchall()]
            print(f"  {currency} sample amounts: {samples}")

        # Commit transaction
        conn.commit()
        print()
        print("=" * 60)
        print("✓ Migration completed successfully!")
        print("=" * 60)
        print(f"Total transactions updated: {total_updated}")
        print(f"Backup location: {backup_path}")
        print()
        print("Next steps:")
        print("1. Restart the application")
        print("2. Verify amounts display correctly in the UI")
        print("3. Test adding new transactions")
        print("4. If issues occur, restore from backup:")
        print(f"   cp {backup_path} {database_path}")

    except Exception as e:
        # Rollback on error
        conn.rollback()
        print()
        print("=" * 60)
        print("✗ Migration failed!")
        print("=" * 60)
        print(f"Error: {e}")
        print(f"\nDatabase has been rolled back to previous state")
        print(f"Backup is still available at: {backup_path}")
        sys.exit(1)

    finally:
        conn.close()


def main():
    """Main entry point."""
    # Parse command line arguments
    database_path = None
    skip_confirmation = False

    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == "--database-path" and i + 1 < len(sys.argv):
            database_path = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--yes":
            skip_confirmation = True
            i += 1
        else:
            print(f"Unknown argument: {sys.argv[i]}")
            print("\nUsage: python3 convert_amounts_to_minor_units.py [--database-path PATH] [--yes]")
            sys.exit(1)

    if database_path is None:
        database_path = get_database_path()

    print("=" * 60)
    print("Migration: Convert Amounts to Minor Currency Units")
    print("=" * 60)
    print()

    migrate(database_path, skip_confirmation)


if __name__ == "__main__":
    main()

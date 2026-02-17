#!/usr/bin/env python3
"""
Migration: Add Visual Description Column to Regexps

This migration:
1. Renames `description` column to `name` (human-readable label)
2. Adds `visual_description` column for JSON-encoded visual rules
3. Converts existing patterns to visual rule format (best-effort)

Usage:
    python3 migrations/add_regexps_visual_description.py [--database-path PATH]
"""

import sqlite3
import sys
import os
import json
import re
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


def parse_raw_regex_to_visual_rules(raw_pattern: str, name: str) -> dict:
    """
    Parse raw regex pattern to visual rules format with OR/AND/NOT support.

    Handles three pattern types:
    1. OR patterns: (keyword1|keyword2|keyword3) - alternations
    2. AND patterns: (?=.*keyword) - positive lookahead assertions
    3. NOT patterns: (?!.*keyword) - negative lookahead assertions

    Args:
        raw_pattern: The raw regex pattern
        name: Human-readable name to use as fallback

    Returns:
        Visual rules dict with OR/AND/NOT rules
    """
    rules = []

    # 1. Extract OR patterns: look for (keyword1|keyword2|keyword3)
    # Skip word boundaries like (^|\s) and (\s|$)
    # Find parentheses groups with | that contain actual keywords (not regex metacharacters)
    or_pattern_matches = re.findall(r'\(([^)]*\|[^)]*)\)', raw_pattern)

    for or_group in or_pattern_matches:
        # Skip word boundary patterns: (^|\s) and (\s|$)
        if or_group in ['^|\\s', '\\s|$', '^|\\\\s', '\\\\s|$']:
            continue

        # This is a real keyword alternation
        or_keywords = or_group.split('|')
        for keyword in or_keywords:
            keyword_clean = keyword.strip().replace('\\', '')
            if keyword_clean and keyword_clean not in ['^', 's', '$', '\\s']:
                rules.append({"operator": "OR", "keyword": keyword_clean})

        # If we found keywords, stop looking (only process first OR group)
        if rules:
            break

    # 2. Extract AND patterns: (?=.*keyword)
    and_keywords = re.findall(r'\(\?=\.\*([^)]+)\)', raw_pattern)
    for keyword in and_keywords:
        keyword_clean = keyword.replace('\\', '')
        rules.append({"operator": "AND", "keyword": keyword_clean})

    # 3. Extract NOT patterns: (?!.*keyword)
    not_keywords = re.findall(r'\(\?!\.\*([^)]+)\)', raw_pattern)
    for keyword in not_keywords:
        keyword_clean = keyword.replace('\\', '')
        rules.append({"operator": "NOT", "keyword": keyword_clean})

    # Fallback: if no rules found, create a single OR rule with the name
    if not rules:
        rules.append({"operator": "OR", "keyword": name})

    return {
        "type": "visual_rule",
        "version": 1,
        "rules": rules
    }


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

        # Check if regexps table exists
        if not check_table_exists(cursor, "regexps"):
            print("⚠ 'regexps' table does not exist, skipping migration")
            conn.commit()
            return

        print("✓ 'regexps' table exists")

        # 1. Add visual_description column if it doesn't exist
        if not check_column_exists(cursor, "regexps", "visual_description"):
            print("Adding 'visual_description' column...")
            cursor.execute("""
                ALTER TABLE regexps
                ADD COLUMN visual_description TEXT
            """)
            print("✓ Added 'visual_description' column")
        else:
            print("⊘ Column 'visual_description' already exists, skipping")

        # 2. Rename description to name (if description exists and name doesn't)
        has_description = check_column_exists(cursor, "regexps", "description")
        has_name = check_column_exists(cursor, "regexps", "name")

        if has_description and not has_name:
            print("Renaming 'description' column to 'name'...")

            # SQLite doesn't support RENAME COLUMN directly in older versions
            # We need to create a new table and copy data

            # Get current schema
            cursor.execute("PRAGMA table_info(regexps)")
            columns = cursor.fetchall()

            # Create new table with renamed column
            cursor.execute("""
                CREATE TABLE regexps_new (
                    id TEXT PRIMARY KEY,
                    raw TEXT NOT NULL,
                    name TEXT NOT NULL,
                    internal_category TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    order_index INTEGER NOT NULL DEFAULT 0,
                    visual_description TEXT
                )
            """)

            # Copy data from old table
            cursor.execute("""
                INSERT INTO regexps_new (id, raw, name, internal_category, user_id, order_index, visual_description)
                SELECT id, raw, description, internal_category, user_id, order_index, visual_description
                FROM regexps
            """)

            # Drop old table
            cursor.execute("DROP TABLE regexps")

            # Rename new table
            cursor.execute("ALTER TABLE regexps_new RENAME TO regexps")

            # Recreate index
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_regexps_order ON regexps(user_id, order_index)")

            print("✓ Renamed 'description' to 'name'")
        elif has_name:
            print("⊘ Column 'name' already exists, skipping rename")
        else:
            print("⚠ Neither 'description' nor 'name' column exists")

        # 3. Convert/update ALL patterns to visual rules format (including existing ones)
        # This ensures we re-parse with improved OR support
        cursor.execute("""
            SELECT id, raw, name, visual_description
            FROM regexps
        """)

        all_patterns = cursor.fetchall()

        if all_patterns:
            print(f"Parsing {len(all_patterns)} patterns to visual rules format (with OR support)...")

            updated_count = 0
            for pattern_id, raw_pattern, name, existing_visual_desc in all_patterns:
                # Parse the raw regex to get visual rules
                visual_rules = parse_raw_regex_to_visual_rules(raw_pattern, name)
                visual_rules_json = json.dumps(visual_rules)

                # Check if we need to update
                needs_update = (
                    not existing_visual_desc or
                    existing_visual_desc == '' or
                    existing_visual_desc != visual_rules_json
                )

                if needs_update:
                    cursor.execute("""
                        UPDATE regexps
                        SET visual_description = ?
                        WHERE id = ?
                    """, (visual_rules_json, pattern_id))

                    updated_count += 1

                    # Show preview of parsed rules
                    rules_preview = ", ".join([
                        f"{r['operator']} {r['keyword']}"
                        for r in visual_rules['rules'][:3]
                    ])
                    if len(visual_rules['rules']) > 3:
                        rules_preview += f" ... (+{len(visual_rules['rules']) - 3} more)"

                    print(f"  ✓ Updated '{name}': {rules_preview}")

            if updated_count > 0:
                print(f"✓ Updated {updated_count} patterns")
            else:
                print("⊘ All patterns already have correct visual_description")
        else:
            print("⊘ No patterns found in database")

        # Commit transaction
        conn.commit()
        print("\n✓ Migration completed successfully!")

    except Exception as e:
        # Rollback on error
        conn.rollback()
        print(f"\n✗ Migration failed: {e}")
        import traceback
        traceback.print_exc()
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
    print("Migration: Add Visual Description Column")
    print("=" * 60)
    print()

    migrate(database_path)


if __name__ == "__main__":
    main()

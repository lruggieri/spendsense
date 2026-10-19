"""
Core table definitions for the SQLite database.

Most repositories create their own table in their constructor. The tables
below are shared: the category repository also reads ``regexps`` and
``manual_assignments`` (to refuse deleting categories that are still in use),
so they must all exist before any of those repositories is used. Without this,
a brand-new database fails on the first request that touches categories.

``ensure_core_tables`` only creates tables that are missing (plus their
indexes), so it never alters an existing table, and it is cheap to call on
every repository construction.
"""

from infrastructure.persistence.sqlite.connection import get_connection

MANUAL_ASSIGNMENTS_DDL = """
CREATE TABLE IF NOT EXISTS manual_assignments (
    tx_id TEXT PRIMARY KEY,
    category_id TEXT NOT NULL,
    user_id TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_category_id ON manual_assignments(category_id);
"""

# Table name -> DDL (table + indexes). Kept in line with the schema produced
# by the scripts in migrations/, so fresh and long-lived databases match.
CORE_TABLES = {
    "categories": """
        CREATE TABLE IF NOT EXISTS categories (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            parent_id TEXT DEFAULT '',
            user_id TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_categories_user_id ON categories(user_id);
    """,
    "regexps": """
        CREATE TABLE IF NOT EXISTS regexps (
            id TEXT PRIMARY KEY,
            raw TEXT NOT NULL,
            name TEXT NOT NULL,
            internal_category TEXT NOT NULL,
            user_id TEXT NOT NULL,
            order_index INTEGER NOT NULL DEFAULT 0,
            visual_description TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_regexps_order ON regexps(user_id, order_index);
    """,
    "groups": """
        CREATE TABLE IF NOT EXISTS groups (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            user_id TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_groups_user_id ON groups(user_id);
    """,
    "fetchers": """
        CREATE TABLE IF NOT EXISTS fetchers (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            from_emails TEXT NOT NULL,
            subject_filter TEXT DEFAULT '',
            amount_pattern TEXT NOT NULL,
            merchant_pattern TEXT,
            currency_pattern TEXT,
            default_currency TEXT DEFAULT 'USD',
            enabled INTEGER DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            group_id TEXT,
            version INTEGER DEFAULT 1,
            negate_amount INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_fetchers_user_id ON fetchers(user_id);
        CREATE INDEX IF NOT EXISTS idx_fetchers_enabled ON fetchers(user_id, enabled);
        CREATE INDEX IF NOT EXISTS idx_fetchers_group_version
            ON fetchers(user_id, group_id, version);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_fetchers_enabled_per_group
            ON fetchers(group_id, user_id) WHERE enabled = 1;
    """,
    "manual_assignments": MANUAL_ASSIGNMENTS_DDL,
}


def ensure_core_tables(db_path: str) -> None:
    """Create any missing core table (and its indexes) in the database at ``db_path``."""
    conn = get_connection(db_path)
    try:
        placeholders = ", ".join("?" for _ in CORE_TABLES)
        existing = {
            row[0]
            for row in conn.execute(
                f"SELECT name FROM sqlite_master WHERE type = 'table' AND name IN ({placeholders})",  # nosec B608 - placeholders only
                tuple(CORE_TABLES),
            )
        }
        missing = [name for name in CORE_TABLES if name not in existing]
        for name in missing:
            conn.executescript(CORE_TABLES[name])
        if missing:
            conn.commit()
    finally:
        conn.close()

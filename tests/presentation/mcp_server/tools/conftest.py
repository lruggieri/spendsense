"""Shared fixtures for MCP tool tests."""
import os
import sqlite3
import tempfile
from unittest.mock import patch

import pytest

from presentation.mcp_server.context import build_services


def make_db() -> str:
    """Create a temp SQLite DB with the full schema."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS categories (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
        parent_id TEXT DEFAULT '', user_id TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS transactions (
        id TEXT PRIMARY KEY, date TEXT NOT NULL, amount INTEGER NOT NULL,
        description TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'Manual',
        comment TEXT DEFAULT '', user_id TEXT, groups TEXT DEFAULT '[]',
        updated_at TEXT, mail_id TEXT, currency TEXT NOT NULL DEFAULT 'JPY',
        created_at TEXT NOT NULL DEFAULT (datetime('now')), fetcher_id TEXT,
        encryption_version INTEGER NOT NULL DEFAULT 0)""")
    c.execute("""CREATE TABLE IF NOT EXISTS manual_assignments (
        tx_id TEXT PRIMARY KEY, category_id TEXT NOT NULL, user_id TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS regexps (
        id TEXT PRIMARY KEY, raw TEXT NOT NULL, name TEXT NOT NULL DEFAULT '',
        internal_category TEXT NOT NULL, user_id TEXT,
        order_index INTEGER NOT NULL DEFAULT 0, visual_description TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS groups (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, user_id TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS user_settings (
        user_id TEXT PRIMARY KEY, display_language TEXT DEFAULT 'en',
        default_currency TEXT DEFAULT 'JPY', browser_settings TEXT,
        created_at TEXT, updated_at TEXT, llm_call_timestamps TEXT DEFAULT '[]')""")
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def svcs_and_path():
    path = make_db()
    with patch(
        "infrastructure.persistence.sqlite.factory.SQLiteDataSourceFactory.get_embedding_datasource",
        return_value=None,
    ):
        yield build_services(path, "u@x.com", None), path
    os.remove(path)

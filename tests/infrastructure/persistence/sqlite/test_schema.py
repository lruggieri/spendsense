"""Tests for core table creation on a brand-new (fresh install) database."""

import os
import sqlite3
import tempfile

import pytest

from application.services.category_service import CategoryService
from application.services.fetcher_service import FetcherService
from application.services.group_service import GroupService
from application.services.pattern_service import PatternService
from application.services.transaction_service import TransactionService
from application.services.user_settings_service import UserSettingsService
from infrastructure.persistence.sqlite.factory import SQLiteDataSourceFactory
from infrastructure.persistence.sqlite.repositories.category_repository import (
    SQLiteCategoryDataSource,
)
from infrastructure.persistence.sqlite.repositories.fetcher_repository import (
    SQLiteFetcherDataSource,
)
from infrastructure.persistence.sqlite.repositories.group_repository import SQLiteGroupDataSource
from infrastructure.persistence.sqlite.repositories.regexp_repository import (
    SQLiteRegexpDataSource,
)
from infrastructure.persistence.sqlite.schema import CORE_TABLES, ensure_core_tables

USER_ID = "fresh@example.com"


@pytest.fixture
def fresh_db_path():
    """Path to a database file that does not exist yet (in a not-yet-created dir)."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield os.path.join(tmp_dir, "data", "transactions.db")


def _tables(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


def _indexes(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    finally:
        conn.close()


class TestEnsureCoreTables:
    def test_creates_all_core_tables_and_indexes(self, fresh_db_path):
        ensure_core_tables(fresh_db_path)

        assert set(CORE_TABLES) <= _tables(fresh_db_path)
        assert {
            "idx_categories_user_id",
            "idx_regexps_order",
            "idx_groups_user_id",
            "idx_fetchers_user_id",
            "idx_fetchers_enabled",
            "idx_fetchers_group_version",
            "idx_fetchers_enabled_per_group",
            "idx_category_id",
        } <= _indexes(fresh_db_path)

    def test_is_idempotent_and_keeps_data(self, fresh_db_path):
        ensure_core_tables(fresh_db_path)
        conn = sqlite3.connect(fresh_db_path)
        conn.execute(
            "INSERT INTO groups (id, name, user_id) VALUES ('g1', 'Trip', ?)", (USER_ID,)
        )
        conn.commit()
        conn.close()

        ensure_core_tables(fresh_db_path)

        conn = sqlite3.connect(fresh_db_path)
        assert conn.execute("SELECT name FROM groups").fetchall() == [("Trip",)]
        conn.close()

    def test_never_alters_an_existing_table(self, fresh_db_path):
        """Existing databases keep their own table definitions; only missing tables are added."""
        os.makedirs(os.path.dirname(fresh_db_path))
        conn = sqlite3.connect(fresh_db_path)
        conn.execute("CREATE TABLE regexps (id TEXT PRIMARY KEY, legacy_col TEXT)")
        conn.commit()
        conn.close()

        ensure_core_tables(fresh_db_path)

        conn = sqlite3.connect(fresh_db_path)
        columns = [r[1] for r in conn.execute("PRAGMA table_info(regexps)")]
        conn.close()
        assert columns == ["id", "legacy_col"]
        assert "idx_regexps_order" not in _indexes(fresh_db_path)
        assert {"categories", "groups", "fetchers", "manual_assignments"} <= _tables(fresh_db_path)

    def test_only_one_enabled_version_per_fetcher_group(self, fresh_db_path):
        ensure_core_tables(fresh_db_path)
        conn = sqlite3.connect(fresh_db_path)
        insert = (
            "INSERT INTO fetchers (id, user_id, name, from_emails, amount_pattern, created_at,"
            " updated_at, group_id, version, enabled) VALUES (?, ?, 'f', '[]', 'x', 'now', 'now',"
            " 'grp', ?, ?)"
        )
        conn.execute(insert, ("v1", USER_ID, 1, 0))
        conn.execute(insert, ("v2", USER_ID, 2, 1))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(insert, ("v3", USER_ID, 3, 1))
        conn.close()


@pytest.mark.parametrize(
    "repository",
    [SQLiteCategoryDataSource, SQLiteRegexpDataSource, SQLiteGroupDataSource, SQLiteFetcherDataSource],
)
def test_each_repository_bootstraps_a_fresh_database(fresh_db_path, repository):
    repository(fresh_db_path, USER_ID)
    assert set(CORE_TABLES) <= _tables(fresh_db_path)


class TestFreshInstall:
    """The application services work against a database that has never been set up."""

    def _services(self, db_path):
        factory = SQLiteDataSourceFactory(db_path, USER_ID)
        category = CategoryService(USER_ID, factory.get_category_datasource(), db_path=db_path)
        settings = UserSettingsService(
            USER_ID, factory.get_user_settings_datasource(), db_path=db_path
        )
        transactions = TransactionService(
            USER_ID,
            factory.get_transaction_datasource(),
            factory.get_manual_assignment_datasource(),
            category,
            settings,
            db_path=db_path,
        )
        return {
            "category": category,
            "pattern": PatternService(
                USER_ID, factory.get_regexp_datasource(), category, db_path=db_path
            ),
            "group": GroupService(
                USER_ID, factory.get_group_datasource(), transactions, db_path=db_path
            ),
            "fetcher": FetcherService(
                USER_ID, factory.get_fetcher_datasource(), settings, db_path=db_path
            ),
        }

    def test_create_and_delete_entities_on_a_fresh_database(self, fresh_db_path):
        services = self._services(fresh_db_path)

        assert services["category"].count_categories() == 0
        ok, err, food_id = services["category"].create_category("Food")
        assert ok, err

        ok, err, _ = services["pattern"].create_pattern(
            [{"operator": "OR", "keyword": "MARKET"}], food_id, "Market"
        )
        assert ok, err
        assert services["pattern"].count_patterns() == 1

        ok, err, _ = services["group"].create_group("Trip")
        assert ok, err
        assert [g.name for g in services["group"].get_all_groups()] == ["Trip"]

        ok, err, _ = services["fetcher"].create_fetcher(
            name="Bank",
            from_emails=["alerts@bank.example"],
            subject_filter="",
            amount_pattern=r"Amount: (\d+)",
            merchant_pattern=r"Merchant: (.+)",
            default_currency="USD",
        )
        assert ok, err
        assert services["fetcher"].count_fetchers() == 1

        # Deleting a category consults regexps and manual_assignments too.
        ok, err = services["category"].delete_category(food_id)
        assert not ok
        assert "regex pattern" in err
        ok, err, other_id = services["category"].create_category("Other")
        assert ok, err
        ok, err = services["category"].delete_category(other_id)
        assert ok, err

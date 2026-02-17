"""Tests for the SQLite datasource factory."""
import os
import sqlite3
import tempfile
import unittest

from infrastructure.persistence.sqlite.factory import SQLiteDataSourceFactory
from infrastructure.persistence.sqlite.repositories.category_repository import SQLiteCategoryDataSource
from infrastructure.persistence.sqlite.repositories.transaction_repository import SQLiteTransactionDataSource
from infrastructure.persistence.sqlite.repositories.manual_assignment_repository import SQLiteManualAssignmentDataSource
from infrastructure.persistence.sqlite.repositories.regexp_repository import SQLiteRegexpDataSource
from infrastructure.persistence.sqlite.repositories.session_repository import SQLiteSessionDataSource
from infrastructure.persistence.sqlite.repositories.user_settings_repository import SQLiteUserSettingsDataSource
from infrastructure.persistence.sqlite.repositories.fetcher_repository import SQLiteFetcherDataSource
from infrastructure.persistence.sqlite.repositories.group_repository import SQLiteGroupDataSource
from infrastructure.persistence.sqlite.repositories.embedding_repository import SQLiteEmbeddingDataSource


class TestSQLiteDataSourceFactory(unittest.TestCase):
    """Tests for SQLiteDataSourceFactory instance creation and caching."""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.db_path = self.temp_db.name
        self.temp_db.close()

        self.user_id = "test_user"
        self.factory = SQLiteDataSourceFactory(self.db_path, self.user_id)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_init_stores_db_path_and_user_id(self):
        """Factory should store db_path and user_id."""
        self.assertEqual(self.factory.db_path, self.db_path)
        self.assertEqual(self.factory.user_id, self.user_id)

    def test_get_category_datasource_returns_correct_type(self):
        """get_category_datasource should return SQLiteCategoryDataSource."""
        ds = self.factory.get_category_datasource()
        self.assertIsInstance(ds, SQLiteCategoryDataSource)

    def test_get_transaction_datasource_returns_correct_type(self):
        """get_transaction_datasource should return SQLiteTransactionDataSource."""
        ds = self.factory.get_transaction_datasource()
        self.assertIsInstance(ds, SQLiteTransactionDataSource)

    def test_get_manual_assignment_datasource_returns_correct_type(self):
        """get_manual_assignment_datasource should return SQLiteManualAssignmentDataSource."""
        ds = self.factory.get_manual_assignment_datasource()
        self.assertIsInstance(ds, SQLiteManualAssignmentDataSource)

    def test_get_regexp_datasource_returns_correct_type(self):
        """get_regexp_datasource should return SQLiteRegexpDataSource."""
        ds = self.factory.get_regexp_datasource()
        self.assertIsInstance(ds, SQLiteRegexpDataSource)

    def test_get_session_datasource_returns_correct_type(self):
        """get_session_datasource should return SQLiteSessionDataSource."""
        ds = self.factory.get_session_datasource()
        self.assertIsInstance(ds, SQLiteSessionDataSource)

    def test_get_user_settings_datasource_returns_correct_type(self):
        """get_user_settings_datasource should return SQLiteUserSettingsDataSource."""
        ds = self.factory.get_user_settings_datasource()
        self.assertIsInstance(ds, SQLiteUserSettingsDataSource)

    def test_get_fetcher_datasource_returns_correct_type(self):
        """get_fetcher_datasource should return SQLiteFetcherDataSource."""
        ds = self.factory.get_fetcher_datasource()
        self.assertIsInstance(ds, SQLiteFetcherDataSource)

    def test_get_group_datasource_returns_correct_type(self):
        """get_group_datasource should return SQLiteGroupDataSource."""
        ds = self.factory.get_group_datasource()
        self.assertIsInstance(ds, SQLiteGroupDataSource)

    def test_get_embedding_datasource_returns_correct_type(self):
        """get_embedding_datasource should return SQLiteEmbeddingDataSource."""
        ds = self.factory.get_embedding_datasource()
        self.assertIsInstance(ds, SQLiteEmbeddingDataSource)

    def test_datasource_caching(self):
        """Calling the same getter twice should return the same instance."""
        ds1 = self.factory.get_category_datasource()
        ds2 = self.factory.get_category_datasource()
        self.assertIs(ds1, ds2)

    def test_different_datasources_are_different(self):
        """Different getters should return different instances."""
        cat_ds = self.factory.get_category_datasource()
        tx_ds = self.factory.get_transaction_datasource()
        self.assertIsNot(cat_ds, tx_ds)

    def test_cache_is_independent_per_factory(self):
        """Two factories should have independent caches."""
        factory2 = SQLiteDataSourceFactory(self.db_path, "other_user")
        ds1 = self.factory.get_category_datasource()
        ds2 = factory2.get_category_datasource()
        self.assertIsNot(ds1, ds2)


if __name__ == '__main__':
    unittest.main()

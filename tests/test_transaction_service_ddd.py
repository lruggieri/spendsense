"""
Tests for TransactionService (application/services/transaction_service.py).

Tests cover:
- CRUD operations (get, add, update)
- Filtering by category, date, category_source, transaction_source, UNKNOWN
- Transaction sources
- Category assignment (single and bulk)
- Last transaction date
- Auto-classification with classifier mock
"""

import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from application.services.category_service import CategoryService
from application.services.transaction_service import TransactionService
from application.services.user_settings_service import UserSettingsService
from domain.entities.category_tree import UNKNOWN_CATEGORY_ID
from domain.entities.transaction import CategorySource, Transaction
from infrastructure.persistence.sqlite.repositories.category_repository import (
    SQLiteCategoryDataSource,
)
from infrastructure.persistence.sqlite.repositories.manual_assignment_repository import (
    SQLiteManualAssignmentDataSource,
)
from infrastructure.persistence.sqlite.repositories.transaction_repository import (
    SQLiteTransactionDataSource,
)
from infrastructure.persistence.sqlite.repositories.user_settings_repository import (
    SQLiteUserSettingsDataSource,
)

USER_ID = "test_user"


class TestTransactionServiceDDD(unittest.TestCase):
    """Test suite for TransactionService with real SQLite database."""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.db_path = self.temp_db.name
        self.temp_db.close()
        os.environ["DATABASE_PATH"] = self.db_path

        # Create all needed tables
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""CREATE TABLE IF NOT EXISTS categories (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL,
            parent_id TEXT DEFAULT '', user_id TEXT)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS transactions (
            id TEXT PRIMARY KEY, date TEXT NOT NULL, amount INTEGER NOT NULL,
            description TEXT NOT NULL, source TEXT NOT NULL, comment TEXT DEFAULT '',
            user_id TEXT, groups TEXT DEFAULT '[]', updated_at TEXT,
            mail_id TEXT, currency TEXT NOT NULL DEFAULT 'JPY',
            created_at TEXT NOT NULL DEFAULT (datetime('now')), fetcher_id TEXT,
            encryption_version INTEGER NOT NULL DEFAULT 0)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS manual_assignments (
            tx_id TEXT PRIMARY KEY, category_id TEXT NOT NULL, user_id TEXT)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS regexps (
            id TEXT PRIMARY KEY, raw TEXT NOT NULL, name TEXT NOT NULL,
            internal_category TEXT NOT NULL, user_id TEXT,
            order_index INTEGER NOT NULL DEFAULT 0, visual_description TEXT)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS groups (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, user_id TEXT NOT NULL)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS embeddings (
            tx_id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
            embedding BLOB NOT NULL, description_hash TEXT NOT NULL,
            created_at TEXT NOT NULL)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS user_settings (
            user_id TEXT PRIMARY KEY, display_language TEXT DEFAULT 'en',
            default_currency TEXT DEFAULT 'USD', browser_settings TEXT,
            created_at TEXT, updated_at TEXT, llm_call_timestamps TEXT DEFAULT '[]')""")

        # Seed categories
        cursor.execute(
            "INSERT INTO categories (id, name, description, parent_id, user_id) VALUES (?, ?, ?, ?, ?)",
            ("food", "Food", "Food expenses", "", USER_ID),
        )
        cursor.execute(
            "INSERT INTO categories (id, name, description, parent_id, user_id) VALUES (?, ?, ?, ?, ?)",
            ("transport", "Transport", "Transport expenses", "", USER_ID),
        )
        cursor.execute(
            "INSERT INTO categories (id, name, description, parent_id, user_id) VALUES (?, ?, ?, ?, ?)",
            ("restaurant", "Restaurant", "Restaurant expenses", "food", USER_ID),
        )

        conn.commit()
        conn.close()

        # Create datasource instances
        self.tx_ds = SQLiteTransactionDataSource(self.db_path, user_id=USER_ID)
        self.ma_ds = SQLiteManualAssignmentDataSource(self.db_path, user_id=USER_ID)
        self.cat_ds = SQLiteCategoryDataSource(self.db_path, user_id=USER_ID)
        self.us_ds = SQLiteUserSettingsDataSource(self.db_path, user_id=USER_ID)

        self.category_service = CategoryService(USER_ID, self.cat_ds, db_path=self.db_path)
        self.user_settings_service = UserSettingsService(USER_ID, self.us_ds, db_path=self.db_path)

        self.service = TransactionService(
            user_id=USER_ID,
            transaction_datasource=self.tx_ds,
            manual_assignment_datasource=self.ma_ds,
            category_service=self.category_service,
            user_settings_service=self.user_settings_service,
            db_path=self.db_path,
        )

    def tearDown(self):
        if "DATABASE_PATH" in os.environ:
            del os.environ["DATABASE_PATH"]
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    # --- Helper methods ---

    def _add_sample_transactions(self):
        """Add sample transactions to the database for testing."""
        txs = [
            Transaction(
                id="tx1",
                date=datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
                amount=1000,
                description="Sushi Lunch",
                category="food",
                source="Sony Bank",
                currency="JPY",
                category_source=CategorySource.MANUAL,
                created_at=datetime.now(timezone.utc),
            ),
            Transaction(
                id="tx2",
                date=datetime(2025, 2, 20, 14, 30, 0, tzinfo=timezone.utc),
                amount=500,
                description="Train ticket",
                category="transport",
                source="Amazon",
                currency="JPY",
                category_source=CategorySource.REGEXP,
                created_at=datetime.now(timezone.utc),
            ),
            Transaction(
                id="tx3",
                date=datetime(2025, 3, 10, 9, 0, 0, tzinfo=timezone.utc),
                amount=2000,
                description="Mystery purchase",
                category="",
                source="Sony Bank",
                currency="JPY",
                category_source=CategorySource.SIMILARITY,
                created_at=datetime.now(timezone.utc),
            ),
        ]
        self.tx_ds.add_transactions_batch(txs)
        # Add manual assignments for tx1
        self.ma_ds.add_assignment("tx1", "food")

    # --- get_all_transactions ---

    def test_get_all_transactions_empty(self):
        """Test getting transactions from empty database."""
        result = self.service.get_all_transactions()
        self.assertEqual(len(result), 0)

    def test_get_all_transactions(self):
        """Test getting all transactions."""
        self._add_sample_transactions()
        result = self.service.get_all_transactions()
        self.assertEqual(len(result), 3)

    # --- get_all_transactions_filtered ---

    def test_filter_by_category(self):
        """Test filtering by category including child categories.

        Note: The SQLite datasource does not store category - it's assigned
        by the classifier at runtime. So we must set categories on the
        transactions after loading, or test the filter logic by inserting
        transactions that have been classified already.
        We test the filter by directly creating Transaction objects with
        categories set, and using a mock datasource that returns them.
        Instead, we use the UNKNOWN category filter which works on
        transactions without categories (the default from DB).
        For category filtering, we test via get_all_transactions_filtered
        with transactions that have NO category, which should show up under UNKNOWN.
        """
        self._add_sample_transactions()
        # Since the datasource returns category="" for all transactions,
        # filtering by "food" (a known category) should return nothing
        # because no loaded transaction has category="food" set on it
        result = self.service.get_all_transactions_filtered(category_id="food")
        self.assertEqual(len(result), 0)

        # But filtering by UNKNOWN should find all (since all have category="")
        result = self.service.get_all_transactions_filtered(category_id=UNKNOWN_CATEGORY_ID)
        self.assertEqual(len(result), 3)

    def test_filter_by_date_range(self):
        """Test filtering by date range."""
        self._add_sample_transactions()
        result = self.service.get_all_transactions_filtered(
            from_date="2025-02-01", to_date="2025-02-28"
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "tx2")

    def test_filter_by_category_source(self):
        """Test filtering by category source.

        Note: category_source is not persisted in the database - it is
        assigned at runtime by the classifier. So transactions loaded
        from the DB will have category_source=None.
        We test that filtering by category_source works on in-memory
        transactions where it has been set.
        """
        self._add_sample_transactions()
        # Since category_source is not stored in DB, all loaded transactions
        # will have category_source=None, so filtering returns nothing
        result = self.service.get_all_transactions_filtered(category_source="manual")
        self.assertEqual(len(result), 0)

        # Filter with no category_source should return all
        result = self.service.get_all_transactions_filtered()
        self.assertEqual(len(result), 3)

    def test_filter_by_transaction_source(self):
        """Test filtering by transaction source."""
        self._add_sample_transactions()
        result = self.service.get_all_transactions_filtered(transaction_source="Sony Bank")
        self.assertEqual(len(result), 2)

    def test_filter_by_unknown_category(self):
        """Test filtering by UNKNOWN category shows uncategorized transactions."""
        self._add_sample_transactions()
        result = self.service.get_all_transactions_filtered(category_id=UNKNOWN_CATEGORY_ID)
        # tx3 has category="" which is not in valid categories
        unknown_ids = [tx.id for tx in result]
        self.assertIn("tx3", unknown_ids)

    def test_filter_results_sorted_by_date_desc(self):
        """Test that filtered results are sorted by date descending."""
        self._add_sample_transactions()
        result = self.service.get_all_transactions_filtered()
        self.assertEqual(len(result), 3)
        # Most recent first
        self.assertEqual(result[0].id, "tx3")
        self.assertEqual(result[1].id, "tx2")
        self.assertEqual(result[2].id, "tx1")

    # --- get_all_transactions_filtered with pre-classified transactions ---

    def test_filter_preclassified_by_category_source(self):
        """Test filtering pre-classified transactions by category_source.

        This tests the scenario where the caller classifies transactions first,
        then passes them to get_all_transactions_filtered. Without the
        `transactions` parameter, category_source filtering would fail because
        DB-loaded transactions have category_source=None.
        """
        self._add_sample_transactions()

        # Simulate classification: load txs and set category_source by ID
        all_txs = self.service.get_all_transactions()
        tx_by_id = {tx.id: tx for tx in all_txs}
        tx_by_id["tx1"].category_source = CategorySource.MANUAL
        tx_by_id["tx1"].category = "food"
        tx_by_id["tx2"].category_source = CategorySource.REGEXP
        tx_by_id["tx2"].category = "transport"
        tx_by_id["tx3"].category_source = CategorySource.SIMILARITY
        tx_by_id["tx3"].category = "food"

        # Filter by category_source="regexp" using pre-classified list
        result = self.service.get_all_transactions_filtered(
            category_source="regexp", transactions=all_txs
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "tx2")

        # Filter by category_source="manual"
        result = self.service.get_all_transactions_filtered(
            category_source="manual", transactions=all_txs
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "tx1")

    def test_filter_preclassified_by_category(self):
        """Test filtering pre-classified transactions by category.

        Categories are runtime-computed. Passing pre-classified transactions
        allows category filtering to work correctly.
        """
        self._add_sample_transactions()

        # Simulate classification
        all_txs = self.service.get_all_transactions()
        all_txs[0].category = "food"
        all_txs[1].category = "transport"
        all_txs[2].category = "restaurant"  # child of food

        # Filter by "food" should include "food" and its child "restaurant"
        result = self.service.get_all_transactions_filtered(
            category_id="food", transactions=all_txs
        )
        result_ids = [tx.id for tx in result]
        self.assertIn("tx1", result_ids)
        self.assertIn("tx3", result_ids)
        self.assertNotIn("tx2", result_ids)

    def test_filter_preclassified_combined(self):
        """Test combining category_source + date filters on pre-classified transactions."""
        self._add_sample_transactions()

        all_txs = self.service.get_all_transactions()
        tx_by_id = {tx.id: tx for tx in all_txs}
        tx_by_id["tx1"].category_source = CategorySource.MANUAL
        tx_by_id["tx2"].category_source = CategorySource.REGEXP
        tx_by_id["tx3"].category_source = CategorySource.REGEXP

        # Filter: regexp + date range that includes only tx3 (March)
        result = self.service.get_all_transactions_filtered(
            category_source="regexp",
            from_date="2025-03-01",
            to_date="2025-03-31",
            transactions=all_txs,
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "tx3")

    # --- get_transaction_sources ---

    def test_get_transaction_sources(self):
        """Test getting distinct transaction sources."""
        self._add_sample_transactions()
        sources = self.service.get_transaction_sources()
        self.assertEqual(sorted(sources), ["Amazon", "Sony Bank"])

    def test_get_transaction_sources_empty(self):
        """Test getting sources from empty database."""
        sources = self.service.get_transaction_sources()
        self.assertEqual(sources, [])

    # --- get_transactions_by_source ---

    def test_get_transactions_by_source(self):
        """Test getting transactions by source."""
        self._add_sample_transactions()
        result = self.service.get_transactions_by_source("Sony Bank")
        self.assertEqual(len(result), 2)

    # --- add_new_transaction ---

    def test_add_new_transaction_success(self):
        """Test adding a new transaction successfully."""
        success, error = self.service.add_new_transaction(
            date_str="2025-06-15", amount="1500", description="Coffee shop", currency="JPY"
        )
        self.assertTrue(success)
        self.assertEqual(error, "")

        # Verify it was added
        txs = self.service.get_all_transactions()
        self.assertEqual(len(txs), 1)
        self.assertEqual(txs[0].description, "Coffee shop")
        self.assertEqual(txs[0].source, "Manual")

    def test_add_new_transaction_missing_fields(self):
        """Test adding transaction with missing required fields."""
        success, error = self.service.add_new_transaction(
            date_str="", amount="1000", description="Test"
        )
        self.assertFalse(success)
        self.assertIn("required", error.lower())

        success, error = self.service.add_new_transaction(
            date_str="2025-01-01", amount="", description="Test"
        )
        self.assertFalse(success)

        success, error = self.service.add_new_transaction(
            date_str="2025-01-01", amount="1000", description=""
        )
        self.assertFalse(success)

    def test_add_new_transaction_invalid_currency(self):
        """Test adding transaction with unsupported currency."""
        success, error = self.service.add_new_transaction(
            date_str="2025-06-15",
            amount="1500",
            description="Test purchase",
            currency="INVALID_CURRENCY",
        )
        self.assertFalse(success)
        self.assertIn("Unsupported currency", error)

    def test_add_new_transaction_with_category(self):
        """Test adding transaction with explicit category creates manual assignment."""
        success, error = self.service.add_new_transaction(
            date_str="2025-06-15",
            amount="1500",
            description="Sushi dinner",
            category="food",
            currency="JPY",
        )
        self.assertTrue(success)
        self.assertEqual(error, "")

        # Verify manual assignment was created
        txs = self.service.get_all_transactions()
        self.assertEqual(len(txs), 1)
        assignments = self.ma_ds.get_assignments()
        self.assertIn(txs[0].id, assignments)
        self.assertEqual(assignments[txs[0].id], "food")

    def test_add_new_transaction_auto_classify(self):
        """Test adding transaction with classifier for auto-classification."""
        mock_classifier = MagicMock()
        mock_classifier.classify.return_value = ("transport", CategorySource.REGEXP)

        success, error = self.service.add_new_transaction(
            date_str="2025-06-15",
            amount="500",
            description="Train ticket",
            currency="JPY",
            classifier=mock_classifier,
        )
        self.assertTrue(success)
        mock_classifier.classify.assert_called_once()

    def test_add_new_transaction_default_currency(self):
        """Test that default currency is used when none provided."""
        success, error = self.service.add_new_transaction(
            date_str="2025-06-15", amount="1500", description="Coffee shop"
        )
        self.assertTrue(success)

        txs = self.service.get_all_transactions()
        self.assertEqual(len(txs), 1)
        # Default should be USD from user settings defaults
        self.assertEqual(txs[0].currency, "USD")

    # --- update_transaction ---

    def test_update_transaction_success(self):
        """Test updating a transaction successfully."""
        self._add_sample_transactions()
        success, error = self.service.update_transaction(
            tx_id="tx1",
            date_str="2025-01-15",
            amount="2000",
            description="Updated description",
            comment="Updated comment",
            currency="JPY",
        )
        self.assertTrue(success)
        self.assertEqual(error, "")

        # Verify update
        all_txs = {tx.id: tx for tx in self.service.get_all_transactions()}
        tx = all_txs.get("tx1")
        self.assertIsNotNone(tx)
        self.assertEqual(tx.description, "Updated description")
        self.assertEqual(tx.amount, 2000)

    def test_update_transaction_not_found(self):
        """Test updating a nonexistent transaction."""
        success, error = self.service.update_transaction(
            tx_id="nonexistent",
            date_str="2025-01-15",
            amount="2000",
            description="Test",
            comment="",
        )
        self.assertFalse(success)
        self.assertIn("not found", error.lower())

    def test_update_transaction_description_change_invalidates_embedding(self):
        """Test that changing description invalidates embedding cache."""
        self._add_sample_transactions()
        mock_embedding_ds = MagicMock()

        success, error = self.service.update_transaction(
            tx_id="tx1",
            date_str="2025-01-15",
            amount="1000",
            description="Completely new description",
            comment="",
            currency="JPY",
            embedding_datasource=mock_embedding_ds,
        )
        self.assertTrue(success)
        mock_embedding_ds.invalidate_embedding.assert_called_once_with("tx1")

    def test_update_transaction_same_description_no_invalidation(self):
        """Test that keeping same description does not invalidate embedding."""
        self._add_sample_transactions()
        mock_embedding_ds = MagicMock()

        success, error = self.service.update_transaction(
            tx_id="tx1",
            date_str="2025-01-15",
            amount="1000",
            description="Sushi Lunch",  # Same as original
            comment="",
            currency="JPY",
            embedding_datasource=mock_embedding_ds,
        )
        self.assertTrue(success)
        mock_embedding_ds.invalidate_embedding.assert_not_called()

    def test_update_encrypted_transaction_rejected(self):
        """Test that updating an encrypted transaction is rejected."""
        self._add_sample_transactions()
        # Mark tx1 as encrypted in the database
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE transactions SET encryption_version = 1 WHERE id = ? AND user_id = ?",
            ("tx1", USER_ID),
        )
        conn.commit()
        conn.close()

        success, error = self.service.update_transaction(
            tx_id="tx1",
            date_str="2025-01-15",
            amount="2000",
            description="Should not update",
            comment="",
            currency="JPY",
        )
        self.assertFalse(success)
        self.assertIn("Encrypted", error)

    # --- update_comment ---

    def test_update_comment_success(self):
        """Test updating only the comment field."""
        self._add_sample_transactions()
        success, error = self.service.update_comment("tx1", "New comment")
        self.assertTrue(success)
        self.assertEqual(error, "")

        # Verify comment was updated
        all_txs = {tx.id: tx for tx in self.service.get_all_transactions()}
        self.assertEqual(all_txs["tx1"].comment, "New comment")

    def test_update_comment_not_found(self):
        """Test updating comment for nonexistent transaction."""
        success, error = self.service.update_comment("nonexistent", "test")
        self.assertFalse(success)
        self.assertIn("not found", error.lower())

    def test_update_comment_empty_string(self):
        """Test clearing comment with empty string."""
        self._add_sample_transactions()
        success, error = self.service.update_comment("tx1", "")
        self.assertTrue(success)

        all_txs = {tx.id: tx for tx in self.service.get_all_transactions()}
        self.assertEqual(all_txs["tx1"].comment, "")

    def test_update_comment_missing_tx_id(self):
        """Test updating comment with empty tx_id."""
        success, error = self.service.update_comment("", "test")
        self.assertFalse(success)
        self.assertIn("required", error.lower())

    # --- assign_category ---

    def test_assign_category(self):
        """Test assigning a category to a transaction."""
        self._add_sample_transactions()
        self.service.assign_category("tx3", "food")

        assignments = self.ma_ds.get_assignments()
        self.assertEqual(assignments["tx3"], "food")

    # --- assign_categories_bulk ---

    def test_assign_categories_bulk_add(self):
        """Test bulk adding category assignments."""
        self._add_sample_transactions()
        self.service.assign_categories_bulk({"tx2": "food", "tx3": "transport"})

        assignments = self.ma_ds.get_assignments()
        self.assertEqual(assignments["tx2"], "food")
        self.assertEqual(assignments["tx3"], "transport")

    def test_assign_categories_bulk_remove(self):
        """Test bulk removing category assignments (empty string)."""
        self._add_sample_transactions()
        # tx1 already has a manual assignment
        self.service.assign_categories_bulk({"tx1": ""})

        assignments = self.ma_ds.get_assignments()
        self.assertNotIn("tx1", assignments)

    def test_assign_categories_bulk_mixed(self):
        """Test bulk with both adds and removes."""
        self._add_sample_transactions()
        self.service.assign_categories_bulk(
            {"tx1": "", "tx2": "food", "tx3": "transport"}  # Remove  # Add  # Add
        )

        assignments = self.ma_ds.get_assignments()
        self.assertNotIn("tx1", assignments)
        self.assertEqual(assignments["tx2"], "food")
        self.assertEqual(assignments["tx3"], "transport")

    # --- get_last_transaction_date ---

    def test_get_last_transaction_date(self):
        """Test getting the last transaction date."""
        self._add_sample_transactions()
        last_date = self.service.get_last_transaction_date()
        self.assertIsNotNone(last_date)
        # tx3 is the most recent (March 10)
        self.assertEqual(last_date.year, 2025)
        self.assertEqual(last_date.month, 3)
        self.assertEqual(last_date.day, 10)

    def test_get_last_transaction_date_empty(self):
        """Test getting last date from empty database."""
        last_date = self.service.get_last_transaction_date()
        self.assertIsNone(last_date)

    # --- categories property ---

    def test_categories_property(self):
        """Test that categories property returns categories from service."""
        categories = self.service.categories
        self.assertIn("food", categories)
        self.assertIn("transport", categories)
        self.assertIn("restaurant", categories)


if __name__ == "__main__":
    unittest.main()

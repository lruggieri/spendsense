"""
Tests for GroupService (application/services/group_service.py).

Tests cover:
- get_all_groups
- get_group_by_id
- create_group (success, empty name)
- update_group (success, not found, empty name)
- delete_group (success, not found, cascade)
- add/remove transaction to/from group
- bulk add/remove transactions
"""

import os
import tempfile
import sqlite3
import unittest
from datetime import datetime, timezone

from application.services.group_service import GroupService
from application.services.transaction_service import TransactionService
from application.services.category_service import CategoryService
from application.services.user_settings_service import UserSettingsService
from domain.entities.transaction import Transaction
from infrastructure.persistence.sqlite.repositories.transaction_repository import SQLiteTransactionDataSource
from infrastructure.persistence.sqlite.repositories.manual_assignment_repository import SQLiteManualAssignmentDataSource
from infrastructure.persistence.sqlite.repositories.category_repository import SQLiteCategoryDataSource
from infrastructure.persistence.sqlite.repositories.group_repository import SQLiteGroupDataSource
from infrastructure.persistence.sqlite.repositories.user_settings_repository import SQLiteUserSettingsDataSource


USER_ID = "test_user"


class TestGroupService(unittest.TestCase):
    """Test suite for GroupService with real SQLite database."""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.db_path = self.temp_db.name
        self.temp_db.close()
        os.environ['DATABASE_PATH'] = self.db_path

        # Create all needed tables
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS categories (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL,
            parent_id TEXT DEFAULT '', user_id TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS transactions (
            id TEXT PRIMARY KEY, date TEXT NOT NULL, amount INTEGER NOT NULL,
            description TEXT NOT NULL, source TEXT NOT NULL, comment TEXT DEFAULT '',
            user_id TEXT, groups TEXT DEFAULT '[]', updated_at TEXT,
            mail_id TEXT, currency TEXT NOT NULL DEFAULT 'JPY',
            created_at TEXT NOT NULL DEFAULT (datetime('now')), fetcher_id TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS manual_assignments (
            tx_id TEXT PRIMARY KEY, category_id TEXT NOT NULL, user_id TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS regexps (
            id TEXT PRIMARY KEY, raw TEXT NOT NULL, name TEXT NOT NULL,
            internal_category TEXT NOT NULL, user_id TEXT,
            order_index INTEGER NOT NULL DEFAULT 0, visual_description TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS groups (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, user_id TEXT NOT NULL)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS embeddings (
            tx_id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
            embedding BLOB NOT NULL, description_hash TEXT NOT NULL,
            created_at TEXT NOT NULL)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS user_settings (
            user_id TEXT PRIMARY KEY, display_language TEXT DEFAULT 'en',
            default_currency TEXT DEFAULT 'USD', browser_settings TEXT,
            created_at TEXT, updated_at TEXT, llm_call_timestamps TEXT DEFAULT '[]')''')

        # Seed a category
        cursor.execute(
            "INSERT INTO categories (id, name, description, parent_id, user_id) VALUES (?, ?, ?, ?, ?)",
            ("food", "Food", "Food expenses", "", USER_ID))

        conn.commit()
        conn.close()

        # Create datasource instances
        self.tx_ds = SQLiteTransactionDataSource(self.db_path, user_id=USER_ID)
        self.ma_ds = SQLiteManualAssignmentDataSource(self.db_path, user_id=USER_ID)
        self.cat_ds = SQLiteCategoryDataSource(self.db_path, user_id=USER_ID)
        self.group_ds = SQLiteGroupDataSource(self.db_path, user_id=USER_ID)
        self.us_ds = SQLiteUserSettingsDataSource(self.db_path, user_id=USER_ID)

        self.category_service = CategoryService(USER_ID, self.cat_ds, db_path=self.db_path)
        self.user_settings_service = UserSettingsService(USER_ID, self.us_ds, db_path=self.db_path)

        self.transaction_service = TransactionService(
            user_id=USER_ID,
            transaction_datasource=self.tx_ds,
            manual_assignment_datasource=self.ma_ds,
            category_service=self.category_service,
            user_settings_service=self.user_settings_service,
            db_path=self.db_path
        )

        self.service = GroupService(
            user_id=USER_ID,
            group_datasource=self.group_ds,
            transaction_service=self.transaction_service,
            db_path=self.db_path
        )

    def tearDown(self):
        if 'DATABASE_PATH' in os.environ:
            del os.environ['DATABASE_PATH']
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    # --- Helper methods ---

    def _get_tx_by_id(self, tx_id: str):
        """Look up a transaction by ID from the datasource."""
        all_txs = self.transaction_service.get_all_transactions()
        return next((tx for tx in all_txs if tx.id == tx_id), None)

    def _add_sample_transactions(self):
        """Add sample transactions for testing."""
        txs = [
            Transaction(id="tx1", date=datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
                        amount=1000, description="Lunch", category="food",
                        source="Test", currency="JPY",
                        created_at=datetime.now(timezone.utc)),
            Transaction(id="tx2", date=datetime(2025, 2, 20, 14, 30, 0, tzinfo=timezone.utc),
                        amount=500, description="Coffee", category="food",
                        source="Test", currency="JPY",
                        created_at=datetime.now(timezone.utc)),
            Transaction(id="tx3", date=datetime(2025, 3, 10, 9, 0, 0, tzinfo=timezone.utc),
                        amount=2000, description="Dinner", category="food",
                        source="Test", currency="JPY",
                        created_at=datetime.now(timezone.utc)),
        ]
        self.tx_ds.add_transactions_batch(txs)

    # --- get_all_groups ---

    def test_get_all_groups_empty(self):
        """Test getting groups from empty database."""
        groups = self.service.get_all_groups()
        self.assertEqual(len(groups), 0)

    def test_get_all_groups(self):
        """Test getting all groups after creating some."""
        self.service.create_group("Trip to Tokyo")
        self.service.create_group("Monthly Budget")
        groups = self.service.get_all_groups()
        self.assertEqual(len(groups), 2)

    # --- get_group_by_id ---

    def test_get_group_by_id_found(self):
        """Test finding a group by ID."""
        success, error, group_id = self.service.create_group("Trip to Tokyo")
        self.assertTrue(success)

        group = self.service.get_group_by_id(group_id)
        self.assertIsNotNone(group)
        self.assertEqual(group.name, "Trip to Tokyo")

    def test_get_group_by_id_not_found(self):
        """Test group not found returns None."""
        group = self.service.get_group_by_id("nonexistent")
        self.assertIsNone(group)

    # --- create_group ---

    def test_create_group_success(self):
        """Test creating a group successfully."""
        success, error, group_id = self.service.create_group("My Group")
        self.assertTrue(success)
        self.assertEqual(error, "")
        self.assertNotEqual(group_id, "")

        # Verify it exists
        group = self.service.get_group_by_id(group_id)
        self.assertIsNotNone(group)
        self.assertEqual(group.name, "My Group")

    def test_create_group_empty_name(self):
        """Test creating a group with empty name fails."""
        success, error, group_id = self.service.create_group("")
        self.assertFalse(success)
        self.assertIn("required", error.lower())
        self.assertEqual(group_id, "")

    def test_create_group_whitespace_name(self):
        """Test creating a group with whitespace-only name fails."""
        success, error, group_id = self.service.create_group("   ")
        self.assertFalse(success)
        self.assertIn("required", error.lower())

    def test_create_group_strips_name(self):
        """Test that group name is trimmed."""
        success, error, group_id = self.service.create_group("  My Group  ")
        self.assertTrue(success)

        group = self.service.get_group_by_id(group_id)
        self.assertEqual(group.name, "My Group")

    # --- update_group ---

    def test_update_group_success(self):
        """Test updating a group name successfully."""
        success, error, group_id = self.service.create_group("Original Name")
        self.assertTrue(success)

        success, error = self.service.update_group(group_id, name="Updated Name")
        self.assertTrue(success)
        self.assertEqual(error, "")

        group = self.service.get_group_by_id(group_id)
        self.assertEqual(group.name, "Updated Name")

    def test_update_group_not_found(self):
        """Test updating a nonexistent group."""
        success, error = self.service.update_group("nonexistent", name="New Name")
        self.assertFalse(success)
        self.assertIn("not found", error.lower())

    def test_update_group_empty_name(self):
        """Test updating a group with empty name fails."""
        success, error, group_id = self.service.create_group("Original")
        self.assertTrue(success)

        success, error = self.service.update_group(group_id, name="")
        self.assertFalse(success)
        self.assertIn("empty", error.lower())

    def test_update_group_no_changes(self):
        """Test updating a group with no changes succeeds."""
        success, error, group_id = self.service.create_group("Original")
        self.assertTrue(success)

        success, error = self.service.update_group(group_id)
        self.assertTrue(success)

    # --- delete_group ---

    def test_delete_group_success(self):
        """Test deleting a group successfully."""
        success, error, group_id = self.service.create_group("To Delete")
        self.assertTrue(success)

        success, error = self.service.delete_group(group_id)
        self.assertTrue(success)
        self.assertEqual(error, "")

        # Verify it's gone
        group = self.service.get_group_by_id(group_id)
        self.assertIsNone(group)

    def test_delete_group_not_found(self):
        """Test deleting a nonexistent group."""
        success, error = self.service.delete_group("nonexistent")
        self.assertFalse(success)
        self.assertIn("not found", error.lower())

    def test_delete_group_cascade(self):
        """Test that deleting a group cascades to remove it from transactions."""
        self._add_sample_transactions()
        success, error, group_id = self.service.create_group("Trip")
        self.assertTrue(success)

        # Add group to transactions
        self.transaction_service.add_group_to_transaction("tx1", group_id)
        self.transaction_service.add_group_to_transaction("tx2", group_id)

        # Verify group is on transactions
        tx1 = self._get_tx_by_id("tx1")
        self.assertIn(group_id, tx1.groups)

        # Delete group with cascade
        success, error = self.service.delete_group(group_id, cascade=True)
        self.assertTrue(success)

        # Verify group is removed from transactions
        tx1 = self._get_tx_by_id("tx1")
        self.assertNotIn(group_id, tx1.groups)
        tx2 = self._get_tx_by_id("tx2")
        self.assertNotIn(group_id, tx2.groups)

    # --- add_transaction_to_group ---

    def test_add_transaction_to_group(self):
        """Test adding a transaction to a group."""
        self._add_sample_transactions()
        success, error, group_id = self.service.create_group("Trip")
        self.assertTrue(success)

        success, error = self.service.add_transaction_to_group("tx1", group_id)
        self.assertTrue(success)
        self.assertEqual(error, "")

        # Verify
        tx1 = self._get_tx_by_id("tx1")
        self.assertIn(group_id, tx1.groups)

    def test_add_transaction_to_nonexistent_group(self):
        """Test adding transaction to nonexistent group."""
        self._add_sample_transactions()
        success, error = self.service.add_transaction_to_group("tx1", "nonexistent")
        self.assertFalse(success)
        self.assertIn("not found", error.lower())

    # --- remove_transaction_from_group ---

    def test_remove_transaction_from_group(self):
        """Test removing a transaction from a group."""
        self._add_sample_transactions()
        success, error, group_id = self.service.create_group("Trip")
        self.assertTrue(success)

        # Add then remove
        self.service.add_transaction_to_group("tx1", group_id)
        success, error = self.service.remove_transaction_from_group("tx1", group_id)
        self.assertTrue(success)

        # Verify
        tx1 = self._get_tx_by_id("tx1")
        self.assertNotIn(group_id, tx1.groups)

    # --- add_transactions_to_group (bulk) ---

    def test_add_transactions_to_group_bulk(self):
        """Test bulk adding transactions to a group."""
        self._add_sample_transactions()
        success, error, group_id = self.service.create_group("Bulk Group")
        self.assertTrue(success)

        success, error, count = self.service.add_transactions_to_group(
            ["tx1", "tx2", "tx3"], group_id)
        self.assertTrue(success)
        self.assertEqual(count, 3)

        # Verify all transactions have the group
        for tx_id in ["tx1", "tx2", "tx3"]:
            tx = self._get_tx_by_id(tx_id)
            self.assertIn(group_id, tx.groups)

    def test_add_transactions_to_nonexistent_group_bulk(self):
        """Test bulk adding transactions to nonexistent group."""
        self._add_sample_transactions()
        success, error, count = self.service.add_transactions_to_group(
            ["tx1", "tx2"], "nonexistent")
        self.assertFalse(success)
        self.assertEqual(count, 0)

    # --- remove_transactions_from_group (bulk) ---

    def test_remove_transactions_from_group_bulk(self):
        """Test bulk removing transactions from a group."""
        self._add_sample_transactions()
        success, error, group_id = self.service.create_group("Bulk Group")
        self.assertTrue(success)

        # Add all
        self.service.add_transactions_to_group(["tx1", "tx2", "tx3"], group_id)

        # Remove some
        success, error, count = self.service.remove_transactions_from_group(
            ["tx1", "tx3"], group_id)
        self.assertTrue(success)
        self.assertEqual(count, 2)

        # Verify tx1 and tx3 don't have the group, but tx2 still does
        tx1 = self._get_tx_by_id("tx1")
        self.assertNotIn(group_id, tx1.groups)
        tx2 = self._get_tx_by_id("tx2")
        self.assertIn(group_id, tx2.groups)
        tx3 = self._get_tx_by_id("tx3")
        self.assertNotIn(group_id, tx3.groups)


if __name__ == '__main__':
    unittest.main()

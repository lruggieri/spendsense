"""
Tests for SQLiteCategoryDataSource CRUD operations.
"""

import unittest
import tempfile
import os
import sqlite3

from infrastructure.persistence.sqlite.repositories.category_repository import SQLiteCategoryDataSource
from infrastructure.persistence.sqlite.repositories.manual_assignment_repository import SQLiteManualAssignmentDataSource
from domain.entities.category import Category


class TestCategoryDataSourceCRUD(unittest.TestCase):
    """Test CRUD operations for category datasource."""

    def setUp(self):
        """Create a temporary database for testing."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.db_path = self.temp_db.name
        self.temp_db.close()

        # Initialize database schema
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE categories (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                parent_id TEXT DEFAULT '',
                user_id TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE manual_assignments (
                tx_id TEXT PRIMARY KEY,
                category_id TEXT NOT NULL,
                user_id TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE regexps (
                id TEXT PRIMARY KEY,
                raw TEXT NOT NULL,
                name TEXT NOT NULL,
                internal_category TEXT NOT NULL,
                user_id TEXT,
                order_index INTEGER NOT NULL DEFAULT 0,
                visual_description TEXT
            )
        """)

        conn.commit()
        conn.close()

        self.user_id = "test_user"
        self.datasource = SQLiteCategoryDataSource(self.db_path, self.user_id)
        self.manual_assignments = SQLiteManualAssignmentDataSource(self.db_path, self.user_id)

    def tearDown(self):
        """Clean up temporary database."""
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_create_category_success(self):
        """Test successful category creation."""
        category = Category("groceries", "Groceries", "Food and groceries", "")
        result = self.datasource.create_category(category)

        self.assertTrue(result)

        # Verify it was created
        retrieved = self.datasource.get_category_by_id("groceries")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.name, "Groceries")
        self.assertEqual(retrieved.description, "Food and groceries")

    def test_create_category_duplicate_id(self):
        """Test that creating a duplicate category ID fails."""
        category1 = Category("groceries", "Groceries", "Food", "")
        category2 = Category("groceries", "Groceries 2", "Food again", "")

        result1 = self.datasource.create_category(category1)
        result2 = self.datasource.create_category(category2)

        self.assertTrue(result1)
        self.assertFalse(result2)

    def test_update_category_name(self):
        """Test updating category name."""
        category = Category("groceries", "Groceries", "Food", "")
        self.datasource.create_category(category)

        result = self.datasource.update_category("groceries", name="Food & Groceries")
        self.assertTrue(result)

        # Verify the update
        retrieved = self.datasource.get_category_by_id("groceries")
        self.assertEqual(retrieved.name, "Food & Groceries")
        self.assertEqual(retrieved.description, "Food")  # Unchanged

    def test_update_category_description(self):
        """Test updating category description."""
        category = Category("groceries", "Groceries", "Food", "")
        self.datasource.create_category(category)

        result = self.datasource.update_category("groceries", description="All food items")
        self.assertTrue(result)

        # Verify the update
        retrieved = self.datasource.get_category_by_id("groceries")
        self.assertEqual(retrieved.name, "Groceries")  # Unchanged
        self.assertEqual(retrieved.description, "All food items")

    def test_update_category_parent(self):
        """Test updating category parent."""
        parent = Category("shopping", "Shopping", "Shopping expenses", "")
        child = Category("groceries", "Groceries", "Food", "")

        self.datasource.create_category(parent)
        self.datasource.create_category(child)

        result = self.datasource.update_category("groceries", parent_id="shopping")
        self.assertTrue(result)

        # Verify the update
        retrieved = self.datasource.get_category_by_id("groceries")
        self.assertEqual(retrieved.parent_id, "shopping")

    def test_update_category_nonexistent(self):
        """Test updating a non-existent category returns False."""
        result = self.datasource.update_category("nonexistent", name="Test")
        self.assertFalse(result)

    def test_delete_category_success(self):
        """Test successful category deletion."""
        category = Category("groceries", "Groceries", "Food", "")
        self.datasource.create_category(category)

        result = self.datasource.delete_category("groceries")
        self.assertTrue(result)

        # Verify it was deleted
        retrieved = self.datasource.get_category_by_id("groceries")
        self.assertIsNone(retrieved)

    def test_delete_category_nonexistent(self):
        """Test deleting a non-existent category returns False."""
        result = self.datasource.delete_category("nonexistent")
        self.assertFalse(result)

    def test_has_transactions_true(self):
        """Test has_transactions returns True when category has transactions."""
        category = Category("groceries", "Groceries", "Food", "")
        self.datasource.create_category(category)

        # Add a transaction assignment
        self.manual_assignments.add_assignment("tx1", "groceries")

        result = self.datasource.has_transactions("groceries")
        self.assertTrue(result)

    def test_has_transactions_false(self):
        """Test has_transactions returns False when category has no transactions."""
        category = Category("groceries", "Groceries", "Food", "")
        self.datasource.create_category(category)

        result = self.datasource.has_transactions("groceries")
        self.assertFalse(result)

    def test_has_children_true(self):
        """Test has_children returns True when category has children."""
        parent = Category("shopping", "Shopping", "Shopping expenses", "")
        child = Category("groceries", "Groceries", "Food", "shopping")

        self.datasource.create_category(parent)
        self.datasource.create_category(child)

        result = self.datasource.has_children("shopping")
        self.assertTrue(result)

    def test_has_children_false(self):
        """Test has_children returns False when category has no children."""
        category = Category("groceries", "Groceries", "Food", "")
        self.datasource.create_category(category)

        result = self.datasource.has_children("groceries")
        self.assertFalse(result)

    def test_get_transaction_count(self):
        """Test get_transaction_count returns correct count."""
        category = Category("groceries", "Groceries", "Food", "")
        self.datasource.create_category(category)

        # Add multiple transaction assignments
        self.manual_assignments.add_assignment("tx1", "groceries")
        self.manual_assignments.add_assignment("tx2", "groceries")
        self.manual_assignments.add_assignment("tx3", "groceries")

        count = self.datasource.get_transaction_count("groceries")
        self.assertEqual(count, 3)

    def test_get_transaction_count_zero(self):
        """Test get_transaction_count returns 0 for category with no transactions."""
        category = Category("groceries", "Groceries", "Food", "")
        self.datasource.create_category(category)

        count = self.datasource.get_transaction_count("groceries")
        self.assertEqual(count, 0)

    def test_has_regexps_true(self):
        """Test has_regexps returns True when category has regex patterns."""
        category = Category("groceries", "Groceries", "Food", "")
        self.datasource.create_category(category)

        # Add a regex pattern
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO regexps (id, raw, name, internal_category, user_id)
            VALUES (?, ?, ?, ?, ?)
        """, ("regex1", ".*market.*", "Market purchases", "groceries", self.user_id))
        conn.commit()
        conn.close()

        result = self.datasource.has_regexps("groceries")
        self.assertTrue(result)

    def test_has_regexps_false(self):
        """Test has_regexps returns False when category has no regex patterns."""
        category = Category("groceries", "Groceries", "Food", "")
        self.datasource.create_category(category)

        result = self.datasource.has_regexps("groceries")
        self.assertFalse(result)

    def test_get_regexp_count(self):
        """Test get_regexp_count returns correct count."""
        category = Category("groceries", "Groceries", "Food", "")
        self.datasource.create_category(category)

        # Add multiple regex patterns
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO regexps (id, raw, name, internal_category, user_id)
            VALUES (?, ?, ?, ?, ?)
        """, ("regex1", ".*market.*", "Market purchases", "groceries", self.user_id))
        cursor.execute("""
            INSERT INTO regexps (id, raw, name, internal_category, user_id)
            VALUES (?, ?, ?, ?, ?)
        """, ("regex2", ".*grocery.*", "Grocery purchases", "groceries", self.user_id))
        conn.commit()
        conn.close()

        count = self.datasource.get_regexp_count("groceries")
        self.assertEqual(count, 2)

    def test_get_regexp_count_zero(self):
        """Test get_regexp_count returns 0 for category with no regex patterns."""
        category = Category("groceries", "Groceries", "Food", "")
        self.datasource.create_category(category)

        count = self.datasource.get_regexp_count("groceries")
        self.assertEqual(count, 0)

    def test_user_isolation(self):
        """Test that categories are isolated by user_id."""
        datasource_user1 = SQLiteCategoryDataSource(self.db_path, "user1")
        datasource_user2 = SQLiteCategoryDataSource(self.db_path, "user2")

        category1 = Category("groceries_user1", "Groceries User 1", "Food", "")
        category2 = Category("groceries_user2", "Groceries User 2", "Food", "")

        # Each user can create their own categories
        result1 = datasource_user1.create_category(category1)
        result2 = datasource_user2.create_category(category2)

        self.assertTrue(result1)
        self.assertTrue(result2)

        # Each user only sees their own categories
        cat1 = datasource_user1.get_category_by_id("groceries_user1")
        cat2_from_user1 = datasource_user1.get_category_by_id("groceries_user2")
        cat2 = datasource_user2.get_category_by_id("groceries_user2")
        cat1_from_user2 = datasource_user2.get_category_by_id("groceries_user1")

        # User 1 can see their own category
        self.assertIsNotNone(cat1)
        self.assertEqual(cat1.name, "Groceries User 1")

        # User 1 cannot see user 2's category
        self.assertIsNone(cat2_from_user1)

        # User 2 can see their own category
        self.assertIsNotNone(cat2)
        self.assertEqual(cat2.name, "Groceries User 2")

        # User 2 cannot see user 1's category
        self.assertIsNone(cat1_from_user2)


if __name__ == '__main__':
    unittest.main()

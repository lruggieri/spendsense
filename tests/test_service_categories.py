"""
Tests for category management in CategoryService.
"""

import os
import sqlite3
import tempfile
import unittest

from application.services.category_service import CategoryService
from infrastructure.persistence.sqlite.repositories.category_repository import (
    SQLiteCategoryDataSource,
)
from infrastructure.persistence.sqlite.repositories.manual_assignment_repository import (
    SQLiteManualAssignmentDataSource,
)


class TestServiceCategoryManagement(unittest.TestCase):
    """Test category management business logic in CategoryService."""

    def setUp(self):
        """Create a temporary database and initialize service."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
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
        category_datasource = SQLiteCategoryDataSource(self.db_path, self.user_id)
        self.service = CategoryService(self.user_id, category_datasource, self.db_path)

        # Helper datasource for test setup (adding manual assignments)
        self.manual_assignments = SQLiteManualAssignmentDataSource(self.db_path, self.user_id)

    def tearDown(self):
        """Clean up temporary database."""
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_create_category_success(self):
        """Test successful category creation through service."""
        success, error, category_id = self.service.create_category(
            "Groceries", "Food and groceries", ""
        )

        self.assertTrue(success)
        self.assertEqual(error, "")
        self.assertIsNotNone(category_id)
        self.assertNotEqual(category_id, "")

        # Verify it's in service categories
        self.assertIn(category_id, self.service.categories)

    def test_create_category_empty_name(self):
        """Test that empty name is rejected."""
        success, error, category_id = self.service.create_category("", "Food", "")

        self.assertFalse(success)
        self.assertIn("cannot be empty", error.lower())
        self.assertEqual(category_id, "")

    def test_create_category_name_too_long(self):
        """Test that names over 40 characters are rejected."""
        long_name = "A" * 41  # 41 characters
        success, error, category_id = self.service.create_category(long_name, "Test", "")

        self.assertFalse(success)
        self.assertIn("40 characters", error.lower())
        self.assertEqual(category_id, "")

        # Test that exactly 40 characters is allowed
        max_name = "B" * 40  # 40 characters
        success2, error2, category_id2 = self.service.create_category(max_name, "Test", "")

        self.assertTrue(success2)
        self.assertEqual(error2, "")
        self.assertNotEqual(category_id2, "")

    def test_create_category_nonexistent_parent(self):
        """Test that non-existent parent is rejected."""
        success, error, category_id = self.service.create_category(
            "Groceries", "Food", "nonexistent"
        )

        self.assertFalse(success)
        self.assertIn("does not exist", error.lower())
        self.assertEqual(category_id, "")

    def test_create_category_with_parent(self):
        """Test creating a category with a valid parent."""
        # Create parent first
        success1, error1, parent_id = self.service.create_category(
            "Shopping", "Shopping expenses", ""
        )
        self.assertTrue(success1)

        # Create child
        success2, error2, child_id = self.service.create_category("Groceries", "Food", parent_id)

        self.assertTrue(success2)
        self.assertEqual(error2, "")

        # Verify parent relationship
        self.assertEqual(self.service.categories[child_id].parent_id, parent_id)

    def test_update_category_success(self):
        """Test successful category update."""
        success1, error1, groceries_id = self.service.create_category("Groceries", "Food", "")
        self.assertTrue(success1)

        success, error = self.service.update_category(groceries_id, name="Food & Groceries")

        self.assertTrue(success)
        self.assertEqual(self.service.categories[groceries_id].name, "Food & Groceries")

    def test_update_category_protected(self):
        """Test that protected categories cannot be updated."""
        success, error = self.service.update_category("all", name="All Categories Modified")

        self.assertFalse(success)
        self.assertIn("system category", error.lower())

        success2, error2 = self.service.update_category("unknown", name="Unknown Modified")

        self.assertFalse(success2)
        self.assertIn("system category", error2.lower())

    def test_update_category_nonexistent(self):
        """Test updating non-existent category."""
        success, error = self.service.update_category("nonexistent", name="Test")

        self.assertFalse(success)
        self.assertIn("does not exist", error.lower())

    def test_update_category_empty_name(self):
        """Test that empty name is rejected on update."""
        success1, error1, groceries_id = self.service.create_category("Groceries", "Food", "")
        self.assertTrue(success1)

        success, error = self.service.update_category(groceries_id, name="")

        self.assertFalse(success)
        self.assertIn("cannot be empty", error.lower())

    def test_update_category_name_too_long(self):
        """Test that names over 40 characters are rejected on update."""
        success1, error1, groceries_id = self.service.create_category("Groceries", "Food", "")
        self.assertTrue(success1)

        long_name = "C" * 41  # 41 characters
        success, error = self.service.update_category(groceries_id, name=long_name)

        self.assertFalse(success)
        self.assertIn("40 characters", error.lower())

        # Test that exactly 40 characters is allowed
        max_name = "D" * 40  # 40 characters
        success2, error2 = self.service.update_category(groceries_id, name=max_name)

        self.assertTrue(success2)
        self.assertEqual(error2, "")
        self.assertEqual(self.service.categories[groceries_id].name, max_name)

    def test_update_category_self_parent(self):
        """Test that category cannot be its own parent."""
        success1, error1, groceries_id = self.service.create_category("Groceries", "Food", "")
        self.assertTrue(success1)

        success, error = self.service.update_category(groceries_id, parent_id=groceries_id)

        self.assertFalse(success)
        self.assertIn("cannot be its own parent", error.lower())

    def test_update_category_cycle_direct(self):
        """Test that direct cycles are prevented."""
        # A -> B, then try to set B -> A
        success1, error1, a_id = self.service.create_category("Category A", "A", "")
        success2, error2, b_id = self.service.create_category("Category B", "B", a_id)
        self.assertTrue(success1 and success2)

        success, error = self.service.update_category(a_id, parent_id=b_id)

        self.assertFalse(success)
        self.assertIn("cycle", error.lower())

    def test_update_category_cycle_indirect(self):
        """Test that indirect cycles are prevented."""
        # A -> B -> C, then try to set A -> C
        success1, error1, a_id = self.service.create_category("Category A", "A", "")
        success2, error2, b_id = self.service.create_category("Category B", "B", a_id)
        success3, error3, c_id = self.service.create_category("Category C", "C", b_id)
        self.assertTrue(success1 and success2 and success3)

        success, error = self.service.update_category(a_id, parent_id=c_id)

        self.assertFalse(success)
        self.assertIn("cycle", error.lower())

    def test_delete_category_success(self):
        """Test successful category deletion."""
        success1, error1, groceries_id = self.service.create_category("Groceries", "Food", "")
        self.assertTrue(success1)

        success, error = self.service.delete_category(groceries_id)

        self.assertTrue(success)
        self.assertNotIn(groceries_id, self.service.categories)

    def test_delete_category_protected(self):
        """Test that protected categories cannot be deleted."""
        success, error = self.service.delete_category("all")

        self.assertFalse(success)
        self.assertIn("system category", error.lower())

    def test_delete_category_with_children(self):
        """Test that categories with children cannot be deleted."""
        success1, error1, shopping_id = self.service.create_category("Shopping", "Shopping", "")
        success2, error2, groceries_id = self.service.create_category(
            "Groceries", "Food", shopping_id
        )
        self.assertTrue(success1 and success2)

        success, error = self.service.delete_category(shopping_id)

        self.assertFalse(success)
        self.assertIn("children", error.lower())

    def test_delete_category_with_regexps(self):
        """Test that categories with regex patterns cannot be deleted."""
        success1, error1, groceries_id = self.service.create_category("Groceries", "Food", "")
        self.assertTrue(success1)

        # Manually add a regex pattern
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO regexps (id, raw, name, internal_category, user_id)
            VALUES (?, ?, ?, ?, ?)
        """,
            ("regex1", ".*market.*", "Market purchases", groceries_id, self.user_id),
        )
        conn.commit()
        conn.close()

        success, error = self.service.delete_category(groceries_id)

        self.assertFalse(success)
        self.assertIn("regex", error.lower())

    def test_delete_category_with_transactions(self):
        """Test that categories with transactions cannot be deleted."""
        success1, error1, groceries_id = self.service.create_category("Groceries", "Food", "")
        self.assertTrue(success1)

        # Manually add a transaction assignment
        self.manual_assignments.add_assignment("tx1", groceries_id)

        success, error = self.service.delete_category(groceries_id)

        self.assertFalse(success)
        self.assertIn("transaction", error.lower())

    def test_delete_category_with_descendant_transactions(self):
        """Test that categories with descendant transactions cannot be deleted."""
        # Create parent -> child hierarchy
        success1, error1, shopping_id = self.service.create_category("Shopping", "Shopping", "")
        success2, error2, groceries_id = self.service.create_category(
            "Groceries", "Food", shopping_id
        )
        self.assertTrue(success1 and success2)

        # Add transaction to child
        self.manual_assignments.add_assignment("tx1", groceries_id)

        # Try to delete parent (should fail even though parent has no direct transactions)
        success, error = self.service.delete_category(shopping_id)

        self.assertFalse(success)
        self.assertIn("child", error.lower())

    def test_delete_category_nonexistent(self):
        """Test deleting non-existent category."""
        success, error = self.service.delete_category("nonexistent")

        self.assertFalse(success)
        self.assertIn("does not exist", error.lower())

    def test_would_create_cycle_no_cycle(self):
        """Test cycle detection returns False when no cycle."""
        success1, error1, a_id = self.service.create_category("Category A", "A", "")
        success2, error2, b_id = self.service.create_category("Category B", "B", "")
        self.assertTrue(success1 and success2)

        # Setting B's parent to A should not create a cycle
        result = self.service._would_create_cycle(b_id, a_id)
        self.assertFalse(result)

    def test_would_create_cycle_direct(self):
        """Test cycle detection for direct cycle."""
        success1, error1, a_id = self.service.create_category("Category A", "A", "")
        success2, error2, b_id = self.service.create_category("Category B", "B", a_id)
        self.assertTrue(success1 and success2)

        # Setting A's parent to B would create a cycle
        result = self.service._would_create_cycle(a_id, b_id)
        self.assertTrue(result)

    def test_would_create_cycle_indirect(self):
        """Test cycle detection for indirect cycle."""
        success1, error1, a_id = self.service.create_category("Category A", "A", "")
        success2, error2, b_id = self.service.create_category("Category B", "B", a_id)
        success3, error3, c_id = self.service.create_category("Category C", "C", b_id)
        self.assertTrue(success1 and success2 and success3)

        # Setting A's parent to C would create a cycle
        result = self.service._would_create_cycle(a_id, c_id)
        self.assertTrue(result)

    def test_would_create_cycle_empty_parent(self):
        """Test cycle detection with empty parent."""
        success1, error1, a_id = self.service.create_category("Category A", "A", "")
        self.assertTrue(success1)

        result = self.service._would_create_cycle(a_id, "")
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()

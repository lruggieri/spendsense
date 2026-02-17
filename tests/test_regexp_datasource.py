"""
Tests for SQLiteRegexpDataSource CRUD operations.
"""

import unittest
import tempfile
import os
import sqlite3

from infrastructure.persistence.sqlite.repositories.regexp_repository import SQLiteRegexpDataSource


class TestRegexpDataSourceCRUD(unittest.TestCase):
    """Test CRUD operations in SQLiteRegexpDataSource."""

    def setUp(self):
        """Create a temporary database and initialize datasource."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.db_path = self.temp_db.name
        self.temp_db.close()

        # Initialize database schema
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE regexps (
                id TEXT PRIMARY KEY,
                raw TEXT NOT NULL,
                name TEXT NOT NULL,
                internal_category TEXT NOT NULL,
                user_id TEXT NOT NULL,
                order_index INTEGER NOT NULL DEFAULT 0,
                visual_description TEXT
            )
        """)

        cursor.execute("""
            CREATE INDEX idx_regexps_order ON regexps(user_id, order_index)
        """)

        conn.commit()
        conn.close()

        self.user_id = "test_user"
        self.datasource = SQLiteRegexpDataSource(self.db_path, self.user_id)

    def tearDown(self):
        """Clean up temporary database."""
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_create_regexp_success(self):
        """Test successful regexp creation."""
        success = self.datasource.create_regexp(
            regexp_id="pattern1",
            raw="^amazon.*$",
            name="Amazon purchases",
            visual_description='{"type":"visual_rule","version":1,"rules":[{"operator":"START_WITH","keyword":"amazon"}]}',
            category="shopping",
            order_index=0
        )

        self.assertTrue(success)

        # Verify it's in the database
        patterns = self.datasource.get_all_regexps_with_metadata()
        self.assertEqual(len(patterns), 1)
        self.assertEqual(patterns[0].id, "pattern1")
        self.assertEqual(patterns[0].name, "Amazon purchases")

    def test_create_regexp_duplicate_id(self):
        """Test that duplicate IDs are rejected."""
        self.datasource.create_regexp(
            regexp_id="pattern1",
            raw="^amazon.*$",
            name="Amazon",
            visual_description='{}',
            category="shopping",
            order_index=0
        )

        # Try to create another with same ID
        success = self.datasource.create_regexp(
            regexp_id="pattern1",
            raw="^ebay.*$",
            name="Ebay",
            visual_description='{}',
            category="shopping",
            order_index=1
        )

        self.assertFalse(success)

    def test_update_regexp_success(self):
        """Test successful regexp update."""
        # Create pattern first
        self.datasource.create_regexp(
            regexp_id="pattern1",
            raw="^amazon.*$",
            name="Amazon",
            visual_description='{}',
            category="shopping",
            order_index=0
        )

        # Update it
        success = self.datasource.update_regexp(
            regexp_id="pattern1",
            raw="^amazon(?=.*grocery).*$",
            name="Amazon Grocery",
            visual_description='{"rules":[{"operator":"START_WITH","keyword":"amazon"},{"operator":"AND","keyword":"grocery"}]}',
            category="groceries"
        )

        self.assertTrue(success)

        # Verify updates
        pattern = self.datasource.get_regexp_by_id("pattern1")
        self.assertEqual(pattern.name, "Amazon Grocery")
        self.assertEqual(pattern.internal_category, "groceries")

    def test_update_regexp_partial(self):
        """Test partial update (only some fields)."""
        self.datasource.create_regexp(
            regexp_id="pattern1",
            raw="^amazon.*$",
            name="Amazon",
            visual_description='{}',
            category="shopping",
            order_index=0
        )

        # Update only name
        success = self.datasource.update_regexp(
            regexp_id="pattern1",
            name="Amazon Updated"
        )

        self.assertTrue(success)

        pattern = self.datasource.get_regexp_by_id("pattern1")
        self.assertEqual(pattern.name, "Amazon Updated")
        self.assertEqual(pattern.internal_category, "shopping")  # Unchanged

    def test_update_regexp_nonexistent(self):
        """Test updating non-existent pattern."""
        success = self.datasource.update_regexp(
            regexp_id="nonexistent",
            name="Test"
        )

        self.assertFalse(success)

    def test_delete_regexp_success(self):
        """Test successful regexp deletion."""
        self.datasource.create_regexp(
            regexp_id="pattern1",
            raw="^amazon.*$",
            name="Amazon",
            visual_description='{}',
            category="shopping",
            order_index=0
        )

        success = self.datasource.delete_regexp("pattern1")
        self.assertTrue(success)

        # Verify it's gone
        patterns = self.datasource.get_all_regexps_with_metadata()
        self.assertEqual(len(patterns), 0)

    def test_delete_regexp_nonexistent(self):
        """Test deleting non-existent pattern."""
        success = self.datasource.delete_regexp("nonexistent")
        self.assertFalse(success)

    def test_reorder_regexps_success(self):
        """Test batch reordering of regexps."""
        # Create 3 patterns
        self.datasource.create_regexp("pattern1", ".*a.*", "A", '{}', "cat1", 0)
        self.datasource.create_regexp("pattern2", ".*b.*", "B", '{}', "cat2", 1)
        self.datasource.create_regexp("pattern3", ".*c.*", "C", '{}', "cat3", 2)

        # Reorder: pattern3 first, pattern1 second, pattern2 third
        success = self.datasource.reorder_regexps([
            ("pattern3", 0),
            ("pattern1", 1),
            ("pattern2", 2)
        ])

        self.assertTrue(success)

        # Verify new order
        patterns = self.datasource.get_all_regexps_with_metadata()
        self.assertEqual(patterns[0].id, "pattern3")
        self.assertEqual(patterns[1].id, "pattern1")
        self.assertEqual(patterns[2].id, "pattern2")

    def test_get_all_regexps_ordered(self):
        """Test that get_all_regexps returns patterns ordered by order_index."""
        # Create patterns in non-sequential order
        self.datasource.create_regexp("pattern1", ".*a.*", "A", '{}', "cat1", 5)
        self.datasource.create_regexp("pattern2", ".*b.*", "B", '{}', "cat2", 2)
        self.datasource.create_regexp("pattern3", ".*c.*", "C", '{}', "cat3", 10)

        patterns = self.datasource.get_all_regexps()

        # Should be ordered by order_index ASC
        self.assertEqual(len(patterns), 3)
        self.assertEqual(patterns[0].internal_category, "cat2")  # pattern2 with order_index 2
        self.assertEqual(patterns[1].internal_category, "cat1")  # pattern1 with order_index 5
        self.assertEqual(patterns[2].internal_category, "cat3")  # pattern3 with order_index 10

    def test_get_max_order_index(self):
        """Test getting maximum order_index."""
        # Empty database
        max_idx = self.datasource.get_max_order_index()
        self.assertEqual(max_idx, 0)

        # Add patterns
        self.datasource.create_regexp("pattern1", ".*a.*", "A", '{}', "cat1", 5)
        self.datasource.create_regexp("pattern2", ".*b.*", "B", '{}', "cat2", 10)

        max_idx = self.datasource.get_max_order_index()
        self.assertEqual(max_idx, 10)

    def test_get_regexp_by_id(self):
        """Test getting a specific regexp by ID."""
        self.datasource.create_regexp(
            regexp_id="pattern1",
            raw="^amazon.*$",
            name="Amazon",
            visual_description='{}',
            category="shopping",
            order_index=0
        )

        pattern = self.datasource.get_regexp_by_id("pattern1")
        self.assertIsNotNone(pattern)
        self.assertEqual(pattern.id, "pattern1")
        self.assertEqual(pattern.raw, "^amazon.*$")
        self.assertEqual(pattern.name, "Amazon")
        self.assertEqual(pattern.internal_category, "shopping")

    def test_get_regexp_by_id_nonexistent(self):
        """Test getting non-existent pattern returns None."""
        pattern = self.datasource.get_regexp_by_id("nonexistent")
        self.assertIsNone(pattern)

    def test_user_isolation(self):
        """Test that patterns are isolated by user_id."""
        datasource_user1 = SQLiteRegexpDataSource(self.db_path, "user1")
        datasource_user2 = SQLiteRegexpDataSource(self.db_path, "user2")

        # Create pattern for user1
        datasource_user1.create_regexp("pattern1", ".*a.*", "A", '{}', "cat1", 0)

        # User2 should not see it
        patterns_user2 = datasource_user2.get_all_regexps()
        self.assertEqual(len(patterns_user2), 0)

        # User1 should see it
        patterns_user1 = datasource_user1.get_all_regexps()
        self.assertEqual(len(patterns_user1), 1)


if __name__ == '__main__':
    unittest.main()

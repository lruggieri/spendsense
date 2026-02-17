"""
Tests for CategoryTree (domain/entities/category_tree.py).

Tests cover:
- Tree construction from categories dict
- Parent-child relationships
- Unknown node auto-creation
- calculate_expenses basic
- calculate_expenses with date filter
- calculate_expenses with currency conversion mock
- Expense propagation to parents
- _find_node_by_id
- _parse_date with various formats and invalid inputs
- _filter_transactions_by_date
"""

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from domain.entities.category import Category
from domain.entities.category_tree import (
    CategoryTree, CategoryNode, ALL_CATEGORY_ID, UNKNOWN_CATEGORY_ID
)
from domain.entities.transaction import Transaction


class TestCategoryTreeConstruction(unittest.TestCase):
    """Test tree construction from categories dict."""

    def _make_categories_dict(self, categories):
        """Helper to create the dict format expected by CategoryTree."""
        return {"internal": categories}

    def test_tree_construction_basic(self):
        """Test basic tree construction with flat categories."""
        categories = self._make_categories_dict([
            Category("food", "Food", "Food expenses", ""),
            Category("transport", "Transport", "Transport expenses", ""),
        ])
        tree = CategoryTree(categories)

        self.assertIsNotNone(tree.root)
        self.assertEqual(tree.root.category.id, ALL_CATEGORY_ID)
        # Root should have children: food, transport, unknown
        child_ids = [c.category.id for c in tree.root.children]
        self.assertIn("food", child_ids)
        self.assertIn("transport", child_ids)
        self.assertIn(UNKNOWN_CATEGORY_ID, child_ids)

    def test_tree_construction_parent_child(self):
        """Test tree construction with parent-child hierarchy."""
        categories = self._make_categories_dict([
            Category("food", "Food", "Food expenses", ""),
            Category("restaurant", "Restaurant", "Restaurant expenses", "food"),
            Category("grocery", "Grocery", "Grocery shopping", "food"),
        ])
        tree = CategoryTree(categories)

        # Find food node
        food_node = tree._find_node_by_id(tree.root, "food")
        self.assertIsNotNone(food_node)

        # food should have restaurant and grocery as children
        food_child_ids = [c.category.id for c in food_node.children]
        self.assertIn("restaurant", food_child_ids)
        self.assertIn("grocery", food_child_ids)

    def test_unknown_node_auto_creation(self):
        """Test that unknown category node is automatically created."""
        categories = self._make_categories_dict([
            Category("food", "Food", "Food expenses", ""),
        ])
        tree = CategoryTree(categories)

        unknown_node = tree._find_node_by_id(tree.root, UNKNOWN_CATEGORY_ID)
        self.assertIsNotNone(unknown_node)
        self.assertEqual(unknown_node.category.name, "Unknown")

    def test_orphan_categories_attach_to_root(self):
        """Test that categories with nonexistent parents attach to root."""
        categories = self._make_categories_dict([
            Category("child", "Child", "Orphan child", "nonexistent_parent"),
        ])
        tree = CategoryTree(categories)

        # Child should be attached to root since parent doesn't exist
        root_child_ids = [c.category.id for c in tree.root.children]
        self.assertIn("child", root_child_ids)

    def test_categories_stored_in_dict(self):
        """Test that categories are stored in the tree's categories dict."""
        categories = self._make_categories_dict([
            Category("food", "Food", "Food expenses", ""),
            Category("transport", "Transport", "Transport expenses", ""),
        ])
        tree = CategoryTree(categories)

        self.assertIn("food", tree.categories)
        self.assertIn("transport", tree.categories)
        # Unknown is also added
        self.assertIn(UNKNOWN_CATEGORY_ID, tree.categories)


class TestFindNodeById(unittest.TestCase):
    """Test _find_node_by_id method."""

    def setUp(self):
        categories = {"internal": [
            Category("food", "Food", "Food expenses", ""),
            Category("restaurant", "Restaurant", "Restaurant expenses", "food"),
            Category("transport", "Transport", "Transport expenses", ""),
        ]}
        self.tree = CategoryTree(categories)

    def test_find_root(self):
        """Test finding the root node."""
        node = self.tree._find_node_by_id(self.tree.root, ALL_CATEGORY_ID)
        self.assertIsNotNone(node)
        self.assertEqual(node.category.id, ALL_CATEGORY_ID)

    def test_find_top_level_node(self):
        """Test finding a top-level category node."""
        node = self.tree._find_node_by_id(self.tree.root, "food")
        self.assertIsNotNone(node)
        self.assertEqual(node.category.name, "Food")

    def test_find_nested_node(self):
        """Test finding a nested category node."""
        node = self.tree._find_node_by_id(self.tree.root, "restaurant")
        self.assertIsNotNone(node)
        self.assertEqual(node.category.name, "Restaurant")

    def test_find_nonexistent_node(self):
        """Test finding a node that doesn't exist."""
        node = self.tree._find_node_by_id(self.tree.root, "nonexistent")
        self.assertIsNone(node)


class TestParseDate(unittest.TestCase):
    """Test _parse_date method."""

    def setUp(self):
        categories = {"internal": [
            Category("food", "Food", "Food expenses", ""),
        ]}
        self.tree = CategoryTree(categories)

    def test_parse_yyyy_mm_dd(self):
        """Test parsing YYYY-MM-DD format."""
        result = self.tree._parse_date("2025-06-15")
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2025)
        self.assertEqual(result.month, 6)
        self.assertEqual(result.day, 15)
        self.assertIsNotNone(result.tzinfo)

    def test_parse_yyyy_slash_mm_slash_dd(self):
        """Test parsing YYYY/MM/DD format."""
        result = self.tree._parse_date("2025/06/15")
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2025)
        self.assertEqual(result.month, 6)
        self.assertEqual(result.day, 15)

    def test_parse_mm_slash_dd_slash_yyyy(self):
        """Test parsing MM/DD/YYYY format."""
        result = self.tree._parse_date("06/15/2025")
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2025)
        self.assertEqual(result.month, 6)
        self.assertEqual(result.day, 15)

    def test_parse_invalid_string(self):
        """Test parsing an invalid date string."""
        result = self.tree._parse_date("not-a-date")
        self.assertIsNone(result)

    def test_parse_datetime_passthrough(self):
        """Test that datetime objects pass through unchanged."""
        dt = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        result = self.tree._parse_date(dt)
        self.assertEqual(result, dt)

    def test_parse_non_string_non_datetime(self):
        """Test that non-string, non-datetime inputs return None."""
        result = self.tree._parse_date(12345)
        self.assertIsNone(result)

    def test_parse_empty_string(self):
        """Test that empty string returns None."""
        result = self.tree._parse_date("")
        self.assertIsNone(result)

    def test_parse_iso8601_utc_z(self):
        """Test parsing ISO 8601 with Z suffix."""
        result = self.tree._parse_date("2026-02-15T15:00:00.000Z")
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2026)
        self.assertEqual(result.month, 2)
        self.assertEqual(result.day, 15)
        self.assertEqual(result.hour, 15)
        self.assertEqual(result.minute, 0)
        self.assertIsNotNone(result.tzinfo)

    def test_parse_iso8601_with_offset(self):
        """Test parsing ISO 8601 with timezone offset."""
        result = self.tree._parse_date("2026-02-16T00:00:00+09:00")
        self.assertIsNotNone(result)
        # Should be converted to UTC: Feb 15 15:00
        self.assertEqual(result.year, 2026)
        self.assertEqual(result.month, 2)
        self.assertEqual(result.day, 15)
        self.assertEqual(result.hour, 15)

    def test_parse_iso8601_no_milliseconds(self):
        """Test parsing ISO 8601 without milliseconds."""
        result = self.tree._parse_date("2026-02-15T15:00:00Z")
        self.assertIsNotNone(result)
        self.assertEqual(result.hour, 15)

    def test_parse_iso8601_utc_offset(self):
        """Test parsing ISO 8601 with +00:00."""
        result = self.tree._parse_date("2026-02-15T15:00:00+00:00")
        self.assertIsNotNone(result)
        self.assertEqual(result.hour, 15)

    def test_parse_iso8601_negative_offset(self):
        """Test parsing ISO 8601 with negative timezone offset (e.g. US Eastern)."""
        result = self.tree._parse_date("2026-02-15T19:00:00-05:00")
        self.assertIsNotNone(result)
        # Should be converted to UTC: Feb 16 00:00
        self.assertEqual(result.year, 2026)
        self.assertEqual(result.month, 2)
        self.assertEqual(result.day, 16)
        self.assertEqual(result.hour, 0)


class TestFilterTransactionsByDate(unittest.TestCase):
    """Test _filter_transactions_by_date method."""

    def setUp(self):
        categories = {"internal": [
            Category("food", "Food", "Food expenses", ""),
        ]}
        self.tree = CategoryTree(categories)

        self.transactions = [
            Transaction(id="tx1", date=datetime(2025, 1, 15, tzinfo=timezone.utc),
                        amount=1000, description="Jan", category="food",
                        source="Test", currency="JPY"),
            Transaction(id="tx2", date=datetime(2025, 6, 15, tzinfo=timezone.utc),
                        amount=2000, description="Jun", category="food",
                        source="Test", currency="JPY"),
            Transaction(id="tx3", date=datetime(2025, 12, 15, tzinfo=timezone.utc),
                        amount=3000, description="Dec", category="food",
                        source="Test", currency="JPY"),
        ]

    def test_no_filter(self):
        """Test with no date filters returns all transactions."""
        result = self.tree._filter_transactions_by_date(self.transactions, None, None)
        self.assertEqual(len(result), 3)

    def test_from_date_filter(self):
        """Test filtering with only from_date."""
        result = self.tree._filter_transactions_by_date(self.transactions, "2025-06-01", None)
        self.assertEqual(len(result), 2)
        ids = [tx.id for tx in result]
        self.assertIn("tx2", ids)
        self.assertIn("tx3", ids)

    def test_to_date_filter(self):
        """Test filtering with only to_date."""
        result = self.tree._filter_transactions_by_date(self.transactions, None, "2025-06-30")
        self.assertEqual(len(result), 2)
        ids = [tx.id for tx in result]
        self.assertIn("tx1", ids)
        self.assertIn("tx2", ids)

    def test_from_and_to_date_filter(self):
        """Test filtering with both from_date and to_date."""
        result = self.tree._filter_transactions_by_date(
            self.transactions, "2025-03-01", "2025-09-30")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "tx2")

    def test_to_date_inclusive_end_of_day(self):
        """Test that to_date is inclusive through end of day."""
        # Transaction at midnight on June 15
        result = self.tree._filter_transactions_by_date(
            self.transactions, None, "2025-06-15")
        ids = [tx.id for tx in result]
        # tx2 is on June 15 (midnight) and should be included
        self.assertIn("tx2", ids)

    def test_iso8601_from_date_filter(self):
        """Test filtering with ISO 8601 from_date (timezone-aware)."""
        # Simulate JST user filtering from Feb 12: start of day is Feb 11 15:00 UTC
        transactions = [
            Transaction(id="tx_before", date=datetime(2026, 2, 11, 14, 0, 0, tzinfo=timezone.utc),
                        amount=1000, description="Before", category="food",
                        source="Test", currency="JPY"),
            Transaction(id="tx_boundary", date=datetime(2026, 2, 11, 22, 20, 0, tzinfo=timezone.utc),
                        amount=2000, description="Boundary", category="food",
                        source="Test", currency="JPY"),
        ]
        # JST midnight Feb 12 = Feb 11 15:00 UTC
        result = self.tree._filter_transactions_by_date(
            transactions, "2026-02-11T15:00:00.000Z", None)
        ids = [tx.id for tx in result]
        self.assertNotIn("tx_before", ids)
        self.assertIn("tx_boundary", ids)

    def test_iso8601_to_date_filter(self):
        """Test filtering with ISO 8601 to_date (timezone-aware)."""
        # Simulate JST user filtering to Feb 12: end of day is Feb 12 14:59:59 UTC
        transactions = [
            Transaction(id="tx_included", date=datetime(2026, 2, 12, 14, 0, 0, tzinfo=timezone.utc),
                        amount=1000, description="Included", category="food",
                        source="Test", currency="JPY"),
            Transaction(id="tx_excluded", date=datetime(2026, 2, 12, 15, 30, 0, tzinfo=timezone.utc),
                        amount=2000, description="Excluded", category="food",
                        source="Test", currency="JPY"),
        ]
        # JST end of Feb 12 (23:59:59) = Feb 12 14:59:59 UTC
        result = self.tree._filter_transactions_by_date(
            transactions, None, "2026-02-12T14:59:59.000Z")
        ids = [tx.id for tx in result]
        self.assertIn("tx_included", ids)
        self.assertNotIn("tx_excluded", ids)

    def test_iso8601_range_reproduces_issue(self):
        """Reproduce the original issue: JST user, tx at 2026-02-12T07:20:00 JST."""
        # Transaction stored as UTC: 2026-02-11T22:20:00Z
        transactions = [
            Transaction(id="tx_jst", date=datetime(2026, 2, 11, 22, 20, 0, tzinfo=timezone.utc),
                        amount=5000, description="JST evening tx", category="food",
                        source="Test", currency="JPY"),
        ]
        # JST user filters for Feb 12 only
        # Start of Feb 12 JST = 2026-02-11T15:00:00Z
        # End of Feb 12 JST = 2026-02-12T14:59:59Z
        result = self.tree._filter_transactions_by_date(
            transactions,
            "2026-02-11T15:00:00.000Z",
            "2026-02-12T14:59:59.000Z")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "tx_jst")


class TestCalculateExpenses(unittest.TestCase):
    """Test calculate_expenses method."""

    def _make_tree(self, categories_list):
        """Helper to create a CategoryTree."""
        return CategoryTree({"internal": categories_list})

    def test_basic_expenses(self):
        """Test basic expense calculation without filters."""
        tree = self._make_tree([
            Category("food", "Food", "Food expenses", ""),
            Category("transport", "Transport", "Transport expenses", ""),
        ])

        transactions = [
            Transaction(id="tx1", date=datetime(2025, 1, 1, tzinfo=timezone.utc),
                        amount=1000, description="Lunch", category="food",
                        source="Test", currency="JPY"),
            Transaction(id="tx2", date=datetime(2025, 1, 2, tzinfo=timezone.utc),
                        amount=2000, description="Train", category="transport",
                        source="Test", currency="JPY"),
            Transaction(id="tx3", date=datetime(2025, 1, 3, tzinfo=timezone.utc),
                        amount=3000, description="Dinner", category="food",
                        source="Test", currency="JPY"),
        ]

        tree.calculate_expenses(transactions)

        # Check food total (1000 + 3000 = 4000 JPY major = 4000.0)
        food_node = tree._find_node_by_id(tree.root, "food")
        self.assertAlmostEqual(food_node.total_expense, 4000.0)

        # Check transport total
        transport_node = tree._find_node_by_id(tree.root, "transport")
        self.assertAlmostEqual(transport_node.total_expense, 2000.0)

        # Check root total (all expenses)
        self.assertAlmostEqual(tree.root.total_expense, 6000.0)

    def test_expenses_with_date_filter(self):
        """Test expense calculation with date filtering."""
        tree = self._make_tree([
            Category("food", "Food", "Food expenses", ""),
        ])

        transactions = [
            Transaction(id="tx1", date=datetime(2025, 1, 1, tzinfo=timezone.utc),
                        amount=1000, description="Jan food", category="food",
                        source="Test", currency="JPY"),
            Transaction(id="tx2", date=datetime(2025, 6, 1, tzinfo=timezone.utc),
                        amount=2000, description="Jun food", category="food",
                        source="Test", currency="JPY"),
        ]

        tree.calculate_expenses(transactions, from_date="2025-05-01", to_date="2025-12-31")

        food_node = tree._find_node_by_id(tree.root, "food")
        self.assertAlmostEqual(food_node.total_expense, 2000.0)

    def test_expenses_with_currency_conversion(self):
        """Test expense calculation with currency conversion mock."""
        tree = self._make_tree([
            Category("food", "Food", "Food expenses", ""),
        ])

        transactions = [
            Transaction(id="tx1", date=datetime(2025, 1, 1, tzinfo=timezone.utc),
                        amount=1000, description="USD food", category="food",
                        source="Test", currency="USD"),
        ]

        # Mock converter: 10.00 USD -> 1500 JPY
        mock_converter = MagicMock()
        mock_converter.convert.return_value = 1500.0

        tree.calculate_expenses(transactions, user_currency="JPY", converter=mock_converter)

        food_node = tree._find_node_by_id(tree.root, "food")
        self.assertAlmostEqual(food_node.total_expense, 1500.0)
        mock_converter.convert.assert_called_once()

    def test_expense_propagation_to_parents(self):
        """Test that expenses propagate up to parent categories."""
        tree = self._make_tree([
            Category("food", "Food", "Food expenses", ""),
            Category("restaurant", "Restaurant", "Restaurant expenses", "food"),
            Category("grocery", "Grocery", "Grocery shopping", "food"),
        ])

        transactions = [
            Transaction(id="tx1", date=datetime(2025, 1, 1, tzinfo=timezone.utc),
                        amount=1000, description="Sushi", category="restaurant",
                        source="Test", currency="JPY"),
            Transaction(id="tx2", date=datetime(2025, 1, 2, tzinfo=timezone.utc),
                        amount=2000, description="Supermarket", category="grocery",
                        source="Test", currency="JPY"),
        ]

        tree.calculate_expenses(transactions)

        # Restaurant: 1000
        restaurant_node = tree._find_node_by_id(tree.root, "restaurant")
        self.assertAlmostEqual(restaurant_node.total_expense, 1000.0)

        # Grocery: 2000
        grocery_node = tree._find_node_by_id(tree.root, "grocery")
        self.assertAlmostEqual(grocery_node.total_expense, 2000.0)

        # Food (parent): 1000 + 2000 = 3000 (propagated from children)
        food_node = tree._find_node_by_id(tree.root, "food")
        self.assertAlmostEqual(food_node.total_expense, 3000.0)

        # Root: 3000 (propagated from food)
        self.assertAlmostEqual(tree.root.total_expense, 3000.0)

    def test_uncategorized_goes_to_unknown(self):
        """Test that transactions with unknown categories go to unknown node."""
        tree = self._make_tree([
            Category("food", "Food", "Food expenses", ""),
        ])

        transactions = [
            Transaction(id="tx1", date=datetime(2025, 1, 1, tzinfo=timezone.utc),
                        amount=1000, description="Mystery", category="nonexistent_cat",
                        source="Test", currency="JPY"),
        ]

        tree.calculate_expenses(transactions)

        unknown_node = tree._find_node_by_id(tree.root, UNKNOWN_CATEGORY_ID)
        self.assertAlmostEqual(unknown_node.total_expense, 1000.0)

    def test_filtered_transactions_stored(self):
        """Test that filtered transactions are stored on the tree."""
        tree = self._make_tree([
            Category("food", "Food", "Food expenses", ""),
        ])

        transactions = [
            Transaction(id="tx1", date=datetime(2025, 1, 1, tzinfo=timezone.utc),
                        amount=1000, description="Food", category="food",
                        source="Test", currency="JPY"),
        ]

        self.assertIsNone(tree.filtered_transactions)
        tree.calculate_expenses(transactions)
        self.assertIsNotNone(tree.filtered_transactions)
        self.assertEqual(len(tree.filtered_transactions), 1)

    def test_reset_expenses_on_recalculate(self):
        """Test that expenses are reset when recalculated."""
        tree = self._make_tree([
            Category("food", "Food", "Food expenses", ""),
        ])

        transactions1 = [
            Transaction(id="tx1", date=datetime(2025, 1, 1, tzinfo=timezone.utc),
                        amount=1000, description="Lunch", category="food",
                        source="Test", currency="JPY"),
        ]

        tree.calculate_expenses(transactions1)
        food_node = tree._find_node_by_id(tree.root, "food")
        self.assertAlmostEqual(food_node.total_expense, 1000.0)

        # Recalculate with different transactions
        transactions2 = [
            Transaction(id="tx2", date=datetime(2025, 1, 2, tzinfo=timezone.utc),
                        amount=500, description="Snack", category="food",
                        source="Test", currency="JPY"),
        ]

        tree.calculate_expenses(transactions2)
        food_node = tree._find_node_by_id(tree.root, "food")
        # Should be 500, not 1000 + 500
        self.assertAlmostEqual(food_node.total_expense, 500.0)

    def test_expenses_with_usd_currency(self):
        """Test expense calculation with USD (has minor units)."""
        tree = self._make_tree([
            Category("food", "Food", "Food expenses", ""),
        ])

        transactions = [
            Transaction(id="tx1", date=datetime(2025, 1, 1, tzinfo=timezone.utc),
                        amount=599, description="Lunch", category="food",
                        source="Test", currency="USD"),
        ]

        tree.calculate_expenses(transactions)

        food_node = tree._find_node_by_id(tree.root, "food")
        # 599 cents = $5.99
        self.assertAlmostEqual(food_node.total_expense, 5.99)


if __name__ == '__main__':
    unittest.main()

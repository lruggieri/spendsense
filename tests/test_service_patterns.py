"""
Tests for pattern management using DDD PatternService and ClassificationService.
"""

import os
import re
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock

from application.services.category_service import CategoryService
from application.services.classification_service import ClassificationService
from application.services.pattern_service import PatternService
from infrastructure.persistence.sqlite.repositories.category_repository import (
    SQLiteCategoryDataSource,
)
from infrastructure.persistence.sqlite.repositories.manual_assignment_repository import (
    SQLiteManualAssignmentDataSource,
)
from infrastructure.persistence.sqlite.repositories.regexp_repository import SQLiteRegexpDataSource


class TestServicePatternManagement(unittest.TestCase):
    """Test pattern management business logic using DDD services."""

    def setUp(self):
        """Create a temporary database and initialize services."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.db_path = self.temp_db.name
        self.temp_db.close()

        # Set the database path via environment variable
        os.environ["DATABASE_PATH"] = self.db_path

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
            CREATE TABLE transactions (
                id TEXT PRIMARY KEY,
                date TEXT NOT NULL,
                amount INTEGER NOT NULL,
                description TEXT NOT NULL,
                source TEXT NOT NULL,
                comment TEXT DEFAULT '',
                user_id TEXT,
                groups TEXT DEFAULT '[]',
                updated_at TEXT,
                mail_id TEXT,
                currency TEXT NOT NULL DEFAULT 'JPY',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                fetcher_id TEXT
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

        cursor.execute("""
            CREATE TABLE groups (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                user_id TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE embeddings (
                tx_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                embedding BLOB NOT NULL,
                description_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(tx_id) REFERENCES transactions(id) ON DELETE CASCADE
            )
        """)

        # Create test categories
        cursor.execute("""
            INSERT INTO categories (id, name, description, parent_id, user_id)
            VALUES ('shopping', 'Shopping', 'Shopping expenses', '', 'test_user')
        """)

        cursor.execute("""
            INSERT INTO categories (id, name, description, parent_id, user_id)
            VALUES ('groceries', 'Groceries', 'Grocery shopping', '', 'test_user')
        """)

        conn.commit()
        conn.close()

        self.user_id = "test_user"

        # Create datasources
        cat_ds = SQLiteCategoryDataSource(self.db_path, self.user_id)
        regexp_ds = SQLiteRegexpDataSource(self.db_path, self.user_id)

        # Create DDD services
        self.category_service = CategoryService(self.user_id, cat_ds, self.db_path)
        self.pattern_service = PatternService(
            self.user_id, regexp_ds, self.category_service, self.db_path
        )

    def tearDown(self):
        """Clean up temporary database."""
        if "DATABASE_PATH" in os.environ:
            del os.environ["DATABASE_PATH"]

        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _create_classification_service(self):
        """Create a fresh ClassificationService that picks up current patterns."""
        ma_ds = SQLiteManualAssignmentDataSource(self.db_path, self.user_id)
        regexp_ds = SQLiteRegexpDataSource(self.db_path, self.user_id)
        embedding_ds = MagicMock()

        return ClassificationService(
            self.user_id,
            manual_assignment_datasource=ma_ds,
            regexp_datasource=regexp_ds,
            embedding_datasource=embedding_ds,
            db_path=self.db_path,
            skip_similarity=True,
        )

    # =========================================================================
    # Pattern CRUD Tests
    # =========================================================================

    def test_create_pattern_success(self):
        """Test successful pattern creation."""
        rules = [{"operator": "OR", "keyword": "amazon"}, {"operator": "AND", "keyword": "grocery"}]

        success, error, pattern_id = self.pattern_service.create_pattern(rules, "shopping")

        self.assertTrue(success)
        self.assertEqual(error, "")
        self.assertIsNotNone(pattern_id)

        # Verify it's in the patterns list
        patterns = self.pattern_service.get_all_patterns()
        self.assertEqual(len(patterns), 1)

    def test_create_pattern_invalid_category(self):
        """Test that invalid category is rejected."""
        rules = [{"operator": "OR", "keyword": "test"}]

        success, error, pattern_id = self.pattern_service.create_pattern(rules, "nonexistent")

        self.assertFalse(success)
        self.assertIn("category", error.lower())
        self.assertEqual(pattern_id, "")

    def test_update_pattern_success(self):
        """Test successful pattern update."""
        rules1 = [{"operator": "OR", "keyword": "amazon"}]
        success1, error1, pattern_id = self.pattern_service.create_pattern(rules1, "shopping")
        self.assertTrue(success1)

        rules2 = [{"operator": "OR", "keyword": "amazon"}, {"operator": "AND", "keyword": "prime"}]
        success2, error2 = self.pattern_service.update_pattern(pattern_id, rules2, "groceries")

        self.assertTrue(success2)
        self.assertEqual(error2, "")

    def test_delete_pattern_success(self):
        """Test successful pattern deletion."""
        rules = [{"operator": "OR", "keyword": "test"}]
        success1, error1, pattern_id = self.pattern_service.create_pattern(rules, "shopping")
        self.assertTrue(success1)

        success2, error2 = self.pattern_service.delete_pattern(pattern_id)

        self.assertTrue(success2)
        self.assertEqual(error2, "")

        # Verify it's gone
        patterns = self.pattern_service.get_all_patterns()
        self.assertEqual(len(patterns), 0)

    # =========================================================================
    # Validation Tests
    # =========================================================================

    def test_validate_rules_empty(self):
        """Test that empty rules are rejected."""
        success, error = self.pattern_service.validate_rules([])

        self.assertFalse(success)
        self.assertIn("at least one", error.lower())

    def test_validate_rules_needs_positive_rule(self):
        """Test that patterns need at least one positive rule."""
        rules = [
            {"operator": "NOT", "keyword": "gift"},
            {"operator": "NOT_START_WITH", "keyword": "marketplace"},
        ]

        success, error = self.pattern_service.validate_rules(rules)

        self.assertFalse(success)
        self.assertIn("positive rule", error.lower())

    def test_validate_rules_keyword_too_long(self):
        """Test that keywords over 100 chars are rejected."""
        rules = [{"operator": "OR", "keyword": "a" * 101}]

        success, error = self.pattern_service.validate_rules(rules)

        self.assertFalse(success)
        self.assertIn("100", error)

    def test_validate_rules_too_many_rules(self):
        """Test that patterns over 20 rules are rejected."""
        rules = [{"operator": "OR", "keyword": f"keyword{i}"} for i in range(21)]

        success, error = self.pattern_service.validate_rules(rules)

        self.assertFalse(success)
        self.assertIn("20", error)

    # =========================================================================
    # Regex Generation Tests - 6 Operators
    # =========================================================================

    def test_rules_to_regex_or_operator(self):
        """Test OR operator generates correct regex with word boundaries."""
        rules = [
            {"operator": "OR", "keyword": "starbucks"},
            {"operator": "OR", "keyword": "coffee"},
        ]

        regex = self.pattern_service.rules_to_regex(rules)

        # Should have word boundaries and alternation
        self.assertIn("(^|\\s)", regex)
        self.assertIn("(\\s|$)", regex)
        self.assertIn("starbucks|coffee", regex)

        # Test matching
        pattern = re.compile(regex, re.IGNORECASE)
        self.assertIsNotNone(pattern.search("starbucks"))
        self.assertIsNotNone(pattern.search("coffee shop"))
        self.assertIsNone(pattern.search("coffeehouse"))  # No word boundary

    def test_rules_to_regex_and_operator(self):
        """Test AND operator uses lookahead assertions."""
        rules = [
            {"operator": "AND", "keyword": "starbucks"},
            {"operator": "AND", "keyword": "coffee"},
        ]

        regex = self.pattern_service.rules_to_regex(rules)

        # Should have lookahead assertions
        self.assertIn("(?=.*starbucks)", regex)
        self.assertIn("(?=.*coffee)", regex)

        # Test matching
        pattern = re.compile(regex, re.IGNORECASE)
        self.assertIsNotNone(pattern.search("starbucks coffee"))
        self.assertIsNotNone(pattern.search("coffee from starbucks"))
        self.assertIsNone(pattern.search("starbucks tea"))

    def test_rules_to_regex_not_operator(self):
        """Test NOT operator uses negative lookahead."""
        rules = [{"operator": "OR", "keyword": "amazon"}, {"operator": "NOT", "keyword": "gift"}]

        regex = self.pattern_service.rules_to_regex(rules)

        # Should have negative lookahead
        self.assertIn("(?!.*gift)", regex)

        # Test matching
        pattern = re.compile(regex, re.IGNORECASE)
        self.assertIsNotNone(pattern.search("amazon purchase"))
        self.assertIsNone(pattern.search("amazon gift card"))

    def test_rules_to_regex_start_with_operator(self):
        """Test START_WITH matches only at beginning."""
        rules = [{"operator": "START_WITH", "keyword": "amazon"}]

        regex = self.pattern_service.rules_to_regex(rules)

        # Should start with ^ and have no word boundaries
        self.assertTrue(regex.startswith("^"))
        self.assertIn("amazon", regex)

        # Test matching
        pattern = re.compile(regex, re.IGNORECASE)
        self.assertIsNotNone(pattern.search("amazon grocery"))
        self.assertIsNone(pattern.search("shop at amazon"))

    def test_rules_to_regex_end_with_operator(self):
        """Test END_WITH matches only at end."""
        rules = [{"operator": "END_WITH", "keyword": "JPY"}]

        regex = self.pattern_service.rules_to_regex(rules)

        # Should end with $
        self.assertTrue(regex.endswith("$"))
        self.assertIn("JPY", regex)

        # Test matching
        pattern = re.compile(regex, re.IGNORECASE)
        self.assertIsNotNone(pattern.search("payment 1000 JPY"))
        self.assertIsNone(pattern.search("JPY payment"))

    def test_rules_to_regex_not_start_with_operator(self):
        """Test NOT_START_WITH excludes patterns starting with keyword."""
        rules = [
            {"operator": "NOT_START_WITH", "keyword": "LAWSON"},
            {"operator": "OR", "keyword": "store"},
        ]

        regex = self.pattern_service.rules_to_regex(rules)

        # Should have negative lookahead at start
        self.assertTrue(regex.startswith("^"))
        self.assertIn("(?!LAWSON)", regex)

        # Test matching
        pattern = re.compile(regex, re.IGNORECASE)
        self.assertIsNotNone(pattern.search("convenience store"))
        self.assertIsNone(pattern.search("LAWSON store"))

    def test_rules_to_regex_all_operators_combined(self):
        """Test all 6 operators working together."""
        rules = [
            {"operator": "NOT_START_WITH", "keyword": "Marketplace:"},
            {"operator": "START_WITH", "keyword": "Amazon"},
            {"operator": "OR", "keyword": "grocery"},
            {"operator": "OR", "keyword": "vegetables"},
            {"operator": "AND", "keyword": "delivery"},
            {"operator": "NOT", "keyword": "gift"},
            {"operator": "END_WITH", "keyword": "JPY"},
        ]

        regex = self.pattern_service.rules_to_regex(rules)

        # Test matching
        pattern = re.compile(regex, re.IGNORECASE)

        # Should match
        self.assertIsNotNone(pattern.search("Amazon grocery delivery 1000 JPY"))
        self.assertIsNotNone(pattern.search("Amazon fresh vegetables delivery 2000 JPY"))

        # Should NOT match
        self.assertIsNone(
            pattern.search("Marketplace: Amazon grocery delivery JPY")
        )  # Starts with Marketplace:
        self.assertIsNone(pattern.search("Amazon grocery 1000 JPY"))  # Missing delivery
        self.assertIsNone(pattern.search("Amazon grocery delivery gift 1000 JPY"))  # Contains gift
        self.assertIsNone(
            pattern.search("Amazon grocery delivery 1000 USD")
        )  # Doesn't end with JPY

    def test_rules_to_regex_escapes_special_chars(self):
        """Test that regex special characters are properly escaped."""
        rules = [{"operator": "OR", "keyword": "a.b*c?d+e"}]

        regex = self.pattern_service.rules_to_regex(rules)

        # Special chars should be escaped
        self.assertIn(r"a\.b\*c\?d\+e", regex)

        # Test matching
        pattern = re.compile(regex, re.IGNORECASE)
        self.assertIsNotNone(pattern.search("test a.b*c?d+e test"))
        self.assertIsNone(pattern.search("test abcde test"))  # Without special chars

    # =========================================================================
    # Human Description Tests
    # =========================================================================

    def test_generate_human_description_or(self):
        """Test human description for OR rules."""
        rules = [{"operator": "OR", "keyword": "amazon"}, {"operator": "OR", "keyword": "ebay"}]

        desc = self.pattern_service.generate_human_description(rules)

        self.assertIn("contains", desc.lower())
        self.assertIn("amazon", desc.lower())
        self.assertIn("ebay", desc.lower())

    def test_generate_human_description_and(self):
        """Test human description for AND rules."""
        rules = [
            {"operator": "AND", "keyword": "starbucks"},
            {"operator": "AND", "keyword": "coffee"},
        ]

        desc = self.pattern_service.generate_human_description(rules)

        self.assertIn("must contain", desc.lower())
        self.assertIn("starbucks", desc.lower())
        self.assertIn("coffee", desc.lower())

    def test_generate_human_description_mixed(self):
        """Test human description for mixed operators."""
        rules = [
            {"operator": "START_WITH", "keyword": "amazon"},
            {"operator": "AND", "keyword": "grocery"},
            {"operator": "NOT", "keyword": "gift"},
            {"operator": "END_WITH", "keyword": "JPY"},
        ]

        desc = self.pattern_service.generate_human_description(rules)

        self.assertIn("starts with", desc.lower())
        self.assertIn("amazon", desc.lower())
        self.assertIn("must contain", desc.lower())
        self.assertIn("grocery", desc.lower())
        self.assertIn("must not contain", desc.lower())
        self.assertIn("gift", desc.lower())
        self.assertIn("ends with", desc.lower())
        self.assertIn("JPY", desc)

    # =========================================================================
    # Visual Description Parsing Tests
    # =========================================================================

    def test_visual_description_to_rules(self):
        """Test parsing JSON visual_description back to rules."""
        visual_desc = '{"type":"visual_rule","version":1,"rules":[{"operator":"OR","keyword":"test"},{"operator":"AND","keyword":"keyword"}]}'

        rules = self.pattern_service.visual_description_to_rules(visual_desc)

        self.assertEqual(len(rules), 2)
        self.assertEqual(rules[0]["operator"], "OR")
        self.assertEqual(rules[0]["keyword"], "test")
        self.assertEqual(rules[1]["operator"], "AND")
        self.assertEqual(rules[1]["keyword"], "keyword")

    def test_visual_description_to_rules_invalid_json(self):
        """Test that invalid JSON returns empty rules."""
        rules = self.pattern_service.visual_description_to_rules("invalid json")

        self.assertEqual(len(rules), 0)

    # =========================================================================
    # Case Insensitivity Tests
    # =========================================================================

    def test_pattern_case_insensitive_and_operator(self):
        """Test that AND operator patterns are case-insensitive."""
        rules = [{"operator": "AND", "keyword": "SEVEN-ELEVEN"}]

        # Create pattern
        success, error, pattern_id = self.pattern_service.create_pattern(rules, "shopping")
        self.assertTrue(success)

        # Create a fresh ClassificationService to pick up the new pattern
        classification_service = self._create_classification_service()

        # Test against various cases
        test_cases = [
            ("SEVEN-ELEVEN", True),  # Uppercase (original)
            ("seven-eleven", True),  # Lowercase
            ("Seven-Eleven", True),  # Mixed case
            ("test seven-eleven test", True),  # Lowercase in context
            ("TEST SEVEN-ELEVEN TEST", True),  # Uppercase in context
        ]

        for description, should_match in test_cases:
            category, source = classification_service.classify("test_tx", description)
            if should_match:
                self.assertEqual(
                    category, "shopping", f"Expected '{description}' to match SEVEN-ELEVEN pattern"
                )
            else:
                self.assertNotEqual(
                    category,
                    "shopping",
                    f"Expected '{description}' to NOT match SEVEN-ELEVEN pattern",
                )

    def test_pattern_case_insensitive_or_operator(self):
        """Test that OR operator patterns are case-insensitive."""
        rules = [{"operator": "OR", "keyword": "AMAZON"}, {"operator": "OR", "keyword": "EBAY"}]

        success, error, pattern_id = self.pattern_service.create_pattern(rules, "shopping")
        self.assertTrue(success)

        # Create a fresh ClassificationService to pick up the new pattern
        classification_service = self._create_classification_service()

        # Test against various cases
        test_cases = [
            "AMAZON purchase",
            "amazon purchase",
            "Amazon Purchase",
            "bought from EBAY",
            "bought from ebay",
            "bought from eBay",
        ]

        for description in test_cases:
            category, source = classification_service.classify("test_tx", description)
            self.assertEqual(
                category, "shopping", f"Expected '{description}' to match OR pattern (AMAZON|EBAY)"
            )

    def test_pattern_case_insensitive_not_operator(self):
        """Test that NOT operator patterns are case-insensitive."""
        rules = [{"operator": "OR", "keyword": "AMAZON"}, {"operator": "NOT", "keyword": "GIFT"}]

        success, error, pattern_id = self.pattern_service.create_pattern(rules, "shopping")
        self.assertTrue(success)

        # Create a fresh ClassificationService to pick up the new pattern
        classification_service = self._create_classification_service()

        # Should match
        category, _ = classification_service.classify("tx1", "AMAZON purchase")
        self.assertEqual(category, "shopping")

        # Should NOT match (contains GIFT in any case)
        test_cases = [
            "AMAZON GIFT card",
            "AMAZON gift card",
            "AMAZON Gift Card",
        ]

        for description in test_cases:
            category, _ = classification_service.classify("test_tx", description)
            self.assertNotEqual(
                category,
                "shopping",
                f"Expected '{description}' to NOT match pattern (excludes GIFT)",
            )

    def test_pattern_not_checks_entire_string(self):
        """
        Test that NOT operator checks the ENTIRE string, not just the part after matching.

        Regression test for bug where "Contains test, Must NOT contain labs" incorrectly
        matched "Eight labs test" because NOT lookahead was placed after consuming "test",
        so it only checked the remaining empty string.
        """
        rules = [{"operator": "OR", "keyword": "test"}, {"operator": "NOT", "keyword": "labs"}]

        success, error, pattern_id = self.pattern_service.create_pattern(rules, "shopping")
        self.assertTrue(success)

        # Create a fresh ClassificationService to pick up the new pattern
        classification_service = self._create_classification_service()

        # These should NOT match (contain "labs")
        test_cases_no_match = [
            "Eight labs test",  # "labs" before "test"
            "Seven labs test",  # "labs" before "test"
            "test labs",  # "labs" after "test"
            "labs test labs",  # "labs" both before and after
        ]

        for description in test_cases_no_match:
            category, _ = classification_service.classify("test_tx", description)
            self.assertNotEqual(
                category, "shopping", f"Expected '{description}' to NOT match (contains 'labs')"
            )

        # These SHOULD match (contain "test" but not "labs")
        test_cases_match = [
            "test only",
            "Eight test",
            "test",
        ]

        for description in test_cases_match:
            category, _ = classification_service.classify("test_tx", description)
            self.assertEqual(
                category, "shopping", f"Expected '{description}' to match (has 'test', no 'labs')"
            )


if __name__ == "__main__":
    unittest.main()

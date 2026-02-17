"""
Tests for ClassificationService (application/services/classification_service.py).

Tests cover:
- Single transaction classification
- Batch classification
- classify_transactions (dict-based)
- recategorize_all
- set_manual_descriptions
- reload_patterns
- get_manual_assignments
- invalidate_embedding
- similarity_threshold property
- has_similarity_calculator property (true and false)
- investigate_similarity (success and no calculator)
"""

import os
import tempfile
import sqlite3
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from application.services.classification_service import ClassificationService
from domain.entities.transaction import Transaction, CategorySource, ENCRYPTED_PLACEHOLDER
from infrastructure.persistence.sqlite.repositories.manual_assignment_repository import SQLiteManualAssignmentDataSource
from infrastructure.persistence.sqlite.repositories.regexp_repository import SQLiteRegexpDataSource


USER_ID = "test_user"


class TestClassificationService(unittest.TestCase):
    """Test suite for ClassificationService with real SQLite database."""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.db_path = self.temp_db.name
        self.temp_db.close()
        os.environ['DATABASE_PATH'] = self.db_path

        # Create needed tables
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

        # Seed a manual assignment
        cursor.execute(
            "INSERT INTO manual_assignments (tx_id, category_id, user_id) VALUES (?, ?, ?)",
            ("tx_manual", "food", USER_ID))

        # Seed regex patterns
        cursor.execute(
            "INSERT INTO regexps (id, raw, name, internal_category, user_id, order_index, visual_description) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("regex1", ".*train.*", "Train Pattern", "transport", USER_ID, 0, ""))
        cursor.execute(
            "INSERT INTO regexps (id, raw, name, internal_category, user_id, order_index, visual_description) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("regex2", ".*coffee.*", "Coffee Pattern", "food", USER_ID, 1, ""))

        conn.commit()
        conn.close()

        # Create datasource instances
        self.ma_ds = SQLiteManualAssignmentDataSource(self.db_path, user_id=USER_ID)
        self.regexp_ds = SQLiteRegexpDataSource(self.db_path, user_id=USER_ID)
        self.mock_embedding_ds = MagicMock()

        # Create service with skip_similarity=True (no ML model needed)
        self.service = ClassificationService(
            user_id=USER_ID,
            manual_assignment_datasource=self.ma_ds,
            regexp_datasource=self.regexp_ds,
            embedding_datasource=self.mock_embedding_ds,
            db_path=self.db_path,
            skip_similarity=True
        )

    def tearDown(self):
        if 'DATABASE_PATH' in os.environ:
            del os.environ['DATABASE_PATH']
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    # --- classify single ---

    def test_classify_manual_assignment(self):
        """Test that manual assignment takes highest priority."""
        category, source = self.service.classify("tx_manual", "anything")
        self.assertEqual(category, "food")
        self.assertEqual(source, CategorySource.MANUAL)

    def test_classify_regexp_match(self):
        """Test regex-based classification."""
        category, source = self.service.classify("tx_new", "Morning train commute")
        self.assertEqual(category, "transport")
        self.assertEqual(source, CategorySource.REGEXP)

    def test_classify_no_match(self):
        """Test classification when nothing matches."""
        category, source = self.service.classify("tx_unknown", "Mystery purchase XYZ")
        self.assertIsNone(category)
        self.assertIsNone(source)

    # --- classify_batch ---

    def test_classify_batch(self):
        """Test batch classification of multiple transactions."""
        transactions = [
            ("tx_manual", "Sushi dinner"),
            ("tx_new1", "Train to Shibuya"),
            ("tx_new2", "Morning coffee latte"),
            ("tx_new3", "Unknown store purchase"),
        ]
        results = self.service.classify_batch(transactions)

        self.assertEqual(len(results), 4)
        # Manual assignment wins
        self.assertEqual(results["tx_manual"][0], "food")
        self.assertEqual(results["tx_manual"][1], CategorySource.MANUAL)
        # Regex matches
        self.assertEqual(results["tx_new1"][0], "transport")
        self.assertEqual(results["tx_new1"][1], CategorySource.REGEXP)
        self.assertEqual(results["tx_new2"][0], "food")
        self.assertEqual(results["tx_new2"][1], CategorySource.REGEXP)
        # No match
        self.assertIsNone(results["tx_new3"][0])
        self.assertIsNone(results["tx_new3"][1])

    # --- classify_transactions ---

    def test_classify_transactions(self):
        """Test classifying a dict of Transaction objects."""
        transactions = {
            "tx_manual": Transaction(
                id="tx_manual",
                date=datetime(2025, 1, 1, tzinfo=timezone.utc),
                amount=1000, description="Sushi", category="",
                source="Test", currency="JPY"),
            "tx_regexp": Transaction(
                id="tx_regexp",
                date=datetime(2025, 1, 2, tzinfo=timezone.utc),
                amount=500, description="Train ticket", category="",
                source="Test", currency="JPY"),
            "tx_none": Transaction(
                id="tx_none",
                date=datetime(2025, 1, 3, tzinfo=timezone.utc),
                amount=2000, description="Mystery", category="",
                source="Test", currency="JPY"),
        }
        result = self.service.classify_transactions(transactions)

        self.assertEqual(result["tx_manual"].category, "food")
        self.assertEqual(result["tx_manual"].category_source, CategorySource.MANUAL)
        self.assertEqual(result["tx_regexp"].category, "transport")
        self.assertEqual(result["tx_regexp"].category_source, CategorySource.REGEXP)
        self.assertIsNone(result["tx_none"].category)
        self.assertIsNone(result["tx_none"].category_source)

    # --- recategorize_all ---

    def test_recategorize_all(self):
        """Test recategorize_all is equivalent to classify_transactions."""
        transactions = {
            "tx_manual": Transaction(
                id="tx_manual",
                date=datetime(2025, 1, 1, tzinfo=timezone.utc),
                amount=1000, description="Lunch", category="old_category",
                source="Test", currency="JPY"),
        }
        result = self.service.recategorize_all(transactions)
        self.assertEqual(result["tx_manual"].category, "food")

    # --- set_manual_descriptions ---

    def test_set_manual_descriptions(self):
        """Test setting manual descriptions for similarity matching."""
        descriptions = {
            "tx_manual": "Sushi dinner",
            "tx_other": "Something else",
        }
        self.service.set_manual_descriptions(descriptions)

        # Verify internal state via classifier
        classifier = self.service.classifier
        # Only tx_manual is in manual_assignments, so only it should be in manual_descriptions
        self.assertIn("tx_manual", classifier.manual_descriptions)
        self.assertNotIn("tx_other", classifier.manual_descriptions)

    # --- reload_patterns ---

    def test_reload_patterns(self):
        """Test reloading patterns reinitializes the classifier."""
        # Get initial classifier
        classifier1 = self.service.classifier

        # Add a new regexp
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO regexps (id, raw, name, internal_category, user_id, order_index, visual_description) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("regex3", ".*pizza.*", "Pizza Pattern", "food", USER_ID, 2, ""))
        conn.commit()
        conn.close()

        # Reload
        self.service.reload_patterns()

        # Verify new pattern is picked up
        category, source = self.service.classify("tx_test", "Dominos pizza order")
        self.assertEqual(category, "food")
        self.assertEqual(source, CategorySource.REGEXP)

    # --- get_manual_assignments ---

    def test_get_manual_assignments(self):
        """Test getting manual assignments from classifier."""
        assignments = self.service.get_manual_assignments()
        self.assertIn("tx_manual", assignments)
        self.assertEqual(assignments["tx_manual"], "food")

    # --- invalidate_embedding ---

    def test_invalidate_embedding(self):
        """Test embedding invalidation calls datasource."""
        self.service.invalidate_embedding("tx_manual")
        self.mock_embedding_ds.invalidate_embedding.assert_called_once_with("tx_manual")

    def test_invalidate_embedding_no_datasource(self):
        """Test embedding invalidation with no datasource does not crash."""
        service = ClassificationService(
            user_id=USER_ID,
            manual_assignment_datasource=self.ma_ds,
            regexp_datasource=self.regexp_ds,
            embedding_datasource=None,
            db_path=self.db_path,
            skip_similarity=True
        )
        # Should not raise
        service.invalidate_embedding("tx_manual")

    # --- similarity_threshold property ---

    def test_similarity_threshold(self):
        """Test the similarity threshold property."""
        threshold = self.service.similarity_threshold
        self.assertEqual(threshold, 0.7)

    # --- has_similarity_calculator property ---

    def test_has_similarity_calculator_false(self):
        """Test has_similarity_calculator when skip_similarity=True."""
        self.assertFalse(self.service.has_similarity_calculator)

    def test_has_similarity_calculator_true(self):
        """Test has_similarity_calculator when a calculator is provided."""
        mock_calculator = MagicMock()
        service = ClassificationService(
            user_id=USER_ID,
            manual_assignment_datasource=self.ma_ds,
            regexp_datasource=self.regexp_ds,
            embedding_datasource=self.mock_embedding_ds,
            db_path=self.db_path,
            similarity_calculator=mock_calculator
        )
        self.assertTrue(service.has_similarity_calculator)

    # --- investigate_similarity ---

    def test_investigate_similarity_no_calculator(self):
        """Test investigate_similarity when no similarity calculator available."""
        result = self.service.investigate_similarity(
            tx_id="tx1",
            description="Test description",
            transactions={},
            categories={}
        )
        self.assertFalse(result['success'])
        self.assertIn("not available", result['error'])

    def test_investigate_similarity_success(self):
        """Test investigate_similarity with a working similarity calculator."""
        mock_calculator = MagicMock()
        # Return similarities above threshold
        mock_calculator.calculate_similarities.return_value = [
            ("tx_ref1", 0.85),
            ("tx_ref2", 0.6),  # Below threshold
        ]

        service = ClassificationService(
            user_id=USER_ID,
            manual_assignment_datasource=self.ma_ds,
            regexp_datasource=self.regexp_ds,
            embedding_datasource=self.mock_embedding_ds,
            db_path=self.db_path,
            similarity_calculator=mock_calculator
        )

        # Set manual descriptions so the classifier knows about them
        ref_tx = Transaction(
            id="tx_ref1",
            date=datetime(2025, 1, 1, tzinfo=timezone.utc),
            amount=1000, description="Reference lunch",
            category="food", source="Test", currency="JPY")

        transactions = {"tx_ref1": ref_tx}

        # Add manual assignment for the reference transaction
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO manual_assignments (tx_id, category_id, user_id) VALUES (?, ?, ?)",
            ("tx_ref1", "food", USER_ID))
        conn.commit()
        conn.close()

        # Reinitialize the service to pick up the new assignment
        ma_ds_fresh = SQLiteManualAssignmentDataSource(self.db_path, user_id=USER_ID)
        service = ClassificationService(
            user_id=USER_ID,
            manual_assignment_datasource=ma_ds_fresh,
            regexp_datasource=self.regexp_ds,
            embedding_datasource=self.mock_embedding_ds,
            db_path=self.db_path,
            similarity_calculator=mock_calculator
        )

        # Set manual descriptions
        service.set_manual_descriptions({"tx_manual": "Sushi", "tx_ref1": "Reference lunch"})

        from domain.entities.category import Category
        categories = {"food": Category("food", "Food", "Food category", "")}

        result = service.investigate_similarity(
            tx_id="tx_test",
            description="Lunch somewhere",
            transactions=transactions,
            categories=categories
        )

        self.assertTrue(result['success'])
        self.assertEqual(result['threshold'], 0.7)
        # tx_ref1 should be in similar_transactions (score 0.85 >= 0.7)
        self.assertEqual(len(result['similar_transactions']), 1)
        self.assertEqual(result['similar_transactions'][0]['tx_id'], "tx_ref1")
        self.assertAlmostEqual(result['similar_transactions'][0]['similarity_score'], 0.85, places=2)

    # --- embedding_datasource property ---

    def test_embedding_datasource_property(self):
        """Test that embedding_datasource property returns the datasource."""
        ds = self.service.embedding_datasource
        self.assertEqual(ds, self.mock_embedding_ds)


class TestClassificationServiceEncryptedTransactions(unittest.TestCase):
    """Test suite for encrypted transaction handling in classify_transactions."""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.db_path = self.temp_db.name
        self.temp_db.close()
        os.environ['DATABASE_PATH'] = self.db_path

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS categories (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL,
            parent_id TEXT DEFAULT '', user_id TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS manual_assignments (
            tx_id TEXT PRIMARY KEY, category_id TEXT NOT NULL, user_id TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS regexps (
            id TEXT PRIMARY KEY, raw TEXT NOT NULL, name TEXT NOT NULL,
            internal_category TEXT NOT NULL, user_id TEXT,
            order_index INTEGER NOT NULL DEFAULT 0, visual_description TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS embeddings (
            tx_id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
            embedding BLOB NOT NULL, description_hash TEXT NOT NULL,
            created_at TEXT NOT NULL)''')

        # Seed manual assignment for an encrypted tx
        cursor.execute(
            "INSERT INTO manual_assignments (tx_id, category_id, user_id) VALUES (?, ?, ?)",
            ("tx_enc_manual", "food", USER_ID))

        # Seed regex pattern
        cursor.execute(
            "INSERT INTO regexps (id, raw, name, internal_category, user_id, order_index, visual_description) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("regex1", ".*coffee.*", "Coffee Pattern", "food", USER_ID, 0, ""))

        conn.commit()
        conn.close()

        self.ma_ds = SQLiteManualAssignmentDataSource(self.db_path, user_id=USER_ID)
        self.regexp_ds = SQLiteRegexpDataSource(self.db_path, user_id=USER_ID)
        self.mock_embedding_ds = MagicMock()

        self.service = ClassificationService(
            user_id=USER_ID,
            manual_assignment_datasource=self.ma_ds,
            regexp_datasource=self.regexp_ds,
            embedding_datasource=self.mock_embedding_ds,
            db_path=self.db_path,
            skip_similarity=True,
        )

    def tearDown(self):
        if 'DATABASE_PATH' in os.environ:
            del os.environ['DATABASE_PATH']
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def _make_tx(self, tx_id, description, encrypted=False):
        return Transaction(
            id=tx_id,
            date=datetime(2025, 1, 1, tzinfo=timezone.utc),
            amount=1000, description=description, category="",
            source="Test", currency="JPY", encrypted=encrypted,
        )

    def test_encrypted_tx_with_manual_assignment_gets_none(self):
        """Encrypted placeholder gets no classification, even with a manual assignment."""
        txs = {"tx_enc_manual": self._make_tx("tx_enc_manual", ENCRYPTED_PLACEHOLDER, encrypted=True)}
        result = self.service.classify_transactions(txs)
        self.assertIsNone(result["tx_enc_manual"].category)
        self.assertIsNone(result["tx_enc_manual"].category_source)

    def test_encrypted_tx_without_manual_gets_none(self):
        """Encrypted placeholder without manual assignment gets None."""
        txs = {"tx_enc_none": self._make_tx("tx_enc_none", ENCRYPTED_PLACEHOLDER, encrypted=True)}
        result = self.service.classify_transactions(txs)
        self.assertIsNone(result["tx_enc_none"].category)
        self.assertIsNone(result["tx_enc_none"].category_source)

    def test_encrypted_tx_skips_regex(self):
        """Encrypted placeholder is not matched by regex, even if description matches."""
        # "[Encrypted]" doesn't match ".*coffee.*", but let's add a pattern that would match
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO regexps (id, raw, name, internal_category, user_id, order_index, visual_description) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("regex_enc", ".*Encrypted.*", "Encrypted Pattern", "misc", USER_ID, 1, ""))
        conn.commit()
        conn.close()

        # Reinitialize service to pick up new pattern
        service = ClassificationService(
            user_id=USER_ID,
            manual_assignment_datasource=self.ma_ds,
            regexp_datasource=SQLiteRegexpDataSource(self.db_path, user_id=USER_ID),
            embedding_datasource=self.mock_embedding_ds,
            db_path=self.db_path,
            skip_similarity=True,
        )

        txs = {"tx_enc": self._make_tx("tx_enc", ENCRYPTED_PLACEHOLDER, encrypted=True)}
        result = service.classify_transactions(txs)
        # Should NOT be categorized by regex — encrypted placeholders skip regex
        self.assertIsNone(result["tx_enc"].category)
        self.assertIsNone(result["tx_enc"].category_source)

    def test_mixed_encrypted_and_plaintext(self):
        """Both encrypted and plaintext transactions handled correctly in one call."""
        txs = {
            "tx_enc_manual": self._make_tx("tx_enc_manual", ENCRYPTED_PLACEHOLDER, encrypted=True),
            "tx_enc_none": self._make_tx("tx_enc_none", ENCRYPTED_PLACEHOLDER, encrypted=True),
            "tx_plain_regex": self._make_tx("tx_plain_regex", "Morning coffee latte"),
            "tx_plain_none": self._make_tx("tx_plain_none", "Mystery purchase"),
        }
        result = self.service.classify_transactions(txs)

        # Encrypted — no classification regardless of manual assignment
        self.assertIsNone(result["tx_enc_manual"].category)
        self.assertIsNone(result["tx_enc_manual"].category_source)
        self.assertIsNone(result["tx_enc_none"].category)
        self.assertIsNone(result["tx_enc_none"].category_source)
        # Plaintext matched by regex
        self.assertEqual(result["tx_plain_regex"].category, "food")
        self.assertEqual(result["tx_plain_regex"].category_source, CategorySource.REGEXP)
        # Plaintext no match
        self.assertIsNone(result["tx_plain_none"].category)

    def test_decrypted_encrypted_tx_classified_normally(self):
        """encrypted=True but real description (user unlocked) gets full classification."""
        txs = {"tx_dec": self._make_tx("tx_dec", "Morning coffee latte", encrypted=True)}
        result = self.service.classify_transactions(txs)
        # Should match the coffee regex
        self.assertEqual(result["tx_dec"].category, "food")
        self.assertEqual(result["tx_dec"].category_source, CategorySource.REGEXP)

    def test_encrypted_descriptions_not_used_as_similarity_reference(self):
        """[Encrypted] placeholder never passed to set_manual_descriptions."""
        mock_classifier = MagicMock()
        mock_classifier.manual_assignments = {}
        mock_classifier.classify_batch.return_value = {}

        service = ClassificationService(
            user_id=USER_ID,
            manual_assignment_datasource=self.ma_ds,
            regexp_datasource=self.regexp_ds,
            embedding_datasource=self.mock_embedding_ds,
            db_path=self.db_path,
            skip_similarity=True,
        )
        # Replace the internal classifier with our mock
        service._classifier = mock_classifier

        txs = {
            "tx_enc": self._make_tx("tx_enc", ENCRYPTED_PLACEHOLDER, encrypted=True),
            "tx_plain": self._make_tx("tx_plain", "Real description"),
        }
        service.classify_transactions(txs)

        # set_manual_descriptions should only receive the plaintext tx
        mock_classifier.set_manual_descriptions.assert_called_once()
        descriptions_arg = mock_classifier.set_manual_descriptions.call_args[0][0]
        self.assertNotIn("tx_enc", descriptions_arg)
        self.assertIn("tx_plain", descriptions_arg)
        self.assertEqual(descriptions_arg["tx_plain"], "Real description")


if __name__ == '__main__':
    unittest.main()

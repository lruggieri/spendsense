"""Tests for the SQLite embedding repository."""

import os
import sqlite3
import tempfile
import unittest

import numpy as np

from infrastructure.persistence.sqlite.repositories.embedding_repository import (
    SQLiteEmbeddingDataSource,
)


class TestSQLiteEmbeddingRepository(unittest.TestCase):
    """Tests for SQLiteEmbeddingDataSource embedding cache operations."""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.db_path = self.temp_db.name
        self.temp_db.close()

        # We need a transactions table since embeddings has a FK reference to it.
        # Create a minimal transactions table so the FK doesn't cause issues.
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE transactions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL
            )
        """)
        # Insert some sample transactions
        cursor.execute("INSERT INTO transactions (id, user_id) VALUES ('tx1', 'test_user')")
        cursor.execute("INSERT INTO transactions (id, user_id) VALUES ('tx2', 'test_user')")
        cursor.execute("INSERT INTO transactions (id, user_id) VALUES ('tx3', 'test_user')")
        conn.commit()
        conn.close()

        self.user_id = "test_user"
        # SQLiteEmbeddingDataSource creates its own table via _ensure_table_exists
        self.ds = SQLiteEmbeddingDataSource(self.db_path, self.user_id)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _make_embedding(self, dim=384):
        """Create a random numpy embedding vector."""
        return np.random.randn(dim).astype(np.float32)

    def test_save_embeddings_and_get_cached(self):
        """save_embeddings should store and get_cached_embeddings should retrieve them."""
        emb1 = self._make_embedding()
        emb2 = self._make_embedding()

        # Save embeddings: dict of tx_id -> (embedding, description)
        self.ds.save_embeddings(
            {
                "tx1": (emb1, "Coffee at Starbucks"),
                "tx2": (emb2, "Lunch at Subway"),
            }
        )

        # Retrieve cached embeddings
        transactions = [("tx1", "Coffee at Starbucks"), ("tx2", "Lunch at Subway")]
        cached, needs_encoding = self.ds.get_cached_embeddings(transactions)

        self.assertEqual(len(cached), 2)
        self.assertEqual(len(needs_encoding), 0)
        self.assertIn("tx1", cached)
        self.assertIn("tx2", cached)
        np.testing.assert_array_almost_equal(cached["tx1"], emb1)
        np.testing.assert_array_almost_equal(cached["tx2"], emb2)

    def test_get_cached_embeddings_not_found(self):
        """get_cached_embeddings should return needs_encoding for uncached txs."""
        transactions = [("tx1", "Some description")]
        cached, needs_encoding = self.ds.get_cached_embeddings(transactions)

        self.assertEqual(len(cached), 0)
        self.assertEqual(len(needs_encoding), 1)
        self.assertEqual(needs_encoding[0], ("tx1", "Some description"))

    def test_get_cached_embeddings_wrong_hash(self):
        """get_cached_embeddings should mark as needs_encoding if description changed."""
        emb = self._make_embedding()
        self.ds.save_embeddings({"tx1": (emb, "Old description")})

        # Request with a different description
        transactions = [("tx1", "New description")]
        cached, needs_encoding = self.ds.get_cached_embeddings(transactions)

        self.assertEqual(len(cached), 0)
        self.assertEqual(len(needs_encoding), 1)
        self.assertEqual(needs_encoding[0][0], "tx1")

    def test_get_cached_embeddings_empty_input(self):
        """get_cached_embeddings should handle empty transaction list."""
        cached, needs_encoding = self.ds.get_cached_embeddings([])
        self.assertEqual(cached, {})
        self.assertEqual(needs_encoding, [])

    def test_save_embeddings_empty(self):
        """save_embeddings with empty dict should not error."""
        self.ds.save_embeddings({})
        # No exception = success

    def test_invalidate_embedding(self):
        """invalidate_embedding should remove the cached embedding."""
        emb = self._make_embedding()
        self.ds.save_embeddings({"tx1": (emb, "Test description")})

        result = self.ds.invalidate_embedding("tx1")
        self.assertTrue(result)

        # Should no longer be cached
        cached, needs_encoding = self.ds.get_cached_embeddings([("tx1", "Test description")])
        self.assertEqual(len(cached), 0)
        self.assertEqual(len(needs_encoding), 1)

    def test_invalidate_embedding_not_found(self):
        """invalidate_embedding should return False for non-existent embedding."""
        result = self.ds.invalidate_embedding("nonexistent")
        self.assertFalse(result)

    def test_invalidate_all_embeddings(self):
        """invalidate_all should remove all embeddings for the user."""
        emb1 = self._make_embedding()
        emb2 = self._make_embedding()
        self.ds.save_embeddings(
            {
                "tx1": (emb1, "Desc 1"),
                "tx2": (emb2, "Desc 2"),
            }
        )

        deleted = self.ds.invalidate_all()
        self.assertEqual(deleted, 2)

        # Verify all are gone
        cached, needs_encoding = self.ds.get_cached_embeddings(
            [("tx1", "Desc 1"), ("tx2", "Desc 2")]
        )
        self.assertEqual(len(cached), 0)
        self.assertEqual(len(needs_encoding), 2)

    def test_invalidate_all_empty(self):
        """invalidate_all should return 0 when no embeddings exist."""
        deleted = self.ds.invalidate_all()
        self.assertEqual(deleted, 0)

    def test_get_cache_stats(self):
        """get_cache_stats should return correct statistics."""
        emb = self._make_embedding()
        self.ds.save_embeddings({"tx1": (emb, "Desc 1")})

        stats = self.ds.get_cache_stats()
        self.assertEqual(stats["total_cached"], 1)
        # We have 3 transactions in the DB
        self.assertEqual(stats["total_transactions"], 3)
        self.assertAlmostEqual(stats["cache_hit_rate"], 1 / 3 * 100, places=1)

    def test_save_embeddings_upsert(self):
        """save_embeddings should overwrite existing embeddings (INSERT OR REPLACE)."""
        emb1 = self._make_embedding()
        emb2 = self._make_embedding()

        self.ds.save_embeddings({"tx1": (emb1, "Old desc")})
        self.ds.save_embeddings({"tx1": (emb2, "New desc")})

        transactions = [("tx1", "New desc")]
        cached, needs_encoding = self.ds.get_cached_embeddings(transactions)
        self.assertEqual(len(cached), 1)
        np.testing.assert_array_almost_equal(cached["tx1"], emb2)

    def test_description_hash_static_method(self):
        """get_description_hash should produce consistent hashes."""
        hash1 = SQLiteEmbeddingDataSource.get_description_hash("hello world")
        hash2 = SQLiteEmbeddingDataSource.get_description_hash("hello world")
        hash3 = SQLiteEmbeddingDataSource.get_description_hash("different")

        self.assertEqual(hash1, hash2)
        self.assertNotEqual(hash1, hash3)


if __name__ == "__main__":
    unittest.main()

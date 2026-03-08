"""
SQLite datasource for embeddings.
"""

import sqlite3
from datetime import datetime, timezone
from typing import Dict, List, Tuple

import numpy as np

from domain.repositories.embedding_repository import EmbeddingRepository
from infrastructure.db_query_logger import get_logging_cursor


class SQLiteEmbeddingDataSource(EmbeddingRepository):
    """SQLite implementation of embedding datasource."""

    def __init__(self, db_path: str, user_id: str):
        """
        Initialize the datasource.

        Args:
            db_path: Path to SQLite database file
            user_id: User ID for multi-tenancy filtering
        """
        self.db_path = db_path
        self.user_id = user_id
        self._ensure_table_exists()

    def _ensure_table_exists(self):
        """Create embeddings table if it doesn't exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS embeddings (
                    tx_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    description_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(tx_id) REFERENCES transactions(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_embeddings_user_id
                ON embeddings(user_id)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_embeddings_hash
                ON embeddings(description_hash)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_embeddings_created_at
                ON embeddings(created_at)
            """)

            conn.commit()

        finally:
            conn.close()

    def get_cached_embeddings(
        self, transactions: List[Tuple[str, str]]
    ) -> Tuple[Dict[str, np.ndarray], List[Tuple[str, str]]]:
        """
        Load embeddings from cache for transactions whose descriptions haven't changed.

        Args:
            transactions: List of (tx_id, description) tuples

        Returns:
            Tuple of:
            - Dictionary mapping tx_id to cached embeddings (numpy arrays)
            - List of (tx_id, description) tuples that need encoding
        """
        if not transactions:
            return {}, []

        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        cached = {}
        needs_encoding = []

        # SQLite has a limit on the number of parameters (typically 999)
        # Use chunks to stay well below the limit
        CHUNK_SIZE = 500

        try:
            # Build mapping of tx_id to (description, hash)
            tx_map = {
                tx_id: (description, self.get_description_hash(description))
                for tx_id, description in transactions
            }

            # Fetch cached embeddings in chunks
            tx_ids = list(tx_map.keys())
            cached_results = {}

            for i in range(0, len(tx_ids), CHUNK_SIZE):
                chunk = tx_ids[i : i + CHUNK_SIZE]
                placeholders = ",".join("?" * len(chunk))
                cursor.execute(
                    f"SELECT tx_id, embedding, description_hash FROM embeddings WHERE tx_id IN ({placeholders}) AND user_id = ?",  # nosec B608
                    tuple(chunk) + (self.user_id,),
                )

                # Merge results from this chunk
                for row in cursor.fetchall():
                    cached_results[row[0]] = (row[1], row[2])

            # Check each transaction
            for tx_id, (description, current_hash) in tx_map.items():
                if tx_id in cached_results:
                    embedding_blob, cached_hash = cached_results[tx_id]
                    if cached_hash == current_hash:
                        # Cache hit - description unchanged
                        embedding = np.frombuffer(embedding_blob, dtype=np.float32)
                        cached[tx_id] = embedding
                    else:
                        # Description changed - need to re-encode
                        needs_encoding.append((tx_id, description))
                else:
                    # Cache miss - need to encode
                    needs_encoding.append((tx_id, description))

            return cached, needs_encoding

        finally:
            conn.close()

    def save_embeddings(self, embeddings: Dict[str, Tuple[np.ndarray, str]]) -> None:
        """
        Save embeddings to cache with description hashes.

        Args:
            embeddings: Dictionary mapping tx_id to (embedding, description) tuples
        """
        if not embeddings:
            return

        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        now = datetime.now(timezone.utc).isoformat()

        # Use chunks to avoid memory issues and keep transactions manageable
        CHUNK_SIZE = 500

        try:
            # Prepare all data for batch insert
            batch_data = [
                (
                    tx_id,
                    self.user_id,
                    embedding.astype(np.float32).tobytes(),
                    self.get_description_hash(description),
                    now,
                )
                for tx_id, (embedding, description) in embeddings.items()
            ]

            # Insert in chunks
            for i in range(0, len(batch_data), CHUNK_SIZE):
                chunk = batch_data[i : i + CHUNK_SIZE]
                cursor.executemany(
                    """
                    INSERT OR REPLACE INTO embeddings (tx_id, user_id, embedding, description_hash, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """,
                    chunk,
                )

            conn.commit()

        finally:
            conn.close()

    def invalidate_embedding(self, tx_id: str) -> bool:
        """
        Invalidate (delete) cached embedding for a transaction.

        Args:
            tx_id: Transaction ID

        Returns:
            True if embedding was deleted, False if it didn't exist
        """
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute(
                """
                DELETE FROM embeddings
                WHERE tx_id = ? AND user_id = ?
            """,
                (tx_id, self.user_id),
            )
            conn.commit()

            return cursor.rowcount > 0

        finally:
            conn.close()

    def invalidate_all(self) -> int:
        """
        Invalidate all cached embeddings for this user (useful for full recategorization).

        Returns:
            Number of embeddings deleted
        """
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute("DELETE FROM embeddings WHERE user_id = ?", (self.user_id,))
            deleted_count = cursor.rowcount
            conn.commit()

            return deleted_count

        finally:
            conn.close()

    def get_cache_stats(self) -> Dict[str, int]:
        """
        Get statistics about the embedding cache for this user.

        Returns:
            Dictionary with cache statistics
        """
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute("SELECT COUNT(*) FROM embeddings WHERE user_id = ?", (self.user_id,))
            total_cached = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM transactions WHERE user_id = ?", (self.user_id,))
            total_transactions = cursor.fetchone()[0]

            return {
                "total_cached": total_cached,
                "total_transactions": total_transactions,
                "cache_hit_rate": (
                    (total_cached / total_transactions * 100) if total_transactions > 0 else 0
                ),
            }

        finally:
            conn.close()

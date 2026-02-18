"""
Embedding datasource abstraction.

This module provides an abstract interface for storing and retrieving
transaction embeddings for the similarity calculator.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Tuple

import numpy as np


class EmbeddingRepository(ABC):
    """Abstract base class for embedding data sources."""

    @abstractmethod
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

    @abstractmethod
    def save_embeddings(self, embeddings: Dict[str, Tuple[np.ndarray, str]]) -> None:
        """
        Save embeddings to cache with description hashes.

        Args:
            embeddings: Dictionary mapping tx_id to (embedding, description) tuples
        """

    @abstractmethod
    def invalidate_embedding(self, tx_id: str) -> bool:
        """
        Invalidate (delete) cached embedding for a transaction.

        Args:
            tx_id: Transaction ID

        Returns:
            True if embedding was deleted, False if it didn't exist
        """

    @abstractmethod
    def invalidate_all(self) -> int:
        """
        Invalidate all cached embeddings (useful for full recategorization).

        Returns:
            Number of embeddings deleted
        """

    @abstractmethod
    def get_cache_stats(self) -> Dict[str, int]:
        """
        Get statistics about the embedding cache.

        Returns:
            Dictionary with cache statistics:
            - total_cached: Number of embeddings in cache
            - total_transactions: Total number of transactions
            - cache_hit_rate: Percentage of transactions with cached embeddings
        """

    @staticmethod
    def get_description_hash(description: str) -> str:
        """
        Generate hash of description for cache validation.

        Args:
            description: Transaction description text

        Returns:
            Hash string (implementation-specific format)

        Note:
            This is a static method because the hashing algorithm should be
            consistent across all implementations
        """
        import hashlib

        return hashlib.sha256(description.encode("utf-8")).hexdigest()

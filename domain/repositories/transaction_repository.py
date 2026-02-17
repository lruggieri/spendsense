"""
Transaction datasource abstraction.

This module provides an abstract interface for transaction storage, allowing easy migration from one source to another.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Set

from domain.entities.transaction import Transaction


class TransactionRepository(ABC):
    """Abstract interface for transaction storage."""

    @abstractmethod
    def get_all_transactions(self) -> List[Transaction]:
        """
        Retrieve all transactions from the datasource.

        Returns:
            List of all Transaction objects
        """

    @abstractmethod
    def add_transaction(self, transaction: Transaction) -> None:
        """
        Add a single transaction to the datasource.

        Args:
            transaction: Transaction object to add

        Note:
            Should handle duplicate IDs gracefully (skip or update)
        """

    @abstractmethod
    def add_transactions_batch(self, transactions: List[Transaction]) -> int:
        """
        Add multiple transactions to the datasource in a batch.

        Args:
            transactions: List of Transaction objects to add

        Returns:
            Number of new transactions added (excluding duplicates)

        Note:
            Should handle duplicate IDs gracefully (skip duplicates)
        """

    @abstractmethod
    def transaction_exists(self, tx_id: str) -> bool:
        """
        Check if a transaction with the given ID already exists.

        Args:
            tx_id: Transaction ID to check

        Returns:
            True if transaction exists, False otherwise
        """

    @abstractmethod
    def get_processed_ids(self) -> Set[str]:
        """
        Get all transaction IDs currently in the datasource.

        Returns:
            Set of all transaction IDs

        Note:
            Useful for deduplication when fetching new transactions
        """

    @abstractmethod
    def get_processed_mail_ids(self, source: Optional[str] = None) -> Set[str]:
        """
        Get all mail IDs currently in the datasource.

        Args:
            source: Optional source filter (e.g., "Sony Bank", "Amazon").
                    If provided, only returns mail IDs for that source.

        Returns:
            Set of all mail IDs (excluding None values)

        Note:
            Used for deduplication when fetching new emails.
            Multiple transactions can share the same mail_id.
        """

    @abstractmethod
    def get_transactions_by_source(self, source: str) -> List[Transaction]:
        """
        Get all transactions from a specific source.

        Args:
            source: Source name (e.g., "Sony Bank", "Amazon")

        Returns:
            List of transactions from that source
        """

    @abstractmethod
    def migrate_to_encrypted(self) -> int:
        """
        Encrypt all plaintext transactions for this user.

        Returns:
            Number of rows migrated.
        """

    @abstractmethod
    def migrate_to_plaintext(self) -> int:
        """
        Decrypt all encrypted transactions back to plaintext for this user.

        Returns:
            Number of rows migrated.
        """

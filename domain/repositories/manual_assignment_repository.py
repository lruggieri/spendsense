"""
Manual assignment datasource abstraction.

This module provides an abstract interface for storing and retrieving
manual category assignments for transactions.
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional


class ManualAssignmentRepository(ABC):
    """Abstract base class for manual category assignment data sources."""

    @abstractmethod
    def get_assignments(self) -> Dict[str, str]:
        """
        Fetch all manual category assignments.

        Returns:
            Dict[str, str]: A dictionary mapping transaction IDs to category IDs
        """
        pass

    @abstractmethod
    def add_assignment(self, tx_id: str, category_id: str) -> None:
        """
        Add or update a manual category assignment for a transaction.

        Args:
            tx_id: Transaction ID
            category_id: Category ID to assign

        Note:
            If assignment already exists, it should be updated
        """
        pass

    @abstractmethod
    def remove_assignment(self, tx_id: str) -> bool:
        """
        Remove a manual category assignment.

        Args:
            tx_id: Transaction ID

        Returns:
            True if assignment was removed, False if it didn't exist
        """
        pass

    @abstractmethod
    def add_assignments_batch(self, assignments: Dict[str, str]) -> int:
        """
        Add or update multiple manual assignments in a batch.

        Args:
            assignments: Dictionary mapping transaction IDs to category IDs

        Returns:
            Number of assignments added/updated
        """
        pass

    @abstractmethod
    def get_assignment(self, tx_id: str) -> Optional[str]:
        """
        Get the manual category assignment for a specific transaction.

        Args:
            tx_id: Transaction ID

        Returns:
            Category ID if assignment exists, None otherwise
        """
        pass

    @abstractmethod
    def has_assignment(self, tx_id: str) -> bool:
        """
        Check if a transaction has a manual assignment.

        Args:
            tx_id: Transaction ID

        Returns:
            True if assignment exists, False otherwise
        """
        pass

    @abstractmethod
    def get_assigned_tx_ids(self) -> set:
        """
        Get all transaction IDs that have manual assignments.

        Returns:
            Set of transaction IDs
        """
        pass

    @abstractmethod
    def count_assignments(self) -> int:
        """
        Get the total number of manual assignments.

        Returns:
            Number of assignments
        """
        pass

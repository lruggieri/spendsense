"""
Group datasource abstraction.

This module provides an abstract interface for storing and retrieving
transaction groups.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from domain.entities.group import Group


class GroupRepository(ABC):
    """Abstract base class for group data sources."""

    @abstractmethod
    def get_all_groups(self) -> List[Group]:
        """
        Fetch all groups.

        Returns:
            List[Group]: List of all groups for the user
        """
        pass

    @abstractmethod
    def get_group(self, group_id: str) -> Optional[Group]:
        """
        Get a specific group by ID.

        Args:
            group_id: Group ID to lookup

        Returns:
            Group object if found, None otherwise
        """
        pass

    @abstractmethod
    def create_group(self, group: Group) -> None:
        """
        Create a new group.

        Args:
            group: Group object to create

        Note:
            If a group with the same ID already exists, behavior is implementation-specific
        """
        pass

    @abstractmethod
    def delete_group(self, group_id: str) -> bool:
        """
        Delete a group.

        Args:
            group_id: Group ID to delete

        Returns:
            True if group was deleted, False if it didn't exist

        Note:
            Deleting a group should also remove it from all transactions
        """
        pass

    @abstractmethod
    def update_group(self, group_id: str, **fields) -> bool:
        """
        Update group fields.

        Args:
            group_id: Group ID to update
            **fields: Fields to update (e.g., name="New Name")

        Returns:
            True if group was updated, False if it didn't exist

        Note:
            This method uses **fields for flexibility to support future fields
            without changing the interface
        """
        pass

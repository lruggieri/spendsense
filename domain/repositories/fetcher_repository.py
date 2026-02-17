"""
Fetcher datasource abstraction.

This module provides an abstract interface for fetcher configuration storage, allowing easy migration from one database to another.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from domain.entities.fetcher import Fetcher


class FetcherRepository(ABC):
    """Abstract interface for fetcher configuration storage."""

    @abstractmethod
    def get_all_fetchers(self) -> List[Fetcher]:
        """
        Retrieve all fetchers from the datasource for this user.

        Returns:
            List of Fetcher entities (all versions)
        """
        pass

    @abstractmethod
    def get_enabled_fetchers_for_list(self) -> List[Fetcher]:
        """
        Retrieve only enabled fetchers for display in the list view.
        Returns one fetcher per group (the enabled version).

        Returns:
            List of enabled Fetcher entities (one per group)
        """
        pass

    @abstractmethod
    def get_fetcher_by_id(self, fetcher_id: str) -> Optional[Fetcher]:
        """
        Get a specific fetcher by ID.

        Args:
            fetcher_id: Fetcher ID to lookup

        Returns:
            Fetcher entity or None if not found
        """
        pass

    @abstractmethod
    def get_enabled_fetchers(self) -> List[Fetcher]:
        """
        Get all enabled fetchers for this user.

        Returns:
            List of enabled Fetcher entities
        """
        pass

    @abstractmethod
    def get_fetcher_versions(self, group_id: str) -> List[Fetcher]:
        """
        Get all versions of a fetcher by its group ID.

        Args:
            group_id: Group ID (shared by all versions)

        Returns:
            List of Fetcher entities ordered by version descending
        """
        pass

    @abstractmethod
    def get_enabled_version(self, group_id: str) -> Optional[Fetcher]:
        """
        Get the currently enabled version of a fetcher group.

        Args:
            group_id: Group ID (shared by all versions)

        Returns:
            The enabled Fetcher version or None if no enabled version
        """
        pass

    @abstractmethod
    def create_fetcher(self, fetcher: Fetcher) -> bool:
        """
        Create a new fetcher in the datasource.

        For new fetchers, group_id is set to id and version is set to 1.

        Args:
            fetcher: Fetcher entity to create

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    def update_fetcher(self, fetcher: Fetcher) -> bool:
        """
        Update an existing fetcher in place (for simple field updates like enabled toggle).

        Note: For configuration changes, use create_new_version() instead.

        Args:
            fetcher: Fetcher entity with updated values

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    def create_new_version(self, old_fetcher_id: str, new_fetcher: Fetcher) -> Optional[Fetcher]:
        """
        Create a new version of a fetcher (immutability semantics).

        This disables the old version and creates a new row with incremented version.

        Args:
            old_fetcher_id: ID of the fetcher being "edited"
            new_fetcher: New Fetcher entity with updated configuration

        Returns:
            The newly created Fetcher entity or None if failed
        """
        pass

    @abstractmethod
    def toggle_fetcher_enabled(self, fetcher_id: str) -> Optional[bool]:
        """
        Toggle the enabled status of a fetcher.

        When enabling a fetcher, disables any other enabled version in the same group.

        Args:
            fetcher_id: ID of the fetcher to toggle

        Returns:
            New enabled status (True/False) or None if failed
        """
        pass

    @abstractmethod
    def delete_fetcher(self, fetcher_id: str) -> bool:
        """
        Delete a fetcher from the datasource.

        Args:
            fetcher_id: ID of fetcher to delete

        Returns:
            True if successful, False otherwise
        """
        pass

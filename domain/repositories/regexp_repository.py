"""
Regexp datasource abstraction.

This module provides an abstract interface for regex pattern storage, allowing easy migration from one database to another.
"""

from abc import ABC, abstractmethod
from typing import List, Tuple, Optional
from domain.entities.regexp import Regexp


class RegexpRepository(ABC):
    """Abstract interface for regex pattern storage."""

    @abstractmethod
    def get_all_regexps(self) -> List[Regexp]:
        """
        Retrieve all regex patterns from the datasource.

        Returns:
            List of Regexp objects ordered by order_index (ascending)
        """
        pass

    @abstractmethod
    def get_regexp_by_id(self, regexp_id: str) -> Optional[Regexp]:
        """
        Get a specific regex pattern by ID.

        Args:
            regexp_id: Regex pattern ID to lookup

        Returns:
            Regexp object or None if not found
        """
        pass

    @abstractmethod
    def get_regexps_for_category(self, category_id: str) -> List[Regexp]:
        """
        Get all regex patterns for a specific category.

        Args:
            category_id: Category ID to filter by

        Returns:
            List of Regexp objects ordered by order_index (ascending)
        """
        pass

    @abstractmethod
    def get_all_regexps_with_metadata(self) -> List[Regexp]:
        """
        Retrieve all regex patterns with full metadata for UI display.

        Returns:
            List of Regexp objects ordered by order_index (ascending)

        Note:
            This method is equivalent to get_all_regexps() but kept for backward compatibility.
        """
        pass

    @abstractmethod
    def create_regexp(self, regexp_id: str, raw: str, name: str,
                      visual_description: str, category: str, order_index: int) -> bool:
        """
        Create a new regexp pattern.

        Args:
            regexp_id: Unique ID for the pattern
            raw: Generated regex pattern string
            name: Human-readable pattern name
            visual_description: JSON-encoded visual rules
            category: Category ID to assign matches to
            order_index: Pattern priority (lower = higher priority)

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    def update_regexp(self, regexp_id: str, raw: str = None, name: str = None,
                      visual_description: str = None, category: str = None) -> bool:
        """
        Update an existing regexp pattern.

        Args:
            regexp_id: ID of pattern to update
            raw: New regex pattern string (optional)
            name: New pattern name (optional)
            visual_description: New JSON visual rules (optional)
            category: New category ID (optional)

        Returns:
            True if successful, False otherwise

        Note:
            order_index is NOT updated here - use reorder_regexps() for that
        """
        pass

    @abstractmethod
    def delete_regexp(self, regexp_id: str) -> bool:
        """
        Delete a regexp pattern.

        Args:
            regexp_id: ID of pattern to delete

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    def reorder_regexps(self, order_updates: List[Tuple[str, int]]) -> bool:
        """
        Batch update order_index for multiple patterns (for drag-and-drop reordering).

        Args:
            order_updates: List of (pattern_id, new_order_index) tuples

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    def get_max_order_index(self) -> int:
        """
        Get the highest order_index value for this user.

        Returns:
            Maximum order_index, or 0 if no patterns exist
        """
        pass

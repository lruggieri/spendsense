"""
Category datasource abstraction.

This module provides an abstract interface for category storage, allowing easy migration from one database to another.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from domain.entities.category import Category


class CategoryRepository(ABC):
    """Abstract interface for category storage."""

    @abstractmethod
    def get_all_categories(self) -> List[Category]:
        """
        Retrieve all categories from the datasource.

        Returns:
            List of Category objects
        """

    @abstractmethod
    def get_category_by_id(self, category_id: str) -> Optional[Category]:
        """
        Get a specific category by ID.

        Args:
            category_id: Category ID to lookup

        Returns:
            Category object or None if not found
        """

    @abstractmethod
    def get_categories_dict(self) -> Dict[str, Category]:
        """
        Get all categories as a dictionary keyed by ID.

        Returns:
            Dictionary mapping category ID to Category object
        """

    @abstractmethod
    def create_category(self, category: Category) -> bool:
        """
        Create a new category in the datasource.

        Args:
            category: Category object to create

        Returns:
            True on success, False if category ID already exists
        """

    @abstractmethod
    def update_category(
        self, category_id: str, name: str = None, description: str = None, parent_id: str = None
    ) -> bool:
        """
        Update an existing category.

        Args:
            category_id: ID of category to update
            name: New name (optional)
            description: New description (optional)
            parent_id: New parent_id (optional)

        Returns:
            True on success, False if category not found
        """

    @abstractmethod
    def delete_category(self, category_id: str) -> bool:
        """
        Delete a category from the datasource.

        Args:
            category_id: ID of category to delete

        Returns:
            True on success, False if category not found
        """

    @abstractmethod
    def has_transactions(self, category_id: str) -> bool:
        """
        Check if a category has any transactions assigned to it.

        Args:
            category_id: ID of category to check

        Returns:
            True if category has transactions, False otherwise
        """

    @abstractmethod
    def has_children(self, category_id: str) -> bool:
        """
        Check if a category has any child categories.

        Args:
            category_id: ID of category to check

        Returns:
            True if category has children, False otherwise
        """

    @abstractmethod
    def get_transaction_count(self, category_id: str) -> int:
        """
        Get the number of transactions assigned to a category.

        Args:
            category_id: ID of category to check

        Returns:
            Number of transactions assigned to this category
        """

    @abstractmethod
    def has_regexps(self, category_id: str) -> bool:
        """
        Check if a category has any regex patterns assigned to it.

        Args:
            category_id: ID of category to check

        Returns:
            True if category has regex patterns, False otherwise
        """

    @abstractmethod
    def get_regexp_count(self, category_id: str) -> int:
        """
        Get the number of regex patterns assigned to a category.

        Args:
            category_id: ID of category to check

        Returns:
            Number of regex patterns assigned to this category
        """

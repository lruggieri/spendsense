"""
Category service for managing expense categories.

Handles category CRUD operations and hierarchy management.
"""

import logging
from typing import Optional, Dict, List, Tuple

from uuid6 import uuid7

from application.services.base_service import BaseService
from domain.entities.category import Category
from domain.entities.category_tree import ALL_CATEGORY_ID, UNKNOWN_CATEGORY_ID
from domain.repositories.category_repository import CategoryRepository

logger = logging.getLogger(__name__)


class CategoryService(BaseService):
    """
    Service for managing expense categories.

    Provides CRUD operations for categories with hierarchy support,
    including cycle detection and validation.
    """

    def __init__(self, user_id: str, category_datasource: CategoryRepository, db_path: Optional[str] = None):
        """
        Initialize CategoryService.

        Args:
            user_id: User ID for data isolation
            category_datasource: Category datasource implementation
            db_path: Optional database path
        """
        super().__init__(user_id, db_path)
        self.datasource = category_datasource
        self._categories: Dict[str, Category] = {}
        self._load_categories()

    def _load_categories(self):
        """Load categories from datasource."""
        category_list = self.datasource.get_all_categories()
        self._categories = {cat.id: cat for cat in category_list}

        # Add the "unknown" category for uncategorized transactions
        unknown_category = Category(
            UNKNOWN_CATEGORY_ID, "Unknown", "Uncategorized transactions", ""
        )
        self._categories[UNKNOWN_CATEGORY_ID] = unknown_category

    @property
    def categories(self) -> Dict[str, Category]:
        """Get all categories as a dictionary."""
        return self._categories

    def get_all_categories(self) -> List[Category]:
        """Get all categories as a list."""
        return list(self._categories.values())

    def get_categories_hierarchical(self) -> List[Tuple[Category, int]]:
        """
        Get categories in hierarchical order with depth level.

        Returns:
            List of tuples (category, depth) where depth indicates nesting level
        """
        result = []
        processed = set()

        def add_category_and_children(cat_id: str, depth: int = 0):
            """Recursively add category and its children."""
            if cat_id in processed or cat_id not in self._categories:
                return

            processed.add(cat_id)
            result.append((self._categories[cat_id], depth))

            # Find and add children
            for child_id, child_cat in self._categories.items():
                if child_cat.parent_id == cat_id and child_id not in processed:
                    add_category_and_children(child_id, depth + 1)

        # First, add all root categories (those without parent or with empty parent)
        root_categories = [
            cat_id
            for cat_id, cat in self._categories.items()
            if not cat.parent_id or cat.parent_id not in self._categories
        ]

        for cat_id in sorted(root_categories):
            add_category_and_children(cat_id)

        return result

    def get_descendant_category_ids(self, category_id: str) -> List[str]:
        """
        Get all descendant category IDs for a given category (including itself).

        Args:
            category_id: Parent category ID

        Returns:
            List of category IDs including the parent and all descendants
        """
        result = [category_id]

        # Find all direct children
        children = [
            cat_id for cat_id, cat in self._categories.items() if cat.parent_id == category_id
        ]

        # Recursively get descendants of each child
        for child_id in children:
            result.extend(self.get_descendant_category_ids(child_id))

        return result

    def count_categories(self) -> int:
        """
        Get the count of user-created categories (excluding system categories).

        Returns:
            Number of categories
        """
        # Exclude system categories (unknown, all)
        return len(
            [
                c
                for c in self._categories.values()
                if c.id not in (UNKNOWN_CATEGORY_ID, ALL_CATEGORY_ID)
            ]
        )

    def create_category(
        self, name: str, description: str = "", parent_id: str = ""
    ) -> Tuple[bool, str, str]:
        """
        Create a new category with auto-generated ID.

        Args:
            name: Category name (max 40 characters)
            description: Category description (optional)
            parent_id: Parent category ID (optional, empty string for root)

        Returns:
            Tuple of (success: bool, error_message: str, category_id: str)
        """
        # Validation
        name = name.strip()

        if not name:
            return (False, "Category name cannot be empty", "")

        if len(name) > 40:
            return (False, "Category name must be 40 characters or less", "")

        if parent_id and parent_id.strip():
            parent_id = parent_id.strip()
            if parent_id not in self._categories:
                return (False, f"Parent category '{parent_id}' does not exist", "")

        # Auto-generate category ID using uuid7 (time-ordered UUID)
        category_id = str(uuid7())

        # Create category
        new_category = Category(
            id=category_id,
            name=name,
            description=description.strip(),
            parent_id=parent_id if parent_id else "",
        )

        if self.datasource.create_category(new_category):
            # Refresh categories cache
            self._load_categories()
            return (True, "", category_id)
        else:
            return (False, "Failed to create category in database", "")

    def update_category(
        self, category_id: str, name: Optional[str] = None, description: Optional[str] = None, parent_id: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Update an existing category.

        Args:
            category_id: ID of category to update
            name: New name (optional, max 40 characters)
            description: New description (optional)
            parent_id: New parent ID (optional)

        Returns:
            Tuple of (success: bool, error_message: str)
        """
        # Validation
        if category_id in [ALL_CATEGORY_ID, UNKNOWN_CATEGORY_ID]:
            return (False, "Cannot modify system category")

        if category_id not in self._categories:
            return (False, f"Category '{category_id}' does not exist")

        if name is not None:
            if not name.strip():
                return (False, "Category name cannot be empty")
            if len(name.strip()) > 40:
                return (False, "Category name must be 40 characters or less")

        if parent_id is not None:
            parent_id = parent_id.strip() if parent_id.strip() else ""

            if parent_id == category_id:
                return (False, "Category cannot be its own parent")

            if parent_id and parent_id not in self._categories:
                return (False, f"Parent category '{parent_id}' does not exist")

            # Check for cycle
            if parent_id and self._would_create_cycle(category_id, parent_id):
                return (False, "Cannot create cycle in category hierarchy")

        # Update category
        if self.datasource.update_category(
            category_id,
            name.strip() if name else None,
            description.strip() if description else None,
            parent_id,
        ):
            # Refresh categories cache
            self._load_categories()
            return (True, "")
        else:
            return (False, "Failed to update category in database")

    def delete_category(self, category_id: str) -> Tuple[bool, str]:
        """
        Delete a category.

        Args:
            category_id: ID of category to delete

        Returns:
            Tuple of (success: bool, error_message: str)
        """
        # Validation
        if category_id in [ALL_CATEGORY_ID, UNKNOWN_CATEGORY_ID]:
            return (False, "Cannot delete system category")

        if category_id not in self._categories:
            return (False, f"Category '{category_id}' does not exist")

        # Check if category has children
        if self.datasource.has_children(category_id):
            return (
                False,
                "Cannot delete category with children. Please delete or move child categories first.",
            )

        # Check if category has regex patterns
        regexp_count = self.datasource.get_regexp_count(category_id)
        if regexp_count > 0:
            return (
                False,
                f"Cannot delete category with {regexp_count} regex pattern(s) assigned to it",
            )

        # Check if category has transactions
        transaction_count = self.datasource.get_transaction_count(category_id)
        if transaction_count > 0:
            return (
                False,
                f"Cannot delete category with {transaction_count} manually assigned transaction(s)",
            )

        # Check if any descendant has transactions
        if self._has_descendant_transactions(category_id):
            return (
                False,
                "Cannot delete category: one or more child categories have assigned transactions",
            )

        # Delete category
        if self.datasource.delete_category(category_id):
            # Refresh categories cache
            self._load_categories()
            return (True, "")
        else:
            return (False, "Failed to delete category from database")

    def _would_create_cycle(self, category_id: str, new_parent_id: str) -> bool:
        """
        Check if setting a category's parent would create a cycle.

        Args:
            category_id: The category being modified
            new_parent_id: The proposed new parent

        Returns:
            True if this would create a cycle, False otherwise
        """
        if not new_parent_id:
            return False

        # Traverse up from new_parent_id to root
        current_id = new_parent_id
        visited = set()

        while current_id:
            if current_id == category_id:
                # Found the category we're modifying in the parent chain
                return True

            if current_id in visited:
                # Cycle already exists in data (shouldn't happen, but be safe)
                return True

            visited.add(current_id)

            # Move to parent
            if current_id in self._categories:
                parent = self._categories[current_id].parent_id
                current_id = parent if parent else ""
            else:
                break

        return False

    def _has_descendant_transactions(self, category_id: str) -> bool:
        """
        Check if any descendant categories have transactions.

        Args:
            category_id: Parent category ID

        Returns:
            True if any descendant has transactions
        """
        # Get all descendant IDs (excluding the category itself)
        descendant_ids = self.get_descendant_category_ids(category_id)

        # Remove the category itself from the list
        descendant_ids = [cid for cid in descendant_ids if cid != category_id]

        # Check each descendant
        for desc_id in descendant_ids:
            if self.datasource.has_transactions(desc_id):
                return True

        return False

    def get_categories_as_dict_list(self) -> Dict[str, List[Category]]:
        """
        Get categories in the dict-list format expected by CategoryTree.

        Returns:
            Dictionary with "internal" key mapping to list of all categories
        """
        return {"internal": list(self._categories.values())}

    def reload(self):
        """Reload categories from datasource."""
        self._load_categories()

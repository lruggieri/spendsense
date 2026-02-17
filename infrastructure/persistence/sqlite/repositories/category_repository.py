"""
SQLite datasource for categories.
"""

import sqlite3
from typing import Dict, List

from domain.entities.category import Category
from domain.repositories.category_repository import CategoryRepository
from infrastructure.db_query_logger import get_logging_cursor


class SQLiteCategoryDataSource(CategoryRepository):
    """Datasource for reading categories from SQLite."""

    def __init__(self, db_path: str, user_id: str):
        """
        Initialize the datasource.

        Args:
            db_path: Path to SQLite database file
            user_id: User ID for multi-tenancy filtering
        """
        self.db_path = db_path
        self.user_id = user_id

    def get_all_categories(self) -> List[Category]:
        """
        Retrieve all categories from the database.

        Returns:
            List of Category objects
        """
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute(
                """
                SELECT id, name, description, parent_id
                FROM categories
                WHERE user_id = ?
                ORDER BY id
            """,
                (self.user_id,),
            )

            categories = []
            for row in cursor.fetchall():
                cat_id, name, description, parent_id = row
                categories.append(
                    Category(
                        id=cat_id,
                        name=name,
                        description=description,
                        parent_id=parent_id if parent_id else "",
                    )
                )

            return categories

        finally:
            conn.close()

    def get_category_by_id(self, category_id: str) -> Category | None:
        """
        Get a specific category by ID.

        Args:
            category_id: Category ID to lookup

        Returns:
            Category object or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute(
                """
                SELECT id, name, description, parent_id
                FROM categories
                WHERE id = ? AND user_id = ?
            """,
                (category_id, self.user_id),
            )

            row = cursor.fetchone()
            if row:
                cat_id, name, description, parent_id = row
                return Category(
                    id=cat_id,
                    name=name,
                    description=description,
                    parent_id=parent_id if parent_id else "",
                )
            return None

        finally:
            conn.close()

    def get_categories_dict(self) -> Dict[str, Category]:
        """
        Get all categories as a dictionary keyed by ID.

        Returns:
            Dictionary mapping category ID to Category object
        """
        categories = self.get_all_categories()
        return {cat.id: cat for cat in categories}

    def create_category(self, category: Category) -> bool:
        """
        Create a new category in the database.

        Args:
            category: Category object to create

        Returns:
            True on success, False if category ID already exists
        """
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute(
                """
                INSERT INTO categories (id, name, description, parent_id, user_id)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    category.id,
                    category.name,
                    category.description,
                    category.parent_id if category.parent_id else "",
                    self.user_id,
                ),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()

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
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            # Build dynamic UPDATE query based on provided fields
            updates = []
            params = []

            if name is not None:
                updates.append("name = ?")
                params.append(name)

            if description is not None:
                updates.append("description = ?")
                params.append(description)

            if parent_id is not None:
                updates.append("parent_id = ?")
                params.append(parent_id if parent_id else "")

            if not updates:
                return True  # Nothing to update

            params.extend([category_id, self.user_id])
            query = f"UPDATE categories SET {', '.join(updates)} WHERE id = ? AND user_id = ?"

            cursor.execute(query, params)
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def delete_category(self, category_id: str) -> bool:
        """
        Delete a category from the database.

        Args:
            category_id: ID of category to delete

        Returns:
            True on success, False if category not found
        """
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute(
                """
                DELETE FROM categories
                WHERE id = ? AND user_id = ?
            """,
                (category_id, self.user_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def has_transactions(self, category_id: str) -> bool:
        """
        Check if a category has any transactions assigned to it.

        Args:
            category_id: ID of category to check

        Returns:
            True if category has transactions, False otherwise
        """
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute(
                """
                SELECT COUNT(*) FROM manual_assignments
                WHERE category_id = ? AND user_id = ?
            """,
                (category_id, self.user_id),
            )
            count = cursor.fetchone()[0]
            return count > 0
        finally:
            conn.close()

    def has_children(self, category_id: str) -> bool:
        """
        Check if a category has any child categories.

        Args:
            category_id: ID of category to check

        Returns:
            True if category has children, False otherwise
        """
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute(
                """
                SELECT COUNT(*) FROM categories
                WHERE parent_id = ? AND user_id = ?
            """,
                (category_id, self.user_id),
            )
            count = cursor.fetchone()[0]
            return count > 0
        finally:
            conn.close()

    def get_transaction_count(self, category_id: str) -> int:
        """
        Get the number of transactions assigned to a category.

        Args:
            category_id: ID of category to check

        Returns:
            Number of transactions assigned to this category
        """
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute(
                """
                SELECT COUNT(*) FROM manual_assignments
                WHERE category_id = ? AND user_id = ?
            """,
                (category_id, self.user_id),
            )
            return cursor.fetchone()[0]
        finally:
            conn.close()

    def has_regexps(self, category_id: str) -> bool:
        """
        Check if a category has any regex patterns assigned to it.

        Args:
            category_id: ID of category to check

        Returns:
            True if category has regex patterns, False otherwise
        """
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute(
                """
                SELECT COUNT(*) FROM regexps
                WHERE internal_category = ? AND user_id = ?
            """,
                (category_id, self.user_id),
            )
            count = cursor.fetchone()[0]
            return count > 0
        finally:
            conn.close()

    def get_regexp_count(self, category_id: str) -> int:
        """
        Get the number of regex patterns assigned to a category.

        Args:
            category_id: ID of category to check

        Returns:
            Number of regex patterns assigned to this category
        """
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute(
                """
                SELECT COUNT(*) FROM regexps
                WHERE internal_category = ? AND user_id = ?
            """,
                (category_id, self.user_id),
            )
            return cursor.fetchone()[0]
        finally:
            conn.close()

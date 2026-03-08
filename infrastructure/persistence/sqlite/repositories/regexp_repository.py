"""
SQLite datasource for regex patterns.
"""

import logging
import sqlite3
from typing import List, Optional, Tuple

from domain.entities.regexp import Regexp
from domain.repositories.regexp_repository import RegexpRepository
from infrastructure.db_query_logger import get_logging_cursor

logger = logging.getLogger(__name__)


class SQLiteRegexpDataSource(RegexpRepository):
    """Datasource for reading regex patterns from SQLite."""

    def __init__(self, db_path: str, user_id: str):
        """
        Initialize the datasource.

        Args:
            db_path: Path to SQLite database file
            user_id: User ID for multi-tenancy filtering
        """
        self.db_path = db_path
        self.user_id = user_id

    def get_all_regexps(self) -> List[Regexp]:
        """
        Retrieve all regex patterns from the database.

        Returns:
            List of Regexp objects
        """
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute(
                """
                SELECT id, raw, name, visual_description, internal_category, order_index
                FROM regexps
                WHERE user_id = ?
                ORDER BY order_index ASC
            """,
                (self.user_id,),
            )

            return [
                Regexp(
                    id=row[0],
                    raw=row[1],
                    name=row[2],
                    visual_description=row[3],
                    internal_category=row[4],
                    order_index=row[5],
                )
                for row in cursor.fetchall()
            ]

        finally:
            conn.close()

    def get_regexp_by_id(self, regexp_id: str) -> Optional[Regexp]:
        """
        Get a specific regex pattern by ID.

        Args:
            regexp_id: Regex pattern ID to lookup

        Returns:
            Regexp object or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute(
                """
                SELECT id, raw, name, visual_description, internal_category, order_index
                FROM regexps
                WHERE id = ? AND user_id = ?
            """,
                (regexp_id, self.user_id),
            )

            row = cursor.fetchone()
            if row:
                return Regexp(
                    id=row[0],
                    raw=row[1],
                    name=row[2],
                    visual_description=row[3],
                    internal_category=row[4],
                    order_index=row[5],
                )
            return None

        finally:
            conn.close()

    def get_regexps_for_category(self, category_id: str) -> List[Regexp]:
        """
        Get all regex patterns for a specific category.

        Args:
            category_id: Category ID to filter by

        Returns:
            List of Regexp objects
        """
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute(
                """
                SELECT id, raw, name, visual_description, internal_category, order_index
                FROM regexps
                WHERE internal_category = ? AND user_id = ?
                ORDER BY order_index ASC
            """,
                (category_id, self.user_id),
            )

            return [
                Regexp(
                    id=row[0],
                    raw=row[1],
                    name=row[2],
                    visual_description=row[3],
                    internal_category=row[4],
                    order_index=row[5],
                )
                for row in cursor.fetchall()
            ]

        finally:
            conn.close()

    def get_all_regexps_with_metadata(self) -> List[Regexp]:
        """
        Retrieve all regex patterns with full metadata for UI display.

        Returns:
            List of Regexp objects ordered by order_index (ascending)

        Note:
            This method is equivalent to get_all_regexps() but kept for backward compatibility.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute(
                """
                SELECT id, raw, name, visual_description, internal_category, order_index
                FROM regexps
                WHERE user_id = ?
                ORDER BY order_index ASC
            """,
                (self.user_id,),
            )

            return [
                Regexp(
                    id=row[0],
                    raw=row[1],
                    name=row[2],
                    visual_description=row[3],
                    internal_category=row[4],
                    order_index=row[5],
                )
                for row in cursor.fetchall()
            ]

        finally:
            conn.close()

    def create_regexp(
        self,
        regexp_id: str,
        raw: str,
        name: str,
        visual_description: str,
        category: str,
        order_index: int,
    ) -> bool:
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
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute(
                """
                INSERT INTO regexps (id, raw, name, visual_description, internal_category, user_id, order_index)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (regexp_id, raw, name, visual_description, category, self.user_id, order_index),
            )

            conn.commit()
            return True

        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"Error creating regexp: {e}")
            return False

        finally:
            conn.close()

    def update_regexp(
        self,
        regexp_id: str,
        raw: Optional[str] = None,
        name: Optional[str] = None,
        visual_description: Optional[str] = None,
        category: Optional[str] = None,
    ) -> bool:
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

        Note: order_index is NOT updated here - use reorder_regexps() for that
        """
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            # Build dynamic UPDATE query based on provided parameters
            update_fields = []
            params = []

            if raw is not None:
                update_fields.append("raw = ?")
                params.append(raw)

            if name is not None:
                update_fields.append("name = ?")
                params.append(name)

            if visual_description is not None:
                update_fields.append("visual_description = ?")
                params.append(visual_description)

            if category is not None:
                update_fields.append("internal_category = ?")
                params.append(category)

            if not update_fields:
                # Nothing to update
                return True

            # Add WHERE clause parameters
            params.extend([regexp_id, self.user_id])

            query = f"UPDATE regexps SET {', '.join(update_fields)} WHERE id = ? AND user_id = ?"  # nosec B608

            cursor.execute(query, tuple(params))
            conn.commit()

            return cursor.rowcount > 0

        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"Error updating regexp: {e}")
            return False

        finally:
            conn.close()

    def delete_regexp(self, regexp_id: str) -> bool:
        """
        Delete a regexp pattern.

        Args:
            regexp_id: ID of pattern to delete

        Returns:
            True if successful, False otherwise
        """
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute(
                """
                DELETE FROM regexps
                WHERE id = ? AND user_id = ?
            """,
                (regexp_id, self.user_id),
            )

            conn.commit()
            return cursor.rowcount > 0

        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"Error deleting regexp: {e}")
            return False

        finally:
            conn.close()

    def reorder_regexps(self, order_updates: List[Tuple[str, int]]) -> bool:
        """
        Batch update order_index for multiple patterns (for drag-and-drop reordering).

        Args:
            order_updates: List of (pattern_id, new_order_index) tuples

        Returns:
            True if successful, False otherwise
        """
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            # Use executemany for batch updates
            cursor.executemany(
                """
                UPDATE regexps
                SET order_index = ?
                WHERE id = ? AND user_id = ?
            """,
                [(order_idx, pattern_id, self.user_id) for pattern_id, order_idx in order_updates],
            )

            conn.commit()
            return True

        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"Error reordering regexps: {e}")
            return False

        finally:
            conn.close()

    def get_max_order_index(self) -> int:
        """
        Get the highest order_index value for this user.

        Returns:
            Maximum order_index, or 0 if no patterns exist
        """
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute(
                """
                SELECT MAX(order_index)
                FROM regexps
                WHERE user_id = ?
            """,
                (self.user_id,),
            )

            result = cursor.fetchone()
            return result[0] if result[0] is not None else 0

        finally:
            conn.close()

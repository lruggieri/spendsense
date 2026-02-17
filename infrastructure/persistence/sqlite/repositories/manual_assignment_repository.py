"""
SQLite implementation of ManualAssignmentRepository.

Stores manual category assignments in a SQLite database with table structure:
- tx_id (TEXT PRIMARY KEY)
- category_id (TEXT NOT NULL)
- user_id (TEXT) - for multi-tenancy support
"""

import sqlite3
from typing import Dict, Optional

from domain.repositories.manual_assignment_repository import ManualAssignmentRepository
from infrastructure.db_query_logger import get_logging_cursor


class SQLiteManualAssignmentDataSource(ManualAssignmentRepository):
    """SQLite-based implementation of manual category assignment datasource."""

    def __init__(self, db_filepath: str, user_id: str):
        """
        Initialize SQLite manual assignment datasource.

        Args:
            db_filepath: Path to the SQLite database file
            user_id: User ID for multi-tenancy filtering
        """
        self.db_filepath = db_filepath
        self.user_id = user_id
        self._ensure_db_exists()

    def _ensure_db_exists(self):
        """Create database and manual_assignments table if they don't exist."""
        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS manual_assignments (
                tx_id TEXT PRIMARY KEY,
                category_id TEXT NOT NULL,
                user_id TEXT NOT NULL
            )
        """)

        # Create index on category_id for faster reverse lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_category_id ON manual_assignments(category_id)
        """)

        conn.commit()
        conn.close()

    def get_assignments(self) -> Dict[str, str]:
        """
        Fetch all manual category assignments from the database.

        Returns:
            Dict[str, str]: A dictionary mapping transaction IDs to category IDs
        """
        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        cursor.execute(
            "SELECT tx_id, category_id FROM manual_assignments WHERE user_id = ?", (self.user_id,)
        )
        assignments = {row[0]: row[1] for row in cursor.fetchall()}

        conn.close()
        return assignments

    def add_assignment(self, tx_id: str, category_id: str) -> None:
        """
        Add or update a manual category assignment.

        Args:
            tx_id: Transaction ID
            category_id: Category ID to assign

        Note:
            If assignment already exists, it will be updated
        """
        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute(
                """
                INSERT OR REPLACE INTO manual_assignments (tx_id, category_id, user_id)
                VALUES (?, ?, ?)
            """,
                (tx_id, category_id, self.user_id),
            )
            conn.commit()
        finally:
            conn.close()

    def remove_assignment(self, tx_id: str) -> bool:
        """
        Remove a manual category assignment.

        Args:
            tx_id: Transaction ID

        Returns:
            True if assignment was removed, False if it didn't exist
        """
        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute(
                "DELETE FROM manual_assignments WHERE tx_id = ? AND user_id = ?",
                (tx_id, self.user_id),
            )
            conn.commit()
            removed = cursor.rowcount > 0
        finally:
            conn.close()

        return removed

    def add_assignments_batch(self, assignments: Dict[str, str]) -> int:
        """
        Add or update multiple manual assignments in a batch.

        Args:
            assignments: Dictionary mapping transaction IDs to category IDs

        Returns:
            Number of assignments added/updated
        """
        if not assignments:
            return 0

        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        try:
            # Use executemany for better performance
            cursor.executemany(
                """
                INSERT OR REPLACE INTO manual_assignments (tx_id, category_id, user_id)
                VALUES (?, ?, ?)
            """,
                [(tx_id, cat_id, self.user_id) for tx_id, cat_id in assignments.items()],
            )
            conn.commit()
            count = len(assignments)
        finally:
            conn.close()

        return count

    def get_assignment(self, tx_id: str) -> Optional[str]:
        """
        Get the manual category assignment for a specific transaction.

        Args:
            tx_id: Transaction ID

        Returns:
            Category ID if assignment exists, None otherwise
        """
        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        cursor.execute(
            "SELECT category_id FROM manual_assignments WHERE tx_id = ? AND user_id = ?",
            (tx_id, self.user_id),
        )
        row = cursor.fetchone()

        conn.close()
        return row[0] if row else None

    def has_assignment(self, tx_id: str) -> bool:
        """
        Check if a transaction has a manual assignment.

        Args:
            tx_id: Transaction ID

        Returns:
            True if assignment exists, False otherwise
        """
        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        cursor.execute(
            "SELECT 1 FROM manual_assignments WHERE tx_id = ? AND user_id = ? LIMIT 1",
            (tx_id, self.user_id),
        )
        exists = cursor.fetchone() is not None

        conn.close()
        return exists

    def get_assigned_tx_ids(self) -> set:
        """
        Get all transaction IDs that have manual assignments.

        Returns:
            Set of transaction IDs
        """
        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        cursor.execute("SELECT tx_id FROM manual_assignments WHERE user_id = ?", (self.user_id,))
        tx_ids = {row[0] for row in cursor.fetchall()}

        conn.close()
        return tx_ids

    def count_assignments(self) -> int:
        """
        Get the total number of manual assignments.

        Returns:
            Number of assignments
        """
        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        cursor.execute("SELECT COUNT(*) FROM manual_assignments WHERE user_id = ?", (self.user_id,))
        count = cursor.fetchone()[0]

        conn.close()
        return count

    def get_assignments_by_category(self, category_id: str) -> Dict[str, str]:
        """
        Get all assignments for a specific category (uses index for performance).

        Args:
            category_id: Category ID to filter by

        Returns:
            Dictionary mapping transaction IDs to category ID
        """
        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        cursor.execute(
            """
            SELECT tx_id, category_id
            FROM manual_assignments
            WHERE category_id = ? AND user_id = ?
        """,
            (category_id, self.user_id),
        )
        assignments = {row[0]: row[1] for row in cursor.fetchall()}

        conn.close()
        return assignments

    def clear_all_assignments(self) -> int:
        """
        Remove all manual assignments (useful for testing or reset).

        Returns:
            Number of assignments removed
        """
        conn = sqlite3.connect(self.db_filepath)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute("DELETE FROM manual_assignments WHERE user_id = ?", (self.user_id,))
            conn.commit()
            count = cursor.rowcount
        finally:
            conn.close()

        return count

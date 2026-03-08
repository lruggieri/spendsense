"""
SQLite datasource for groups.
"""

import sqlite3
from typing import List, Optional

from domain.entities.group import Group
from domain.repositories.group_repository import GroupRepository
from infrastructure.db_query_logger import get_logging_cursor


class SQLiteGroupDataSource(GroupRepository):
    """SQLite implementation of group datasource."""

    def __init__(self, db_path: str, user_id: str):
        """
        Initialize the datasource.

        Args:
            db_path: Path to SQLite database file
            user_id: User ID for multi-tenancy filtering
        """
        self.db_path = db_path
        self.user_id = user_id

    def get_all_groups(self) -> List[Group]:
        """
        Retrieve all groups from the database.

        Returns:
            List of Group objects
        """
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute(
                """
                SELECT id, name
                FROM groups
                WHERE user_id = ?
                ORDER BY name
            """,
                (self.user_id,),
            )

            groups = []
            for row in cursor.fetchall():
                group_id, name = row
                groups.append(Group(id=group_id, name=name))

            return groups

        finally:
            conn.close()

    def get_group(self, group_id: str) -> Optional[Group]:
        """
        Get a specific group by ID.

        Args:
            group_id: Group ID to lookup

        Returns:
            Group object if found, None otherwise
        """
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute(
                """
                SELECT id, name
                FROM groups
                WHERE id = ? AND user_id = ?
            """,
                (group_id, self.user_id),
            )

            row = cursor.fetchone()
            if row:
                group_id, name = row
                return Group(id=group_id, name=name)
            return None

        finally:
            conn.close()

    def create_group(self, group: Group) -> None:
        """
        Create a new group.

        Args:
            group: Group object to create
        """
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute(
                """
                INSERT INTO groups (id, name, user_id)
                VALUES (?, ?, ?)
            """,
                (group.id, group.name, self.user_id),
            )
            conn.commit()

        finally:
            conn.close()

    def delete_group(self, group_id: str) -> bool:
        """
        Delete a group.

        Args:
            group_id: Group ID to delete

        Returns:
            True if group was deleted, False if it didn't exist

        Note:
            This does NOT cascade to transactions. Use
            sqlite_transaction_datasource.remove_group_from_all_transactions()
            before calling this method if cascade is needed.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute(
                """
                DELETE FROM groups
                WHERE id = ? AND user_id = ?
            """,
                (group_id, self.user_id),
            )
            conn.commit()

            return cursor.rowcount > 0

        finally:
            conn.close()

    def update_group(self, group_id: str, **fields) -> bool:
        """
        Update group fields.

        Args:
            group_id: Group ID to update
            **fields: Fields to update (e.g., name="New Name")

        Returns:
            True if group was updated, False if it didn't exist

        Supported fields:
            - name: Group name
        """
        if not fields:
            return False

        # Build dynamic UPDATE query based on provided fields
        set_clauses = []
        params = []

        if "name" in fields:
            set_clauses.append("name = ?")
            params.append(fields["name"])

        if not set_clauses:
            # No valid fields provided
            return False

        # Add WHERE clause parameters
        params.extend([group_id, self.user_id])

        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            query = f"UPDATE groups SET {', '.join(set_clauses)} WHERE id = ? AND user_id = ?"  # nosec B608
            cursor.execute(query, tuple(params))
            conn.commit()

            return cursor.rowcount > 0

        finally:
            conn.close()

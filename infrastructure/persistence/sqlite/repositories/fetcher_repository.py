"""
SQLite datasource for fetcher configurations.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import List, Optional

from domain.entities.fetcher import Fetcher
from domain.repositories.fetcher_repository import FetcherRepository
from infrastructure.db_query_logger import get_logging_cursor

logger = logging.getLogger(__name__)


class SQLiteFetcherDataSource(FetcherRepository):
    """Datasource for reading and writing fetcher configurations from SQLite."""

    def __init__(self, db_path: str, user_id: str):
        """
        Initialize the datasource.

        Args:
            db_path: Path to SQLite database file
            user_id: User ID for multi-tenancy filtering
        """
        self.db_path = db_path
        self.user_id = user_id

    def get_all_fetchers(self) -> List[Fetcher]:
        """
        Retrieve all fetchers from the database for this user.

        Returns:
            List of Fetcher entities (all versions)
        """
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute(
                """
                SELECT id, user_id, name, from_emails, subject_filter,
                       amount_pattern, merchant_pattern, currency_pattern,
                       default_currency, negate_amount, enabled, created_at, updated_at,
                       group_id, version
                FROM fetchers
                WHERE user_id = ?
                ORDER BY created_at DESC
            """,
                (self.user_id,),
            )

            rows = cursor.fetchall()
            fetchers = []

            for row in rows:
                fetchers.append(self._row_to_fetcher(row))

            return fetchers

        finally:
            conn.close()

    def get_enabled_fetchers_for_list(self) -> List[Fetcher]:
        """
        Retrieve only enabled fetchers for display in the list view.
        Returns one fetcher per group (the enabled version).

        Returns:
            List of enabled Fetcher entities (one per group)
        """
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute(
                """
                SELECT id, user_id, name, from_emails, subject_filter,
                       amount_pattern, merchant_pattern, currency_pattern,
                       default_currency, negate_amount, enabled, created_at, updated_at,
                       group_id, version
                FROM fetchers
                WHERE user_id = ? AND enabled = 1
                ORDER BY created_at DESC
            """,
                (self.user_id,),
            )

            rows = cursor.fetchall()
            fetchers = []

            for row in rows:
                fetchers.append(self._row_to_fetcher(row))

            return fetchers

        finally:
            conn.close()

    def get_fetcher_by_id(self, fetcher_id: str) -> Optional[Fetcher]:
        """
        Get a specific fetcher by ID.

        Args:
            fetcher_id: Fetcher ID to lookup

        Returns:
            Fetcher entity or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute(
                """
                SELECT id, user_id, name, from_emails, subject_filter,
                       amount_pattern, merchant_pattern, currency_pattern,
                       default_currency, negate_amount, enabled, created_at, updated_at,
                       group_id, version
                FROM fetchers
                WHERE id = ? AND user_id = ?
            """,
                (fetcher_id, self.user_id),
            )

            row = cursor.fetchone()
            return self._row_to_fetcher(row) if row else None

        finally:
            conn.close()

    def get_enabled_fetchers(self) -> List[Fetcher]:
        """
        Get all enabled fetchers for this user.

        Returns:
            List of enabled Fetcher entities
        """
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute(
                """
                SELECT id, user_id, name, from_emails, subject_filter,
                       amount_pattern, merchant_pattern, currency_pattern,
                       default_currency, negate_amount, enabled, created_at, updated_at,
                       group_id, version
                FROM fetchers
                WHERE user_id = ? AND enabled = 1
                ORDER BY created_at DESC
            """,
                (self.user_id,),
            )

            rows = cursor.fetchall()
            fetchers = []

            for row in rows:
                fetchers.append(self._row_to_fetcher(row))

            return fetchers

        finally:
            conn.close()

    def get_fetcher_versions(self, group_id: str) -> List[Fetcher]:
        """
        Get all versions of a fetcher by its group ID.

        Args:
            group_id: Group ID (shared by all versions)

        Returns:
            List of Fetcher entities ordered by version descending
        """
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute(
                """
                SELECT id, user_id, name, from_emails, subject_filter,
                       amount_pattern, merchant_pattern, currency_pattern,
                       default_currency, negate_amount, enabled, created_at, updated_at,
                       group_id, version
                FROM fetchers
                WHERE user_id = ? AND group_id = ?
                ORDER BY version DESC
            """,
                (self.user_id, group_id),
            )

            rows = cursor.fetchall()
            return [self._row_to_fetcher(row) for row in rows]

        finally:
            conn.close()

    def get_enabled_version(self, group_id: str) -> Optional[Fetcher]:
        """
        Get the currently enabled version of a fetcher group.

        Args:
            group_id: Group ID (shared by all versions)

        Returns:
            The enabled Fetcher version or None if no enabled version
        """
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute(
                """
                SELECT id, user_id, name, from_emails, subject_filter,
                       amount_pattern, merchant_pattern, currency_pattern,
                       default_currency, negate_amount, enabled, created_at, updated_at,
                       group_id, version
                FROM fetchers
                WHERE user_id = ? AND group_id = ? AND enabled = 1
            """,
                (self.user_id, group_id),
            )

            row = cursor.fetchone()
            return self._row_to_fetcher(row) if row else None

        finally:
            conn.close()

    def create_fetcher(self, fetcher: Fetcher) -> bool:
        """
        Create a new fetcher in the database.

        For new fetchers, group_id is set to id and version is set to 1.

        Args:
            fetcher: Fetcher entity to create

        Returns:
            True if successful, False otherwise
        """
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            # Serialize from_emails list to JSON
            from_emails_json = json.dumps(fetcher.from_emails)

            # Convert datetime to ISO 8601 string
            created_at = (
                fetcher.created_at.isoformat()
                if fetcher.created_at
                else datetime.now(timezone.utc).isoformat()
            )
            updated_at = (
                fetcher.updated_at.isoformat()
                if fetcher.updated_at
                else datetime.now(timezone.utc).isoformat()
            )

            # For new fetchers, group_id = id and version = 1
            group_id = fetcher.group_id if fetcher.group_id else fetcher.id
            version = fetcher.version if fetcher.version else 1

            cursor.execute(
                """
                INSERT INTO fetchers (
                    id, user_id, name, from_emails, subject_filter,
                    amount_pattern, merchant_pattern, currency_pattern,
                    default_currency, negate_amount, enabled, created_at, updated_at,
                    group_id, version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    fetcher.id,
                    fetcher.user_id,
                    fetcher.name,
                    from_emails_json,
                    fetcher.subject_filter,
                    fetcher.amount_pattern,
                    fetcher.merchant_pattern,
                    fetcher.currency_pattern,
                    fetcher.default_currency,
                    1 if fetcher.negate_amount else 0,
                    1 if fetcher.enabled else 0,
                    created_at,
                    updated_at,
                    group_id,
                    version,
                ),
            )

            conn.commit()
            logger.info(
                f"Created fetcher {fetcher.id} ({fetcher.name}) v{version} for user {self.user_id}"
            )
            return True

        except Exception as e:
            logger.error(f"Error creating fetcher: {e}", exc_info=True)
            conn.rollback()
            return False

        finally:
            conn.close()

    def update_fetcher(self, fetcher: Fetcher) -> bool:
        """
        Update an existing fetcher in place (for simple field updates like enabled toggle).

        Note: For configuration changes, use create_new_version() instead.

        Args:
            fetcher: Fetcher entity with updated values

        Returns:
            True if successful, False otherwise
        """
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            # Serialize from_emails list to JSON
            from_emails_json = json.dumps(fetcher.from_emails)

            # Update timestamp
            updated_at = datetime.now(timezone.utc).isoformat()

            cursor.execute(
                """
                UPDATE fetchers
                SET name = ?,
                    from_emails = ?,
                    subject_filter = ?,
                    amount_pattern = ?,
                    merchant_pattern = ?,
                    currency_pattern = ?,
                    default_currency = ?,
                    negate_amount = ?,
                    enabled = ?,
                    updated_at = ?
                WHERE id = ? AND user_id = ?
            """,
                (
                    fetcher.name,
                    from_emails_json,
                    fetcher.subject_filter,
                    fetcher.amount_pattern,
                    fetcher.merchant_pattern,
                    fetcher.currency_pattern,
                    fetcher.default_currency,
                    1 if fetcher.negate_amount else 0,
                    1 if fetcher.enabled else 0,
                    updated_at,
                    fetcher.id,
                    self.user_id,
                ),
            )

            conn.commit()
            logger.info(f"Updated fetcher {fetcher.id} ({fetcher.name}) for user {self.user_id}")
            return True

        except Exception as e:
            logger.error(f"Error updating fetcher: {e}", exc_info=True)
            conn.rollback()
            return False

        finally:
            conn.close()

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
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            # Get the old fetcher to retrieve group_id and current max version
            cursor.execute(
                """
                SELECT group_id, MAX(version)
                FROM fetchers
                WHERE user_id = ? AND group_id = (
                    SELECT group_id FROM fetchers WHERE id = ? AND user_id = ?
                )
            """,
                (self.user_id, old_fetcher_id, self.user_id),
            )

            row = cursor.fetchone()
            if not row or not row[0]:
                logger.error(f"Could not find fetcher {old_fetcher_id} for versioning")
                return None

            group_id = row[0]
            current_max_version = row[1] or 1
            new_version = current_max_version + 1

            # Disable all other versions in this group
            cursor.execute(
                """
                UPDATE fetchers
                SET enabled = 0, updated_at = ?
                WHERE user_id = ? AND group_id = ? AND enabled = 1
            """,
                (datetime.now(timezone.utc).isoformat(), self.user_id, group_id),
            )

            # Serialize from_emails list to JSON
            from_emails_json = json.dumps(new_fetcher.from_emails)

            # Create new version
            now = datetime.now(timezone.utc).isoformat()

            cursor.execute(
                """
                INSERT INTO fetchers (
                    id, user_id, name, from_emails, subject_filter,
                    amount_pattern, merchant_pattern, currency_pattern,
                    default_currency, negate_amount, enabled, created_at, updated_at,
                    group_id, version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    new_fetcher.id,
                    self.user_id,
                    new_fetcher.name,
                    from_emails_json,
                    new_fetcher.subject_filter,
                    new_fetcher.amount_pattern,
                    new_fetcher.merchant_pattern,
                    new_fetcher.currency_pattern,
                    new_fetcher.default_currency,
                    1 if new_fetcher.negate_amount else 0,
                    1,  # New version is always enabled
                    now,
                    now,
                    group_id,
                    new_version,
                ),
            )

            conn.commit()
            logger.info(
                f"Created new version {new_version} of fetcher group {group_id} (new id: {new_fetcher.id})"
            )

            # Return the created fetcher with correct group_id and version
            new_fetcher.group_id = group_id
            new_fetcher.version = new_version
            new_fetcher.enabled = True
            return new_fetcher

        except Exception as e:
            logger.error(f"Error creating new version: {e}", exc_info=True)
            conn.rollback()
            return None

        finally:
            conn.close()

    def toggle_fetcher_enabled(self, fetcher_id: str) -> Optional[bool]:
        """
        Toggle the enabled status of a fetcher.

        When enabling a fetcher, disables any other enabled version in the same group.

        Args:
            fetcher_id: ID of the fetcher to toggle

        Returns:
            New enabled status (True/False) or None if failed
        """
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            # Get current fetcher
            cursor.execute(
                """
                SELECT enabled, group_id FROM fetchers
                WHERE id = ? AND user_id = ?
            """,
                (fetcher_id, self.user_id),
            )

            row = cursor.fetchone()
            if not row:
                return None

            current_enabled = bool(row[0])
            group_id = row[1]
            new_enabled = not current_enabled
            now = datetime.now(timezone.utc).isoformat()

            if new_enabled and group_id:
                # When enabling, first disable any other enabled version in the group
                cursor.execute(
                    """
                    UPDATE fetchers
                    SET enabled = 0, updated_at = ?
                    WHERE user_id = ? AND group_id = ? AND enabled = 1 AND id != ?
                """,
                    (now, self.user_id, group_id, fetcher_id),
                )

            # Toggle the current fetcher
            cursor.execute(
                """
                UPDATE fetchers
                SET enabled = ?, updated_at = ?
                WHERE id = ? AND user_id = ?
            """,
                (1 if new_enabled else 0, now, fetcher_id, self.user_id),
            )

            conn.commit()
            logger.info(f"Toggled fetcher {fetcher_id} to enabled={new_enabled}")
            return new_enabled

        except Exception as e:
            logger.error(f"Error toggling fetcher: {e}", exc_info=True)
            conn.rollback()
            return None

        finally:
            conn.close()

    def delete_fetcher(self, fetcher_id: str) -> bool:
        """
        Delete a fetcher from the database.

        Args:
            fetcher_id: ID of fetcher to delete

        Returns:
            True if successful, False otherwise
        """
        conn = sqlite3.connect(self.db_path)
        cursor = get_logging_cursor(conn)

        try:
            cursor.execute(
                """
                DELETE FROM fetchers
                WHERE id = ? AND user_id = ?
            """,
                (fetcher_id, self.user_id),
            )

            conn.commit()
            logger.info(f"Deleted fetcher {fetcher_id} for user {self.user_id}")
            return True

        except Exception as e:
            logger.error(f"Error deleting fetcher: {e}", exc_info=True)
            conn.rollback()
            return False

        finally:
            conn.close()

    def _row_to_fetcher(self, row) -> Fetcher:
        """
        Convert database row to Fetcher entity.

        Args:
            row: Database row tuple with 15 columns:
                (id, user_id, name, from_emails, subject_filter,
                 amount_pattern, merchant_pattern, currency_pattern,
                 default_currency, negate_amount, enabled, created_at, updated_at,
                 group_id, version)

        Returns:
            Fetcher entity
        """
        (
            id,
            user_id,
            name,
            from_emails_json,
            subject_filter,
            amount_pattern,
            merchant_pattern,
            currency_pattern,
            default_currency,
            negate_amount,
            enabled,
            created_at_str,
            updated_at_str,
            group_id,
            version,
        ) = row

        # Deserialize from_emails JSON array
        from_emails = json.loads(from_emails_json)

        # Parse ISO 8601 timestamps
        created_at = datetime.fromisoformat(created_at_str) if created_at_str else None
        updated_at = datetime.fromisoformat(updated_at_str) if updated_at_str else None

        return Fetcher(
            id=id,
            user_id=user_id,
            name=name,
            from_emails=from_emails,
            subject_filter=subject_filter or "",
            amount_pattern=amount_pattern or "",
            merchant_pattern=merchant_pattern,
            currency_pattern=currency_pattern,
            default_currency=default_currency or "USD",
            negate_amount=bool(negate_amount),
            enabled=bool(enabled),
            created_at=created_at,
            updated_at=updated_at,
            group_id=group_id or id,  # Default to id for backward compatibility
            version=version or 1,  # Default to 1 for backward compatibility
        )

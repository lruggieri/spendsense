"""
Fetcher service for managing email transaction fetchers.

Handles fetcher CRUD operations including versioning.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from uuid6 import uuid7

from application.services.base_service import BaseService
from application.services.user_settings_service import UserSettingsService
from domain.entities.fetcher import Fetcher
from domain.repositories.fetcher_repository import FetcherRepository

logger = logging.getLogger(__name__)


class FetcherService(BaseService):
    """
    Service for managing email transaction fetchers.

    Provides CRUD operations for fetchers with versioning support.
    """

    def __init__(
        self,
        user_id: str,
        fetcher_datasource: FetcherRepository,
        user_settings_service: UserSettingsService,
        db_path: Optional[str] = None,
    ):
        """
        Initialize FetcherService.

        Args:
            user_id: User ID for data isolation
            fetcher_datasource: Fetcher datasource implementation
            user_settings_service: UserSettingsService for settings
            db_path: Optional database path
        """
        super().__init__(user_id, db_path)
        self._user_settings_service = user_settings_service
        self._fetcher_datasource = fetcher_datasource

    def get_all_fetchers(self) -> List[Fetcher]:
        """
        Get all fetchers for the user (all versions).

        Returns:
            List of all Fetcher entities
        """
        return self._fetcher_datasource.get_all_fetchers()

    def get_enabled_fetchers(self) -> List[Fetcher]:
        """
        Get all enabled fetchers for the user.

        Returns:
            List of enabled Fetcher entities
        """
        return self._fetcher_datasource.get_enabled_fetchers()

    def get_enabled_fetchers_for_list(self) -> List[Fetcher]:
        """
        Get enabled fetchers for display in list views.

        Returns:
            List of enabled Fetcher entities (one per group)
        """
        return self._fetcher_datasource.get_enabled_fetchers_for_list()

    def count_fetchers(self) -> int:
        """
        Get the count of enabled fetchers for this user.

        Returns:
            Number of enabled fetchers
        """
        return len(self._fetcher_datasource.get_enabled_fetchers_for_list())

    def get_fetcher_by_id(self, fetcher_id: str) -> Optional[Fetcher]:
        """
        Get a specific fetcher by ID.

        Args:
            fetcher_id: Fetcher ID to lookup

        Returns:
            Fetcher entity or None if not found
        """
        return self._fetcher_datasource.get_fetcher_by_id(fetcher_id)

    def get_fetcher_versions(self, group_id: str) -> List[Fetcher]:
        """
        Get all versions of a fetcher by its group ID.

        Args:
            group_id: Group ID (shared by all versions)

        Returns:
            List of Fetcher entities ordered by version descending
        """
        return self._fetcher_datasource.get_fetcher_versions(group_id)

    def get_enabled_version(self, group_id: str) -> Optional[Fetcher]:
        """
        Get the currently enabled version of a fetcher group.

        Args:
            group_id: Group ID (shared by all versions)

        Returns:
            The enabled Fetcher version or None if no enabled version
        """
        return self._fetcher_datasource.get_enabled_version(group_id)

    def create_fetcher(
        self,
        name: str,
        from_emails: List[str],
        subject_filter: str,
        amount_pattern: str,
        merchant_pattern: str,
        currency_pattern: Optional[str] = None,
        default_currency: Optional[str] = None,
        negate_amount: bool = False,
    ) -> Tuple[bool, str, str]:
        """
        Create a new fetcher.

        Args:
            name: Fetcher name
            from_emails: List of sender email addresses
            subject_filter: Subject line filter
            amount_pattern: Regex pattern to extract amount
            merchant_pattern: Regex pattern to extract merchant name
            currency_pattern: Optional regex pattern to extract currency
            default_currency: Default currency if not extracted (defaults to user's default)
            negate_amount: Whether to negate amounts (for income)

        Returns:
            Tuple of (success: bool, error_message: str, fetcher_id: str)
        """
        # Validate required fields
        if not name or not name.strip():
            return (False, "Fetcher name is required", "")

        if not from_emails:
            return (False, "At least one sender email is required", "")

        if not amount_pattern:
            return (False, "Amount pattern is required", "")

        if not merchant_pattern:
            return (False, "Merchant pattern is required", "")

        # Use user's default currency if not provided
        if not default_currency:
            default_currency = self._user_settings_service.get_default_currency()

        # Validate currency
        if not self._user_settings_service.validate_currency(default_currency):
            return (False, f"Unsupported currency: {default_currency}", "")

        # Generate ID
        fetcher_id = str(uuid7())
        now = datetime.now(timezone.utc)

        # Create fetcher entity
        fetcher = Fetcher(
            id=fetcher_id,
            user_id=self.user_id,
            name=name.strip(),
            from_emails=from_emails,
            subject_filter=subject_filter or "",
            amount_pattern=amount_pattern,
            merchant_pattern=merchant_pattern,
            currency_pattern=currency_pattern or "",
            default_currency=default_currency,
            negate_amount=negate_amount,
            enabled=True,  # New fetchers are enabled by default
            created_at=now,
            updated_at=now,
            group_id=fetcher_id,  # New fetcher starts its own group
            version=1,
        )

        if self._fetcher_datasource.create_fetcher(fetcher):
            return (True, "", fetcher_id)
        else:
            return (False, "Failed to create fetcher in database", "")

    def update_fetcher(
        self,
        fetcher_id: str,
        name: Optional[str] = None,
        from_emails: Optional[List[str]] = None,
        subject_filter: Optional[str] = None,
        amount_pattern: Optional[str] = None,
        merchant_pattern: Optional[str] = None,
        currency_pattern: Optional[str] = None,
        default_currency: Optional[str] = None,
        negate_amount: Optional[bool] = None,
    ) -> Tuple[bool, str, str]:
        """
        Update a fetcher by creating a new version (immutability semantics).

        Args:
            fetcher_id: ID of fetcher to update
            name: New name (optional)
            from_emails: New sender emails (optional)
            subject_filter: New subject filter (optional)
            amount_pattern: New amount pattern (optional)
            merchant_pattern: New merchant pattern (optional)
            currency_pattern: New currency pattern (optional)
            default_currency: New default currency (optional)
            negate_amount: New negate amount flag (optional)

        Returns:
            Tuple of (success: bool, error_message: str, new_fetcher_id: str)
        """
        # Get existing fetcher
        existing = self._fetcher_datasource.get_fetcher_by_id(fetcher_id)
        if not existing:
            return (False, "Fetcher not found", "")

        # Use existing values if not provided
        final_name = name.strip() if name is not None else existing.name
        final_from_emails = from_emails if from_emails is not None else existing.from_emails
        final_subject_filter = (
            subject_filter if subject_filter is not None else existing.subject_filter
        )
        final_amount_pattern = (
            amount_pattern if amount_pattern is not None else existing.amount_pattern
        )
        final_merchant_pattern = (
            merchant_pattern if merchant_pattern is not None else existing.merchant_pattern
        )
        final_currency_pattern = (
            currency_pattern if currency_pattern is not None else existing.currency_pattern
        )
        final_default_currency = (
            default_currency if default_currency is not None else existing.default_currency
        )
        final_negate_amount = negate_amount if negate_amount is not None else existing.negate_amount

        # Validate
        if not final_name:
            return (False, "Fetcher name is required", "")

        if not final_from_emails:
            return (False, "At least one sender email is required", "")

        if not final_amount_pattern:
            return (False, "Amount pattern is required", "")

        if not final_merchant_pattern:
            return (False, "Merchant pattern is required", "")

        # Validate currency
        if not self._user_settings_service.validate_currency(final_default_currency):
            return (False, f"Unsupported currency: {final_default_currency}", "")

        # Generate new ID for the new version
        new_id = str(uuid7())
        now = datetime.now(timezone.utc)

        # Create new version entity
        new_fetcher = Fetcher(
            id=new_id,
            user_id=self.user_id,
            name=final_name,
            from_emails=final_from_emails,
            subject_filter=final_subject_filter,
            amount_pattern=final_amount_pattern,
            merchant_pattern=final_merchant_pattern,
            currency_pattern=final_currency_pattern,
            default_currency=final_default_currency,
            negate_amount=final_negate_amount,
            enabled=True,
            created_at=now,
            updated_at=now,
            group_id=existing.group_id,  # Keep same group
            version=0,  # Will be set by datasource
        )

        result = self._fetcher_datasource.create_new_version(fetcher_id, new_fetcher)
        if result:
            return (True, "", result.id)
        else:
            return (False, "Failed to update fetcher", "")

    def toggle_fetcher_enabled(self, fetcher_id: str) -> Tuple[bool, str, bool]:
        """
        Toggle the enabled status of a fetcher.

        Args:
            fetcher_id: ID of fetcher to toggle

        Returns:
            Tuple of (success: bool, error_message: str, new_enabled_status: bool)
        """
        result = self._fetcher_datasource.toggle_fetcher_enabled(fetcher_id)
        if result is not None:
            return (True, "", result)
        else:
            return (False, "Failed to toggle fetcher status", False)

    def delete_fetcher(self, fetcher_id: str) -> Tuple[bool, str]:
        """
        Delete a fetcher.

        Args:
            fetcher_id: ID of fetcher to delete

        Returns:
            Tuple of (success: bool, error_message: str)
        """
        if self._fetcher_datasource.delete_fetcher(fetcher_id):
            return (True, "")
        else:
            return (False, "Failed to delete fetcher")

    def delete_fetcher_group(self, group_id: str) -> Tuple[bool, str, int]:
        """
        Delete all versions of a fetcher group.

        Args:
            group_id: Group ID of the fetcher to delete

        Returns:
            Tuple of (success: bool, error_message: str, versions_deleted: int)
        """
        versions = self._fetcher_datasource.get_fetcher_versions(group_id)
        deleted = 0

        for fetcher in versions:
            if self._fetcher_datasource.delete_fetcher(fetcher.id):
                deleted += 1

        if deleted == len(versions):
            return (True, "", deleted)
        else:
            return (False, f"Only deleted {deleted} of {len(versions)} versions", deleted)

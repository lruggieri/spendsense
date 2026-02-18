"""
Group service for managing transaction groups.

Handles group CRUD operations and transaction grouping.
"""

import logging
from typing import List, Optional, Tuple

from uuid6 import uuid7

from application.services.base_service import BaseService
from application.services.transaction_service import TransactionService
from domain.entities.group import Group
from domain.repositories.group_repository import GroupRepository

logger = logging.getLogger(__name__)


class GroupService(BaseService):
    """
    Service for managing transaction groups.

    Provides CRUD operations for groups and transaction assignment.
    """

    def __init__(
        self,
        user_id: str,
        group_datasource: GroupRepository,
        transaction_service: TransactionService,
        db_path: Optional[str] = None,
    ):
        """
        Initialize GroupService.

        Args:
            user_id: User ID for data isolation
            group_datasource: Group datasource implementation
            transaction_service: TransactionService for transaction operations
            db_path: Optional database path
        """
        super().__init__(user_id, db_path)
        self._transaction_service = transaction_service
        self._group_datasource = group_datasource

    def get_all_groups(self) -> List[Group]:
        """
        Get all groups for the user.

        Returns:
            List of Group entities
        """
        return self._group_datasource.get_all_groups()

    def get_group_by_id(self, group_id: str) -> Optional[Group]:
        """
        Get a specific group by ID.

        Args:
            group_id: Group ID to lookup

        Returns:
            Group entity or None if not found
        """
        return self._group_datasource.get_group(group_id)

    def create_group(self, name: str) -> Tuple[bool, str, str]:
        """
        Create a new group.

        Args:
            name: Group name

        Returns:
            Tuple of (success: bool, error_message: str, group_id: str)
        """
        if not name or not name.strip():
            return (False, "Group name is required", "")

        # Generate ID
        group_id = str(uuid7())

        # Create group entity
        group = Group(id=group_id, name=name.strip())

        try:
            self._group_datasource.create_group(group)
            return (True, "", group_id)
        except Exception as e:
            logger.error(f"Error creating group: {e}")
            return (False, f"Failed to create group: {str(e)}", "")

    def update_group(self, group_id: str, name: Optional[str] = None) -> Tuple[bool, str]:
        """
        Update a group.

        Args:
            group_id: ID of group to update
            name: New name (optional)

        Returns:
            Tuple of (success: bool, error_message: str)
        """
        if name is not None and not name.strip():
            return (False, "Group name cannot be empty")

        # Check group exists
        existing = self._group_datasource.get_group(group_id)
        if not existing:
            return (False, "Group not found")

        if name is not None:
            if self._group_datasource.update_group(group_id, name=name.strip()):
                return (True, "")
            else:
                return (False, "Failed to update group")

        return (True, "")

    def delete_group(self, group_id: str, cascade: bool = True) -> Tuple[bool, str]:
        """
        Delete a group.

        Args:
            group_id: ID of group to delete
            cascade: If True, remove group from all transactions first

        Returns:
            Tuple of (success: bool, error_message: str)
        """
        # Check group exists
        existing = self._group_datasource.get_group(group_id)
        if not existing:
            return (False, "Group not found")

        # Cascade: remove group from all transactions
        if cascade:
            self._transaction_service.remove_group_from_all_transactions(group_id)

        if self._group_datasource.delete_group(group_id):
            return (True, "")
        else:
            return (False, "Failed to delete group")

    def add_transaction_to_group(self, tx_id: str, group_id: str) -> Tuple[bool, str]:
        """
        Add a transaction to a group.

        Args:
            tx_id: Transaction ID
            group_id: Group ID

        Returns:
            Tuple of (success: bool, error_message: str)
        """
        # Check group exists
        if not self._group_datasource.get_group(group_id):
            return (False, "Group not found")

        if self._transaction_service.add_group_to_transaction(tx_id, group_id):
            return (True, "")
        else:
            return (False, "Failed to add transaction to group")

    def remove_transaction_from_group(self, tx_id: str, group_id: str) -> Tuple[bool, str]:
        """
        Remove a transaction from a group.

        Args:
            tx_id: Transaction ID
            group_id: Group ID

        Returns:
            Tuple of (success: bool, error_message: str)
        """
        if self._transaction_service.remove_group_from_transaction(tx_id, group_id):
            return (True, "")
        else:
            return (False, "Failed to remove transaction from group")

    def add_transactions_to_group(self, tx_ids: List[str], group_id: str) -> Tuple[bool, str, int]:
        """
        Add multiple transactions to a group.

        Args:
            tx_ids: List of transaction IDs
            group_id: Group ID

        Returns:
            Tuple of (success: bool, error_message: str, count_updated: int)
        """
        # Check group exists
        if not self._group_datasource.get_group(group_id):
            return (False, "Group not found", 0)

        count = self._transaction_service.add_group_to_transactions_batch(tx_ids, group_id)
        return (True, "", count)

    def remove_transactions_from_group(
        self, tx_ids: List[str], group_id: str
    ) -> Tuple[bool, str, int]:
        """
        Remove multiple transactions from a group.

        Args:
            tx_ids: List of transaction IDs
            group_id: Group ID

        Returns:
            Tuple of (success: bool, error_message: str, count_updated: int)
        """
        count = self._transaction_service.remove_group_from_transactions_batch(tx_ids, group_id)
        return (True, "", count)

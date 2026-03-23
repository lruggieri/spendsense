"""
Transaction service for managing financial transactions.

Handles transaction CRUD operations and filtering.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from uuid6 import uuid7

from application.services.base_service import BaseService
from application.services.category_service import CategoryService
from application.services.user_settings_service import UserSettingsService
from application.services.utils import parse_date
from domain.entities.category_tree import UNKNOWN_CATEGORY_ID
from domain.entities.transaction import ENCRYPTED_PLACEHOLDER, CategorySource, Transaction
from domain.repositories.manual_assignment_repository import ManualAssignmentRepository
from domain.repositories.transaction_repository import TransactionRepository
from domain.services.amount_utils import to_minor_units

logger = logging.getLogger(__name__)


class TransactionService(BaseService):
    """
    Service for managing financial transactions.

    Provides CRUD operations for transactions, filtering,
    and category assignment.
    """

    def __init__(
        self,
        user_id: str,
        transaction_datasource: TransactionRepository,
        manual_assignment_datasource: ManualAssignmentRepository,
        category_service: CategoryService,
        user_settings_service: UserSettingsService,
        db_path: Optional[str] = None,
    ):
        """
        Initialize TransactionService.

        Args:
            user_id: User ID for data isolation
            transaction_datasource: Transaction datasource implementation
            manual_assignment_datasource: Manual assignment datasource implementation
            category_service: CategoryService for category operations
            user_settings_service: UserSettingsService for settings
            db_path: Optional database path
        """
        super().__init__(user_id, db_path)
        self._category_service = category_service
        self._user_settings_service = user_settings_service
        self._transaction_datasource = transaction_datasource
        self._manual_assignment_datasource = manual_assignment_datasource

    @property
    def categories(self) -> Dict:
        """Get categories from category service."""
        return self._category_service.categories

    def get_all_transactions(self) -> List[Transaction]:
        """
        Get all transactions for the user.

        Returns:
            List of Transaction entities
        """
        return self._transaction_datasource.get_all_transactions()

    def get_all_transactions_filtered(
        self,
        category_id: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        category_source: Optional[str] = None,
        transaction_source: Optional[str] = None,
        transactions: Optional[List[Transaction]] = None,
    ) -> List[Transaction]:
        """
        Get ALL transactions with optional filters.
        When filtering by category, includes transactions from child categories too.

        Args:
            category_id: Optional category ID to filter by (includes child categories)
            from_date: Optional start date filter (YYYY-MM-DD)
            to_date: Optional end date filter (YYYY-MM-DD)
            category_source: Optional category source to filter by (manual, regexp, similarity)
            transaction_source: Optional transaction source to filter by (e.g., "Sony Bank", "Amazon")
            transactions: Optional pre-loaded list (e.g. already-classified). If None, loads from DB.

        Returns:
            List of all transactions matching filters, sorted by date DESC
        """
        # Start with provided transactions or load from DB
        filtered_txs = (
            list(transactions)
            if transactions is not None
            else self._transaction_datasource.get_all_transactions()
        )
        categories = self._category_service.categories

        # Filter by category if specified (including all descendants)
        if category_id:
            if category_id == UNKNOWN_CATEGORY_ID:
                # Special case: "unknown" category includes transactions with no category
                # or with a category that doesn't exist (excluding the "unknown" category itself)
                valid_category_ids = set(categories.keys()) - {UNKNOWN_CATEGORY_ID}
                filtered_txs = [
                    tx
                    for tx in filtered_txs
                    if tx.category is None or tx.category not in valid_category_ids
                ]
            else:
                category_ids = self._category_service.get_descendant_category_ids(category_id)
                filtered_txs = [tx for tx in filtered_txs if tx.category in category_ids]

        # Filter by date range if specified
        if from_date:
            try:
                from_dt = parse_date(from_date)
                # Client sends full timezone-aware datetime
                filtered_txs = [tx for tx in filtered_txs if tx.date >= from_dt]
            except ValueError:
                pass  # Ignore invalid date format

        if to_date:
            try:
                to_dt = parse_date(to_date)
                # If it's a simple date string (no 'T'), extend to end of day
                if "T" not in to_date:
                    to_dt = to_dt.replace(hour=23, minute=59, second=59)
                filtered_txs = [tx for tx in filtered_txs if tx.date <= to_dt]
            except ValueError:
                pass  # Ignore invalid date format

        # Filter by category source if specified
        if category_source:
            filtered_txs = [
                tx
                for tx in filtered_txs
                if tx.category_source and tx.category_source.value == category_source
            ]

        # Filter by transaction source if specified
        if transaction_source:
            filtered_txs = [tx for tx in filtered_txs if tx.source == transaction_source]

        return sorted(filtered_txs, key=lambda tx: tx.date, reverse=True)

    def get_transaction_sources(self) -> List[str]:
        """
        Get all distinct transaction sources for the current user.

        Returns:
            List of unique source names, sorted alphabetically
        """
        transactions = self._transaction_datasource.get_all_transactions()
        sources = set(tx.source for tx in transactions)
        return sorted(list(sources))

    def get_transactions_by_source(self, source: str) -> List[Transaction]:
        """
        Get transactions filtered by source.

        Args:
            source: Transaction source (e.g., 'Manual', 'Sony Bank')

        Returns:
            List of transactions with the specified source
        """
        return self._transaction_datasource.get_transactions_by_source(source)

    def get_transactions_by_group(self, group_id: str) -> List[Transaction]:
        """
        Get transactions in a specific group.

        Args:
            group_id: Group ID to filter by

        Returns:
            List of transactions in the group
        """
        return self._transaction_datasource.get_transactions_by_group(group_id)

    def add_new_transaction(
        self,
        date_str: str,
        amount: str,
        description: str,
        category: str = "",
        comment: str = "",
        currency: Optional[str] = None,
        classifier=None,
    ) -> Tuple[bool, str]:
        """
        Add a new transaction manually. Source is automatically set to 'Manual'.
        Transaction ID is auto-generated using UUID7.

        Args:
            date_str: Date string (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)
            amount: Amount as string
            description: Transaction description
            category: Optional category ID to assign (if empty, will auto-classify)
            comment: Optional comment
            currency: ISO 4217 currency code (defaults to user's default currency)
            classifier: Optional classifier for auto-classification

        Returns:
            Tuple of (success: bool, error_message: str)
        """
        # Generate UUID7 for transaction ID
        tx_id = str(uuid7())

        # Validate inputs
        if not date_str or not amount or not description:
            return False, "Date, amount, and description are required"

        # Set currency to user's default if not provided
        if not currency:
            currency = self._user_settings_service.get_default_currency()

        # Validate currency
        if not self._user_settings_service.validate_currency(currency):
            return False, f"Unsupported currency: {currency}"

        # Validate category if provided
        if category and category not in self.categories:
            return False, f"Invalid category ID: {category}"

        try:
            # Parse date
            date = parse_date(date_str)
        except ValueError as e:
            return False, f"Invalid date format: {str(e)}"

        try:
            # Convert amount string to minor units (e.g., "5.99" USD -> 599 cents)
            amount_int = to_minor_units(amount, currency)
        except ValueError as e:
            return False, f"Invalid amount format: {str(e)}"

        # Determine category and category source
        if category:
            # User provided a category - use it as manual assignment
            final_category = category
            final_category_source = CategorySource.MANUAL
        elif classifier:
            # No category provided - use classifier to auto-assign
            final_category, final_category_source = classifier.classify(tx_id, description)
        else:
            # No classifier provided - leave uncategorized
            final_category = ""
            final_category_source = None

        # Create transaction object
        tx = Transaction(
            id=tx_id,
            date=date,
            amount=amount_int,
            description=description,
            category=final_category,
            source="Manual",  # Hardcoded to 'Manual'
            currency=currency,
            category_source=final_category_source,
            comment=comment,
            created_at=datetime.now(timezone.utc),
        )

        # Add to datasource
        try:
            self._transaction_datasource.add_transaction(tx)
        except Exception as e:
            return False, f"Failed to save transaction: {str(e)}"

        # If user provided a category, save to manual assignments via datasource
        if category:
            try:
                self._manual_assignment_datasource.add_assignment(tx_id, category)
            except Exception as e:
                return False, f"Failed to save manual assignment: {str(e)}"

        return True, ""

    def add_transactions_batch(self, transactions: List[Transaction]) -> int:
        """
        Add multiple transactions in a batch.

        Args:
            transactions: List of Transaction entities to add

        Returns:
            Number of transactions successfully added
        """
        return self._transaction_datasource.add_transactions_batch(transactions)

    def update_transaction(
        self,
        tx_id: str,
        date_str: str,
        amount: str,
        description: str,
        comment: str,
        currency: Optional[str] = None,
        embedding_datasource=None,
    ) -> Tuple[bool, str]:
        """
        Update all fields of a transaction.

        Args:
            tx_id: Transaction ID to update
            date_str: Date string (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)
            amount: Amount as string
            description: Transaction description
            comment: Comment text
            currency: ISO 4217 currency code (optional, keeps existing if not provided)
            embedding_datasource: Optional embedding datasource for cache invalidation

        Returns:
            Tuple of (success: bool, error_message: str)
        """
        # Validate inputs
        if not date_str or not amount or not description:
            return False, "Date, amount, and description are required"

        # Get existing transaction
        transactions = self._transaction_datasource.get_all_transactions()
        existing_tx = next((tx for tx in transactions if tx.id == tx_id), None)

        if not existing_tx:
            return False, "Transaction not found"

        if existing_tx.description == ENCRYPTED_PLACEHOLDER:
            return False, "Encrypted transactions cannot be edited"

        # Set currency to existing if not provided
        if not currency:
            currency = existing_tx.currency

        # Validate currency
        if not self._user_settings_service.validate_currency(currency):
            return False, f"Unsupported currency: {currency}"

        try:
            # Parse date
            date = parse_date(date_str)
        except ValueError as e:
            return False, f"Invalid date format: {str(e)}"

        try:
            # Convert amount string to minor units (e.g., "5.99" USD -> 599 cents)
            amount_int = to_minor_units(amount, currency)
        except ValueError as e:
            return False, f"Invalid amount format: {str(e)}"

        # Check if description changed (need to invalidate embedding cache)
        old_description = existing_tx.description
        description_changed = old_description != description

        # Update transaction in datasource
        if self._transaction_datasource.update_transaction(
            tx_id, date, amount_int, description, comment, currency
        ):
            # Invalidate embedding cache if description changed
            if description_changed and embedding_datasource:
                logger.debug(f"Description changed for tx {tx_id}, invalidating embedding cache")
                embedding_datasource.invalidate_embedding(tx_id)

            return True, ""

        return False, "Failed to update transaction"

    def assign_category(self, tx_id: str, category_id: str):
        """
        Assign a category to a transaction and save via datasource.

        Args:
            tx_id: Transaction ID
            category_id: Category ID to assign
        """
        self._manual_assignment_datasource.add_assignment(tx_id, category_id)

    def assign_categories_bulk(self, new_assignments: Dict[str, str]):
        """
        Assign categories to multiple transactions at once and save via datasource.
        If a category is set to empty string, removes the manual assignment.

        Args:
            new_assignments: Dictionary mapping tx_id to category_id (empty string removes assignment)
        """
        # Separate removals and additions
        to_add = {}
        to_remove = []

        for tid, cat in new_assignments.items():
            if cat == "":
                # Empty string means remove the manual assignment
                to_remove.append(tid)
            else:
                # Add or update the assignment
                to_add[tid] = cat

        # Process removals
        for tid in to_remove:
            self._manual_assignment_datasource.remove_assignment(tid)

        # Process additions/updates in batch
        if to_add:
            self._manual_assignment_datasource.add_assignments_batch(to_add)

    def get_processed_mail_ids(self) -> set:
        """
        Get set of processed mail IDs for deduplication.

        Returns:
            Set of mail IDs that have already been processed
        """
        return self._transaction_datasource.get_processed_mail_ids()

    def filter_imported_mail_ids(self, candidate_ids: list) -> set:
        """
        Given a list of candidate mail IDs, return the subset already imported.

        More efficient than get_processed_mail_ids() for targeted dedup checks
        because it uses WHERE mail_id IN (...) instead of loading all IDs.

        Args:
            candidate_ids: Mail IDs to check

        Returns:
            Set of mail IDs from candidate_ids that already exist
        """
        return self._transaction_datasource.filter_imported_mail_ids(candidate_ids)

    def get_last_transaction_date(self) -> Optional[datetime]:
        """
        Get the date of the most recent transaction.

        Returns:
            Datetime of last transaction or None if no transactions
        """
        return self._transaction_datasource.get_last_transaction_date()

    def add_group_to_transaction(self, tx_id: str, group_id: str) -> bool:
        """
        Add a group to a transaction.

        Args:
            tx_id: Transaction ID
            group_id: Group ID to add

        Returns:
            True if successful
        """
        return self._transaction_datasource.add_group_to_transaction(tx_id, group_id)

    def remove_group_from_transaction(self, tx_id: str, group_id: str) -> bool:
        """
        Remove a group from a transaction.

        Args:
            tx_id: Transaction ID
            group_id: Group ID to remove

        Returns:
            True if successful
        """
        return self._transaction_datasource.remove_group_from_transaction(tx_id, group_id)

    def add_group_to_transactions_batch(self, tx_ids: List[str], group_id: str) -> int:
        """
        Add a group to multiple transactions.

        Args:
            tx_ids: List of transaction IDs
            group_id: Group ID to add

        Returns:
            Number of transactions updated
        """
        return self._transaction_datasource.add_group_to_transactions_batch(tx_ids, group_id)

    def remove_group_from_transactions_batch(self, tx_ids: List[str], group_id: str) -> int:
        """
        Remove a group from multiple transactions.

        Args:
            tx_ids: List of transaction IDs
            group_id: Group ID to remove

        Returns:
            Number of transactions updated
        """
        return self._transaction_datasource.remove_group_from_transactions_batch(tx_ids, group_id)

    def remove_group_from_all_transactions(self, group_id: str) -> int:
        """
        Remove a group from all transactions (cascade delete).

        Args:
            group_id: Group ID to remove

        Returns:
            Number of transactions updated
        """
        return self._transaction_datasource.remove_group_from_all_transactions(group_id)

"""
Tests for SQLiteTransactionDataSource.

Tests cover:
- Database creation and initialization
- Single and batch transaction operations
- Duplicate handling
- Datetime precision
- Filtering (by source, by date range)
- Getting processed IDs
- Field encryption at rest
"""

import base64
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from domain.entities.transaction import ENCRYPTED_PLACEHOLDER, Transaction
from infrastructure.persistence.sqlite.repositories.transaction_repository import (
    SQLiteTransactionDataSource,
)


@pytest.fixture
def temp_db():
    """Create a temporary database file."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield db_path
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def datasource(temp_db):
    """Create a SQLiteTransactionDataSource instance."""
    return SQLiteTransactionDataSource(temp_db, user_id="test_user")


class TestDatabaseCreation:
    """Test database initialization."""

    def test_database_creation(self, temp_db):
        """Test that database and table are created automatically."""
        # Delete the temp file so datasource creates it
        os.unlink(temp_db)

        datasource = SQLiteTransactionDataSource(temp_db, user_id="test_user")

        # Verify database file exists
        assert os.path.exists(temp_db)

        # Verify empty at start
        count = datasource.get_transaction_count()
        assert count == 0


class TestSingleTransaction:
    """Test single transaction operations."""

    def test_add_single_transaction(self, datasource):
        """Test adding a single transaction."""
        # Create test transaction
        tx = Transaction(
            id="test_tx_1",
            date=datetime(2025, 10, 26, 14, 32, 45),
            amount=1000,
            description="Test Transaction",
            category="",
            source="Test Source",
            comment="Test comment",
            currency="JPY",
        )

        datasource.add_transaction(tx)

        # Verify transaction was added
        assert datasource.transaction_exists("test_tx_1")

        # Verify count
        count = datasource.get_transaction_count()
        assert count == 1

        # Retrieve and verify
        all_txs = datasource.get_all_transactions()
        assert len(all_txs) == 1
        retrieved = all_txs[0]

        assert retrieved.id == "test_tx_1"
        assert retrieved.date == datetime(2025, 10, 26, 14, 32, 45, tzinfo=timezone.utc)
        assert retrieved.amount == 1000
        assert retrieved.description == "Test Transaction"
        assert retrieved.source == "Test Source"
        assert retrieved.comment == "Test comment"


class TestDuplicateHandling:
    """Test duplicate transaction handling."""

    def test_duplicate_handling(self, datasource):
        """Test that duplicate IDs are handled gracefully."""
        # Add first transaction
        tx1 = Transaction(
            id="dup_tx",
            date=datetime(2025, 10, 26, 10, 0, 0),
            amount=1000,
            description="Original",
            category="",
            source="Test",
            comment="",
            currency="JPY",
        )
        datasource.add_transaction(tx1)

        # Try to add duplicate
        tx2 = Transaction(
            id="dup_tx",  # Same ID
            date=datetime(2025, 10, 26, 11, 0, 0),
            amount=2000,
            description="Duplicate",
            category="",
            source="Test",
            comment="",
            currency="JPY",
        )
        datasource.add_transaction(tx2)

        # Should only have 1 transaction (original)
        count = datasource.get_transaction_count()
        assert count == 1

        # Verify original is preserved
        all_txs = datasource.get_all_transactions()
        assert all_txs[0].description == "Original"


class TestBatchOperations:
    """Test batch transaction operations."""

    def test_batch_add(self, datasource):
        """Test adding multiple transactions in batch."""
        # Create batch of transactions
        transactions = [
            Transaction(
                id=f"batch_tx_{i}",
                date=datetime(2025, 10, 26, i, 0, 0),
                amount=1000 * i,
                description=f"Batch Transaction {i}",
                category="",
                source="Test",
                comment="",
                currency="JPY",
            )
            for i in range(1, 6)
        ]

        # Add batch
        added = datasource.add_transactions_batch(transactions)
        assert added == 5

        # Verify count
        count = datasource.get_transaction_count()
        assert count == 5

    def test_batch_with_duplicates(self, datasource):
        """Test batch add with some duplicates."""
        # Add initial batch
        initial_batch = [
            Transaction(
                id=f"batch_tx_{i}",
                date=datetime(2025, 10, 26, i, 0, 0),
                amount=1000 * i,
                description=f"Batch Transaction {i}",
                category="",
                source="Test",
                comment="",
                currency="JPY",
            )
            for i in range(1, 6)
        ]
        datasource.add_transactions_batch(initial_batch)

        # Add batch with some duplicates
        new_batch = [
            Transaction(
                id="batch_tx_1",  # Duplicate
                date=datetime(2025, 10, 27, 1, 0, 0),
                amount=9999,
                description="Duplicate",
                category="",
                source="Test",
                comment="",
                currency="JPY",
            ),
            Transaction(
                id="batch_tx_new",  # New
                date=datetime(2025, 10, 27, 2, 0, 0),
                amount=5000,
                description="New Transaction",
                category="",
                source="Test",
                comment="",
                currency="JPY",
            ),
        ]

        added = datasource.add_transactions_batch(new_batch)
        assert added == 1  # Only 1 new transaction added


class TestDatetimePrecision:
    """Test datetime precision handling."""

    def test_datetime_precision(self, datasource):
        """Test that datetime precision is preserved."""
        # Add transaction with precise timestamp
        tx = Transaction(
            id="precise_tx",
            date=datetime(2025, 10, 26, 14, 32, 45),
            amount=1000,
            description="Precise timestamp",
            category="",
            source="Test",
            comment="",
            currency="JPY",
        )
        datasource.add_transaction(tx)

        # Retrieve and verify precision
        retrieved = datasource.get_all_transactions()[0]
        assert retrieved.date.year == 2025
        assert retrieved.date.month == 10
        assert retrieved.date.day == 26
        assert retrieved.date.hour == 14
        assert retrieved.date.minute == 32
        assert retrieved.date.second == 45


class TestFiltering:
    """Test transaction filtering operations."""

    def test_get_by_source(self, datasource):
        """Test filtering transactions by source."""
        # Add transactions from different sources
        transactions = [
            Transaction(
                id="sony_1",
                date=datetime(2025, 10, 26, 10, 0, 0),
                amount=1000,
                description="Sony 1",
                category="",
                source="Sony Bank",
                comment="",
                currency="JPY",
            ),
            Transaction(
                id="sony_2",
                date=datetime(2025, 10, 26, 11, 0, 0),
                amount=2000,
                description="Sony 2",
                category="",
                source="Sony Bank",
                comment="",
                currency="JPY",
            ),
            Transaction(
                id="amazon_1",
                date=datetime(2025, 10, 26, 12, 0, 0),
                amount=3000,
                description="Amazon 1",
                category="",
                source="Amazon",
                comment="",
                currency="JPY",
            ),
        ]
        datasource.add_transactions_batch(transactions)

        # Filter by Sony Bank
        sony_txs = datasource.get_transactions_by_source("Sony Bank")
        assert len(sony_txs) == 2

        # Filter by Amazon
        amazon_txs = datasource.get_transactions_by_source("Amazon")
        assert len(amazon_txs) == 1

    def test_date_range_query(self, datasource):
        """Test efficient date range querying."""
        # Add transactions across multiple days
        transactions = [
            Transaction(
                id="tx_25",
                date=datetime(2025, 10, 25, 10, 0, 0),
                amount=1000,
                description="Oct 25",
                category="",
                source="Test",
                comment="",
                currency="JPY",
            ),
            Transaction(
                id="tx_26_morning",
                date=datetime(2025, 10, 26, 9, 0, 0),
                amount=2000,
                description="Oct 26 Morning",
                category="",
                source="Test",
                comment="",
                currency="JPY",
            ),
            Transaction(
                id="tx_26_evening",
                date=datetime(2025, 10, 26, 18, 0, 0),
                amount=3000,
                description="Oct 26 Evening",
                category="",
                source="Test",
                comment="",
                currency="JPY",
            ),
            Transaction(
                id="tx_27",
                date=datetime(2025, 10, 27, 10, 0, 0),
                amount=4000,
                description="Oct 27",
                category="",
                source="Test",
                comment="",
                currency="JPY",
            ),
        ]
        datasource.add_transactions_batch(transactions)

        # Query Oct 26 only
        from_date = datetime(2025, 10, 26, 0, 0, 0)
        to_date = datetime(2025, 10, 26, 23, 59, 59)
        oct26_txs = datasource.get_transactions_by_date_range(from_date, to_date)
        assert len(oct26_txs) == 2

        # Query from Oct 26 onwards
        from_date = datetime(2025, 10, 26, 0, 0, 0)
        recent_txs = datasource.get_transactions_by_date_range(from_date=from_date)
        assert len(recent_txs) == 3


class TestProcessedIds:
    """Test getting processed transaction IDs."""

    def test_get_processed_ids(self, datasource):
        """Test getting all transaction IDs."""
        # Add transactions
        transactions = [
            Transaction(
                id=f"id_tx_{i}",
                date=datetime(2025, 10, 26, i, 0, 0),
                amount=1000,
                description="Test",
                category="",
                source="Test",
                comment="",
                currency="JPY",
            )
            for i in range(1, 4)
        ]
        datasource.add_transactions_batch(transactions)

        # Get IDs
        ids = datasource.get_processed_ids()
        assert isinstance(ids, set)
        assert len(ids) == 3
        assert "id_tx_1" in ids
        assert "id_tx_2" in ids
        assert "id_tx_3" in ids

    def test_get_processed_ids_empty(self, datasource):
        """Test getting IDs from empty datasource."""
        ids = datasource.get_processed_ids()
        assert isinstance(ids, set)
        assert len(ids) == 0


class TestProcessedMailIds:
    """Test getting processed mail IDs for deduplication."""

    def test_get_processed_mail_ids_empty(self, datasource):
        """Test getting mail IDs from empty datasource."""
        mail_ids = datasource.get_processed_mail_ids()
        assert isinstance(mail_ids, set)
        assert len(mail_ids) == 0

    def test_get_processed_mail_ids_all(self, datasource):
        """Test getting all mail IDs without source filter."""
        transactions = [
            Transaction(
                id="tx_1",
                date=datetime(2025, 10, 26, 10, 0, 0),
                amount=1000,
                description="Test 1",
                category="",
                source="Source A",
                comment="",
                currency="JPY",
                mail_id="mail_001",
            ),
            Transaction(
                id="tx_2",
                date=datetime(2025, 10, 26, 11, 0, 0),
                amount=2000,
                description="Test 2",
                category="",
                source="Source B",
                comment="",
                currency="JPY",
                mail_id="mail_002",
            ),
            Transaction(
                id="tx_3",
                date=datetime(2025, 10, 26, 12, 0, 0),
                amount=3000,
                description="Test 3",
                category="",
                source="Source A",
                comment="",
                currency="JPY",
                mail_id="mail_003",
            ),
        ]
        datasource.add_transactions_batch(transactions)

        mail_ids = datasource.get_processed_mail_ids()
        assert isinstance(mail_ids, set)
        assert len(mail_ids) == 3
        assert "mail_001" in mail_ids
        assert "mail_002" in mail_ids
        assert "mail_003" in mail_ids

    def test_get_processed_mail_ids_by_source(self, datasource):
        """Test getting mail IDs filtered by source."""
        transactions = [
            Transaction(
                id="tx_1",
                date=datetime(2025, 10, 26, 10, 0, 0),
                amount=1000,
                description="Test 1",
                category="",
                source="Source A",
                comment="",
                currency="JPY",
                mail_id="mail_001",
            ),
            Transaction(
                id="tx_2",
                date=datetime(2025, 10, 26, 11, 0, 0),
                amount=2000,
                description="Test 2",
                category="",
                source="Source B",
                comment="",
                currency="JPY",
                mail_id="mail_002",
            ),
            Transaction(
                id="tx_3",
                date=datetime(2025, 10, 26, 12, 0, 0),
                amount=3000,
                description="Test 3",
                category="",
                source="Source A",
                comment="",
                currency="JPY",
                mail_id="mail_003",
            ),
        ]
        datasource.add_transactions_batch(transactions)

        # Filter by Source A
        mail_ids_a = datasource.get_processed_mail_ids(source="Source A")
        assert len(mail_ids_a) == 2
        assert "mail_001" in mail_ids_a
        assert "mail_003" in mail_ids_a
        assert "mail_002" not in mail_ids_a

        # Filter by Source B
        mail_ids_b = datasource.get_processed_mail_ids(source="Source B")
        assert len(mail_ids_b) == 1
        assert "mail_002" in mail_ids_b

    def test_get_processed_mail_ids_excludes_null(self, datasource):
        """Test that transactions without mail_id are excluded."""
        transactions = [
            Transaction(
                id="tx_with_mail",
                date=datetime(2025, 10, 26, 10, 0, 0),
                amount=1000,
                description="With mail",
                category="",
                source="Test",
                comment="",
                currency="JPY",
                mail_id="mail_001",
            ),
            Transaction(
                id="tx_without_mail",
                date=datetime(2025, 10, 26, 11, 0, 0),
                amount=2000,
                description="Without mail",
                category="",
                source="Test",
                comment="",
                currency="JPY",
                mail_id=None,
            ),
        ]
        datasource.add_transactions_batch(transactions)

        mail_ids = datasource.get_processed_mail_ids()
        assert len(mail_ids) == 1
        assert "mail_001" in mail_ids
        assert None not in mail_ids

    def test_get_processed_mail_ids_global_finds_cross_source_duplicates(self, datasource):
        """Test that global query finds mail_id even if processed by different source.

        This is critical for deduplication: if email X was processed by fetcher "Wise",
        a different fetcher "Wise (with conversion)" should still see it as processed
        when using global query (no source filter).
        """
        # Same email processed by "Wise" fetcher
        tx_original = Transaction(
            id="tx_original",
            date=datetime(2025, 10, 26, 10, 0, 0),
            amount=1000,
            description="Google Cloud",
            category="",
            source="Wise",
            comment="",
            currency="JPY",
            mail_id="shared_mail_id_123",
        )
        datasource.add_transaction(tx_original)

        # Global query should find it (for any fetcher)
        all_mail_ids = datasource.get_processed_mail_ids()
        assert "shared_mail_id_123" in all_mail_ids

        # Source-specific query for "Wise" should find it
        wise_mail_ids = datasource.get_processed_mail_ids(source="Wise")
        assert "shared_mail_id_123" in wise_mail_ids

        # Source-specific query for different fetcher should NOT find it
        other_mail_ids = datasource.get_processed_mail_ids(source="Wise (with conversion)")
        assert "shared_mail_id_123" not in other_mail_ids

        # This demonstrates why global deduplication is necessary:
        # If we only check source-specific mail_ids, a renamed/different fetcher
        # would re-process the same email, creating duplicates


class TestUpdatedAtField:
    """Test updated_at field behavior."""

    def test_new_transaction_updated_at_equals_date(self, datasource):
        """Test that new transactions have updated_at set to transaction date."""
        tx_date = datetime(2025, 10, 26, 14, 32, 45)
        tx = Transaction(
            id="test_updated_at",
            date=tx_date,
            amount=1000,
            description="Test",
            category="",
            source="Test",
            comment="",
            currency="JPY",
        )

        datasource.add_transaction(tx)

        # Retrieve and verify updated_at equals date
        retrieved = datasource.get_all_transactions()[0]
        assert retrieved.updated_at is not None
        assert retrieved.updated_at == datetime(2025, 10, 26, 14, 32, 45, tzinfo=timezone.utc)
        assert retrieved.updated_at.replace(tzinfo=None) == tx_date

    def test_batch_transactions_updated_at_equals_date(self, datasource):
        """Test that batch transactions have updated_at set to transaction date."""
        transactions = [
            Transaction(
                id=f"batch_updated_at_{i}",
                date=datetime(2025, 10, i, 10, 0, 0),
                amount=1000 * i,
                description=f"Batch {i}",
                category="",
                source="Test",
                comment="",
                currency="JPY",
            )
            for i in range(1, 4)
        ]

        datasource.add_transactions_batch(transactions)

        # Verify all have updated_at equal to their date
        all_txs = datasource.get_all_transactions()
        for tx in all_txs:
            assert tx.updated_at is not None
            assert tx.updated_at.replace(tzinfo=None) == tx.date.replace(tzinfo=None)

    def test_update_transaction_changes_updated_at(self, datasource):
        """Test that updating a transaction updates the updated_at field."""
        # Add initial transaction
        tx_date = datetime(2025, 10, 26, 10, 0, 0)
        tx = Transaction(
            id="test_update_updated_at",
            date=tx_date,
            amount=1000,
            description="Original",
            category="",
            source="Test",
            comment="",
            currency="JPY",
        )
        datasource.add_transaction(tx)

        # Get initial updated_at (= tx_date, a fixed past date)
        retrieved = datasource.get_all_transactions()[0]
        initial_updated_at = retrieved.updated_at

        # Update the transaction
        datasource.update_transaction(
            tx_id="test_update_updated_at",
            date=tx_date,
            amount=2000,
            description="Updated",
            comment="New comment",
        )

        # Verify updated_at changed
        updated = datasource.get_all_transactions()[0]
        assert updated.updated_at is not None
        assert updated.updated_at > initial_updated_at
        # updated_at should be different from date
        assert updated.updated_at.replace(tzinfo=None) != tx_date

    def test_add_group_updates_updated_at(self, datasource):
        """Test that adding a group updates the updated_at field."""
        # Add initial transaction
        tx = Transaction(
            id="test_group_updated_at",
            date=datetime(2025, 10, 26, 10, 0, 0),
            amount=1000,
            description="Test",
            category="",
            source="Test",
            comment="",
            currency="JPY",
        )
        datasource.add_transaction(tx)

        # Get initial updated_at (= tx date, a fixed past date)
        retrieved = datasource.get_all_transactions()[0]
        initial_updated_at = retrieved.updated_at

        # Add group
        datasource.add_group_to_transaction("test_group_updated_at", "group1")

        # Verify updated_at changed
        updated = datasource.get_all_transactions()[0]
        assert updated.updated_at is not None
        assert updated.updated_at > initial_updated_at

    def test_remove_group_updates_updated_at(self, datasource):
        """Test that removing a group updates the updated_at field."""
        # Add initial transaction with a group
        tx = Transaction(
            id="test_remove_group_updated_at",
            date=datetime(2025, 10, 26, 10, 0, 0),
            amount=1000,
            description="Test",
            category="",
            source="Test",
            comment="",
            groups=["group1"],
            currency="JPY",
        )
        datasource.add_transaction(tx)

        # Get initial updated_at (= tx date, a fixed past date)
        retrieved = datasource.get_all_transactions()[0]
        initial_updated_at = retrieved.updated_at

        # Remove group
        datasource.remove_group_from_transaction("test_remove_group_updated_at", "group1")

        # Verify updated_at changed
        updated = datasource.get_all_transactions()[0]
        assert updated.updated_at is not None
        assert updated.updated_at > initial_updated_at


class TestCreatedAtField:
    """Test created_at field behavior."""

    def test_new_transaction_has_created_at(self, datasource):
        """Test that new transactions have created_at set to current time."""
        import time

        # Get current time before adding transaction (truncate microseconds for SQLite comparison)
        before_time = datetime.now(timezone.utc).replace(microsecond=0)
        time.sleep(0.01)  # Small delay to ensure time difference

        tx_date = datetime(2025, 10, 26, 14, 32, 45)
        tx = Transaction(
            id="test_created_at",
            date=tx_date,
            amount=1000,
            description="Test",
            category="",
            source="Test",
            comment="",
            currency="JPY",
            created_at=datetime.now(timezone.utc),
        )

        datasource.add_transaction(tx)

        time.sleep(0.01)  # Small delay
        after_time = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(seconds=1)

        # Retrieve and verify created_at is set and within expected range
        retrieved = datasource.get_all_transactions()[0]
        assert retrieved.created_at is not None
        assert before_time <= retrieved.created_at <= after_time
        # created_at should NOT equal transaction date
        assert retrieved.created_at.replace(tzinfo=None) != tx_date

    def test_batch_transactions_have_created_at(self, datasource):
        """Test that batch transactions have created_at set."""
        import time

        before_time = datetime.now(timezone.utc).replace(microsecond=0)
        time.sleep(0.01)

        current_created_at = datetime.now(timezone.utc)
        transactions = [
            Transaction(
                id=f"batch_created_at_{i}",
                date=datetime(2025, 10, i, 10, 0, 0),
                amount=1000 * i,
                description=f"Batch {i}",
                category="",
                source="Test",
                comment="",
                currency="JPY",
                created_at=current_created_at,
            )
            for i in range(1, 4)
        ]

        datasource.add_transactions_batch(transactions)

        time.sleep(0.01)
        after_time = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(seconds=1)

        # Verify all have created_at set
        all_txs = datasource.get_all_transactions()
        for tx in all_txs:
            assert tx.created_at is not None
            assert before_time <= tx.created_at <= after_time

    def test_update_transaction_does_not_change_created_at(self, datasource):
        """Test that updating a transaction does NOT change created_at (immutability)."""
        # Add initial transaction
        # Use a past timestamp so updated_at (set to now()) is guaranteed to be greater
        # without needing to sleep for SQLite's second-precision clock.
        tx_date = datetime(2025, 10, 26, 10, 0, 0)
        created_time = datetime.now(timezone.utc) - timedelta(seconds=2)
        tx = Transaction(
            id="test_immutable_created_at",
            date=tx_date,
            amount=1000,
            description="Original",
            category="",
            source="Test",
            comment="",
            currency="JPY",
            created_at=created_time,
        )
        datasource.add_transaction(tx)

        # Get initial created_at
        retrieved = datasource.get_all_transactions()[0]
        initial_created_at = retrieved.created_at

        # Update the transaction
        datasource.update_transaction(
            tx_id="test_immutable_created_at",
            date=tx_date,
            amount=2000,
            description="Updated",
            comment="New comment",
        )

        # Verify created_at did NOT change (immutability)
        updated = datasource.get_all_transactions()[0]
        assert updated.created_at is not None
        assert updated.created_at == initial_created_at
        # But updated_at should have changed (should be later)
        assert updated.updated_at > initial_created_at

    def test_add_group_does_not_change_created_at(self, datasource):
        """Test that adding a group does NOT change created_at (immutability)."""
        # Add initial transaction
        # Use a past timestamp so updated_at (set to now()) is guaranteed to be greater
        # without needing to sleep for SQLite's second-precision clock.
        created_time = datetime.now(timezone.utc) - timedelta(seconds=2)
        tx = Transaction(
            id="test_group_immutable_created_at",
            date=datetime(2025, 10, 26, 10, 0, 0),
            amount=1000,
            description="Test",
            category="",
            source="Test",
            comment="",
            currency="JPY",
            created_at=created_time,
        )
        datasource.add_transaction(tx)

        # Get initial created_at
        retrieved = datasource.get_all_transactions()[0]
        initial_created_at = retrieved.created_at

        # Add group
        datasource.add_group_to_transaction("test_group_immutable_created_at", "group1")

        # Verify created_at did NOT change (immutability)
        updated = datasource.get_all_transactions()[0]
        assert updated.created_at is not None
        assert updated.created_at == initial_created_at
        # But updated_at should have changed (should be later)
        assert updated.updated_at > initial_created_at


def _generate_test_key() -> str:
    """Generate a base64-encoded 256-bit key for testing."""
    return base64.b64encode(os.urandom(32)).decode("ascii")


class TestEncryptedTransactions:
    """Test field encryption at rest for transactions."""

    def test_add_and_retrieve_encrypted(self, temp_db):
        """Test roundtrip: add encrypted transaction and retrieve decrypted."""
        key = _generate_test_key()
        ds = SQLiteTransactionDataSource(temp_db, user_id="test_user", encryption_key=key)

        tx = Transaction(
            id="enc_tx_1",
            date=datetime(2025, 11, 1, 10, 0, 0),
            amount=4200,
            description="Encrypted Coffee",
            category="",
            source="Test",
            comment="secret note",
            currency="JPY",
        )
        ds.add_transaction(tx)

        retrieved = ds.get_all_transactions()[0]
        assert retrieved.description == "Encrypted Coffee"
        assert retrieved.amount == 4200
        assert retrieved.comment == "secret note"

    def test_encrypted_data_unreadable_without_key(self, temp_db):
        """Write encrypted, read without key — should get placeholders."""
        key = _generate_test_key()
        ds_enc = SQLiteTransactionDataSource(temp_db, user_id="test_user", encryption_key=key)

        tx = Transaction(
            id="enc_tx_2",
            date=datetime(2025, 11, 1, 10, 0, 0),
            amount=9999,
            description="Top Secret Purchase",
            category="",
            source="Test",
            comment="hidden",
            currency="JPY",
        )
        ds_enc.add_transaction(tx)

        # Read without encryption key — amount stays readable, text fields get placeholders
        ds_plain = SQLiteTransactionDataSource(temp_db, user_id="test_user")
        retrieved = ds_plain.get_all_transactions()[0]
        assert retrieved.description == ENCRYPTED_PLACEHOLDER
        assert retrieved.amount == 9999  # amount is never encrypted
        assert retrieved.comment == ""

    def test_batch_encrypted(self, temp_db):
        """Batch insert with encryption key, verify all decrypt correctly."""
        key = _generate_test_key()
        ds = SQLiteTransactionDataSource(temp_db, user_id="test_user", encryption_key=key)

        transactions = [
            Transaction(
                id=f"batch_enc_{i}",
                date=datetime(2025, 11, i, 10, 0, 0),
                amount=1000 * i,
                description=f"Batch Encrypted {i}",
                category="",
                source="Test",
                comment=f"note {i}",
                currency="JPY",
            )
            for i in range(1, 4)
        ]
        ds.add_transactions_batch(transactions)

        retrieved = ds.get_all_transactions()
        assert len(retrieved) == 3
        for tx in retrieved:
            i = int(tx.id.split("_")[-1])
            assert tx.amount == 1000 * i
            assert tx.description == f"Batch Encrypted {i}"
            assert tx.comment == f"note {i}"

    def test_update_encrypted(self, temp_db):
        """Update an encrypted transaction, verify updated values decrypt."""
        key = _generate_test_key()
        ds = SQLiteTransactionDataSource(temp_db, user_id="test_user", encryption_key=key)

        tx = Transaction(
            id="enc_update_1",
            date=datetime(2025, 11, 1, 10, 0, 0),
            amount=500,
            description="Original Encrypted",
            category="",
            source="Test",
            comment="old note",
            currency="JPY",
        )
        ds.add_transaction(tx)

        ds.update_transaction(
            tx_id="enc_update_1",
            date=datetime(2025, 11, 1, 10, 0, 0),
            amount=750,
            description="Updated Encrypted",
            comment="new note",
        )

        retrieved = ds.get_all_transactions()[0]
        assert retrieved.amount == 750
        assert retrieved.description == "Updated Encrypted"
        assert retrieved.comment == "new note"

    def test_mixed_plaintext_and_encrypted(self, temp_db):
        """Read DB with both plaintext (version 0) and encrypted (version 1) rows."""
        # Write plaintext first (no key)
        ds_plain = SQLiteTransactionDataSource(temp_db, user_id="test_user")
        tx_plain = Transaction(
            id="plain_1",
            date=datetime(2025, 11, 1, 10, 0, 0),
            amount=100,
            description="Plaintext Purchase",
            category="",
            source="Test",
            comment="visible",
            currency="JPY",
        )
        ds_plain.add_transaction(tx_plain)

        # Write encrypted (with key)
        key = _generate_test_key()
        ds_enc = SQLiteTransactionDataSource(temp_db, user_id="test_user", encryption_key=key)
        tx_enc = Transaction(
            id="enc_1",
            date=datetime(2025, 11, 2, 10, 0, 0),
            amount=200,
            description="Encrypted Purchase",
            category="",
            source="Test",
            comment="secret",
            currency="JPY",
        )
        ds_enc.add_transaction(tx_enc)

        # Read both with key — should decrypt encrypted, pass through plaintext
        all_txs = ds_enc.get_all_transactions()
        assert len(all_txs) == 2
        tx_map = {tx.id: tx for tx in all_txs}

        assert tx_map["plain_1"].description == "Plaintext Purchase"
        assert tx_map["plain_1"].amount == 100
        assert tx_map["enc_1"].description == "Encrypted Purchase"
        assert tx_map["enc_1"].amount == 200

    def test_encryption_version_column_value(self, temp_db):
        """Verify encryption_version column via raw SQL."""
        key = _generate_test_key()
        ds = SQLiteTransactionDataSource(temp_db, user_id="test_user", encryption_key=key)

        tx = Transaction(
            id="ver_check",
            date=datetime(2025, 11, 1, 10, 0, 0),
            amount=100,
            description="Version Check",
            category="",
            source="Test",
            comment="",
            currency="JPY",
        )
        ds.add_transaction(tx)

        # Check raw value
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT encryption_version, description, amount FROM transactions WHERE id = 'ver_check'"
        )
        row = cursor.fetchone()
        conn.close()

        assert row[0] == 1  # encryption_version = 1
        assert row[1] != "Version Check"  # description should be ciphertext
        assert row[2] == 100  # amount is never encrypted, stays as integer

    def test_no_key_plaintext_unchanged(self, temp_db):
        """No encryption key = plaintext mode, proving backward compatibility."""
        ds = SQLiteTransactionDataSource(temp_db, user_id="test_user")

        tx = Transaction(
            id="plain_compat",
            date=datetime(2025, 11, 1, 10, 0, 0),
            amount=300,
            description="Backward Compatible",
            category="",
            source="Test",
            comment="plain comment",
            currency="JPY",
        )
        ds.add_transaction(tx)

        # Raw SQL should show plaintext
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT encryption_version, description, amount, comment FROM transactions WHERE id = 'plain_compat'"
        )
        row = cursor.fetchone()
        conn.close()

        assert row[0] == 0  # encryption_version = 0
        assert row[1] == "Backward Compatible"
        assert row[2] == 300
        assert row[3] == "plain comment"

        # Normal retrieval
        retrieved = ds.get_all_transactions()[0]
        assert retrieved.description == "Backward Compatible"
        assert retrieved.amount == 300

    def test_encrypted_by_source_query(self, temp_db):
        """Verify get_transactions_by_source works with encrypted data."""
        key = _generate_test_key()
        ds = SQLiteTransactionDataSource(temp_db, user_id="test_user", encryption_key=key)

        tx = Transaction(
            id="src_enc_1",
            date=datetime(2025, 11, 1, 10, 0, 0),
            amount=555,
            description="Source Query Test",
            category="",
            source="Sony Bank",
            comment="",
            currency="JPY",
        )
        ds.add_transaction(tx)

        results = ds.get_transactions_by_source("Sony Bank")
        assert len(results) == 1
        assert results[0].description == "Source Query Test"
        assert results[0].amount == 555

    def test_encrypted_by_date_range_query(self, temp_db):
        """Verify get_transactions_by_date_range works with encrypted data."""
        key = _generate_test_key()
        ds = SQLiteTransactionDataSource(temp_db, user_id="test_user", encryption_key=key)

        tx = Transaction(
            id="date_enc_1",
            date=datetime(2025, 11, 15, 10, 0, 0),
            amount=777,
            description="Date Range Test",
            category="",
            source="Test",
            comment="",
            currency="JPY",
        )
        ds.add_transaction(tx)

        results = ds.get_transactions_by_date_range(
            from_date=datetime(2025, 11, 1), to_date=datetime(2025, 11, 30)
        )
        assert len(results) == 1
        assert results[0].description == "Date Range Test"
        assert results[0].amount == 777

    def test_encrypted_by_group_query(self, temp_db):
        """Verify get_transactions_by_group works with encrypted data."""
        key = _generate_test_key()
        ds = SQLiteTransactionDataSource(temp_db, user_id="test_user", encryption_key=key)

        tx = Transaction(
            id="grp_enc_1",
            date=datetime(2025, 11, 1, 10, 0, 0),
            amount=888,
            description="Group Query Test",
            category="",
            source="Test",
            comment="",
            currency="JPY",
            groups=["group_abc"],
        )
        ds.add_transaction(tx)

        results = ds.get_transactions_by_group("group_abc")
        assert len(results) == 1
        assert results[0].description == "Group Query Test"
        assert results[0].amount == 888

    def test_wrong_key_returns_placeholders(self, temp_db):
        """Decrypt with wrong key should return placeholders, not crash."""
        key1 = _generate_test_key()
        ds1 = SQLiteTransactionDataSource(temp_db, user_id="test_user", encryption_key=key1)

        tx = Transaction(
            id="wrong_key_1",
            date=datetime(2025, 11, 1, 10, 0, 0),
            amount=1234,
            description="Secret Data",
            category="",
            source="Test",
            comment="private",
            currency="JPY",
        )
        ds1.add_transaction(tx)

        # Read with a different key — decryption should fail gracefully
        key2 = _generate_test_key()
        ds2 = SQLiteTransactionDataSource(temp_db, user_id="test_user", encryption_key=key2)
        retrieved = ds2.get_all_transactions()[0]
        assert retrieved.description == ENCRYPTED_PLACEHOLDER
        assert retrieved.amount == 1234  # amount is never encrypted
        assert retrieved.comment == ""


class TestMigrateEncryption:
    """Test bulk encrypt/decrypt migration methods."""

    def test_migrate_to_encrypted(self, temp_db):
        """Migrate plaintext rows to encrypted."""
        key = _generate_test_key()

        # Insert plaintext rows (no key)
        ds_plain = SQLiteTransactionDataSource(temp_db, user_id="test_user")
        for i in range(3):
            ds_plain.add_transaction(
                Transaction(
                    id=f"mig_enc_{i}",
                    date=datetime(2025, 1, 1 + i),
                    amount=100 * i,
                    description=f"Plain {i}",
                    category="",
                    source="Test",
                    comment=f"note {i}",
                    currency="JPY",
                )
            )

        # Migrate with key
        ds_enc = SQLiteTransactionDataSource(temp_db, user_id="test_user", encryption_key=key)
        count = ds_enc.migrate_to_encrypted()
        assert count == 3

        # Read back with key — should get original text
        results = ds_enc.get_all_transactions()
        descriptions = sorted(t.description for t in results)
        assert descriptions == ["Plain 0", "Plain 1", "Plain 2"]

        # Read without key — should get placeholders
        ds_no_key = SQLiteTransactionDataSource(temp_db, user_id="test_user")
        results_no_key = ds_no_key.get_all_transactions()
        assert all(t.description == ENCRYPTED_PLACEHOLDER for t in results_no_key)

    def test_migrate_already_encrypted_noop(self, temp_db):
        """Migrating already-encrypted rows should return 0."""
        key = _generate_test_key()

        # Insert encrypted rows
        ds = SQLiteTransactionDataSource(temp_db, user_id="test_user", encryption_key=key)
        ds.add_transaction(
            Transaction(
                id="already_enc",
                date=datetime(2025, 1, 1),
                amount=500,
                description="Already encrypted",
                category="",
                source="Test",
                currency="JPY",
            )
        )

        count = ds.migrate_to_encrypted()
        assert count == 0

    def test_migrate_to_plaintext(self, temp_db):
        """Migrate encrypted rows back to plaintext."""
        key = _generate_test_key()

        # Insert encrypted rows
        ds_enc = SQLiteTransactionDataSource(temp_db, user_id="test_user", encryption_key=key)
        for i in range(2):
            ds_enc.add_transaction(
                Transaction(
                    id=f"mig_dec_{i}",
                    date=datetime(2025, 2, 1 + i),
                    amount=200 * i,
                    description=f"Secret {i}",
                    category="",
                    source="Test",
                    comment=f"hidden {i}",
                    currency="JPY",
                )
            )

        # Decrypt back to plaintext
        count = ds_enc.migrate_to_plaintext()
        assert count == 2

        # Read without key — should be plaintext
        ds_plain = SQLiteTransactionDataSource(temp_db, user_id="test_user")
        results = ds_plain.get_all_transactions()
        descriptions = sorted(t.description for t in results)
        assert descriptions == ["Secret 0", "Secret 1"]

    def test_migrate_to_plaintext_already_plain_noop(self, temp_db):
        """Decrypting plaintext rows should return 0."""
        key = _generate_test_key()

        ds_plain = SQLiteTransactionDataSource(temp_db, user_id="test_user")
        ds_plain.add_transaction(
            Transaction(
                id="already_plain",
                date=datetime(2025, 1, 1),
                amount=100,
                description="Plaintext",
                category="",
                source="Test",
                currency="JPY",
            )
        )

        ds_enc = SQLiteTransactionDataSource(temp_db, user_id="test_user", encryption_key=key)
        count = ds_enc.migrate_to_plaintext()
        assert count == 0

    def test_migrate_no_key_returns_zero(self, temp_db):
        """Calling migrate without encryption key should return 0."""
        ds = SQLiteTransactionDataSource(temp_db, user_id="test_user")
        ds.add_transaction(
            Transaction(
                id="no_key_mig",
                date=datetime(2025, 1, 1),
                amount=100,
                description="Test",
                category="",
                source="Test",
                currency="JPY",
            )
        )
        assert ds.migrate_to_encrypted() == 0
        assert ds.migrate_to_plaintext() == 0

"""
Tests for SQLiteManualAssignmentDataSource.

Tests cover:
- Basic CRUD operations (add, get, remove)
- Batch operations
- Getting assigned transaction IDs
- SQLite-specific features (get by category, clear all)
"""

import os
import tempfile

import pytest

from infrastructure.persistence.sqlite.repositories.manual_assignment_repository import (
    SQLiteManualAssignmentDataSource,
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
    """Create a SQLiteManualAssignmentDataSource instance."""
    return SQLiteManualAssignmentDataSource(temp_db, user_id="test_user")


class TestBasicOperations:
    """Test basic CRUD operations."""

    def test_starts_empty(self, datasource):
        """Test that new datasource starts empty."""
        assert datasource.count_assignments() == 0

    def test_add_assignment(self, datasource):
        """Test adding a single assignment."""
        datasource.add_assignment("tx_1", "food")
        assert datasource.count_assignments() == 1
        assert datasource.get_assignment("tx_1") == "food"
        assert datasource.has_assignment("tx_1")

    def test_get_all_assignments(self, datasource):
        """Test getting all assignments."""
        datasource.add_assignment("tx_1", "food")
        assignments = datasource.get_assignments()
        assert len(assignments) == 1
        assert assignments["tx_1"] == "food"

    def test_update_assignment(self, datasource):
        """Test updating an existing assignment."""
        datasource.add_assignment("tx_1", "food")
        datasource.add_assignment("tx_1", "transport")
        assert datasource.get_assignment("tx_1") == "transport"

    def test_remove_assignment(self, datasource):
        """Test removing an assignment."""
        datasource.add_assignment("tx_1", "food")
        removed = datasource.remove_assignment("tx_1")
        assert removed is True
        assert datasource.count_assignments() == 0

    def test_remove_nonexistent(self, datasource):
        """Test removing a non-existent assignment returns False."""
        removed = datasource.remove_assignment("tx_nonexistent")
        assert removed is False


class TestBatchOperations:
    """Test batch operations."""

    def test_batch_add(self, datasource):
        """Test adding multiple assignments in batch."""
        assignments = {
            "tx_1": "food",
            "tx_2": "transport",
            "tx_3": "entertainment",
            "tx_4": "shopping",
            "tx_5": "food",
        }
        count = datasource.add_assignments_batch(assignments)
        assert count == 5
        assert datasource.count_assignments() == 5

    def test_batch_add_verifies_all(self, datasource):
        """Test that all batch-added assignments are retrievable."""
        assignments = {"tx_1": "food", "tx_2": "transport", "tx_3": "entertainment"}
        datasource.add_assignments_batch(assignments)
        assert datasource.get_assignment("tx_1") == "food"
        assert datasource.get_assignment("tx_3") == "entertainment"

    def test_batch_update(self, datasource):
        """Test batch update (overlapping assignments)."""
        # Add initial assignments
        datasource.add_assignments_batch({"tx_1": "food", "tx_2": "transport"})

        # Batch update with overlapping and new
        new_assignments = {"tx_1": "groceries", "tx_6": "utilities"}  # Update  # New
        count = datasource.add_assignments_batch(new_assignments)
        assert count == 2
        assert datasource.count_assignments() == 3
        assert datasource.get_assignment("tx_1") == "groceries"


class TestGetAssignedIds:
    """Test getting assigned transaction IDs."""

    def test_get_assigned_tx_ids(self, datasource):
        """Test getting all assigned transaction IDs."""
        datasource.add_assignments_batch({"tx_1": "food", "tx_2": "transport", "tx_3": "food"})

        tx_ids = datasource.get_assigned_tx_ids()
        assert isinstance(tx_ids, set)
        assert len(tx_ids) == 3
        assert "tx_1" in tx_ids
        assert "tx_2" in tx_ids
        assert "tx_3" in tx_ids

    def test_get_assigned_tx_ids_empty(self, datasource):
        """Test getting IDs from empty datasource."""
        tx_ids = datasource.get_assigned_tx_ids()
        assert isinstance(tx_ids, set)
        assert len(tx_ids) == 0


class TestSQLiteSpecificFeatures:
    """Test SQLite-specific features."""

    def test_get_by_category(self, datasource):
        """Test getting assignments by category."""
        datasource.add_assignments_batch(
            {"tx_1": "food", "tx_2": "food", "tx_3": "transport", "tx_4": "food"}
        )

        food_assignments = datasource.get_assignments_by_category("food")
        assert len(food_assignments) == 3
        assert "tx_1" in food_assignments
        assert "tx_2" in food_assignments
        assert "tx_4" in food_assignments
        assert food_assignments["tx_1"] == "food"

    def test_get_by_category_empty(self, datasource):
        """Test getting assignments for non-existent category."""
        datasource.add_assignment("tx_1", "food")
        results = datasource.get_assignments_by_category("nonexistent")
        assert len(results) == 0

    def test_clear_all(self, datasource):
        """Test clearing all assignments."""
        datasource.add_assignments_batch(
            {"tx_1": "food", "tx_2": "food", "tx_3": "transport", "tx_4": "food"}
        )

        cleared = datasource.clear_all_assignments()
        assert cleared == 4
        assert datasource.count_assignments() == 0

    def test_clear_all_empty(self, datasource):
        """Test clearing empty datasource."""
        cleared = datasource.clear_all_assignments()
        assert cleared == 0

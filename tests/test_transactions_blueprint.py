"""Tests for the transactions blueprint routes."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from domain.entities.transaction import CategorySource, Transaction


@pytest.fixture
def mock_services():
    """Set up mock services for the transactions blueprint."""
    mock_category_service = MagicMock()
    mock_category_service.get_categories_hierarchical.return_value = []
    mock_category_service.categories = {}
    mock_category_service.get_categories_as_dict_list.return_value = []

    mock_user_settings = MagicMock(currency="JPY", language="en", browser_settings={})
    mock_user_settings_service = MagicMock()
    mock_user_settings_service.get_user_settings.return_value = mock_user_settings
    mock_user_settings_service.get_currency_symbol.return_value = "\u00a5"
    mock_user_settings_service.get_currency_converter.return_value = MagicMock(
        convert=lambda a, f, t, d=None: a
    )
    mock_user_settings_service.get_supported_currencies.return_value = [
        {"code": "JPY", "symbol": "¥", "name": "Japanese Yen", "minor_units": 0},
        {"code": "USD", "symbol": "$", "name": "US Dollar", "minor_units": 2},
        {"code": "EUR", "symbol": "€", "name": "Euro", "minor_units": 2},
    ]
    mock_user_settings_service.get_default_currency.return_value = "JPY"
    mock_user_settings_service.validate_currency.side_effect = lambda c: c in ["JPY", "USD", "EUR"]

    mock_tx_service = MagicMock()
    mock_tx_service.get_all_transactions.return_value = []
    mock_tx_service.get_all_transactions_filtered.return_value = []
    mock_tx_service.get_transactions_by_group.return_value = []
    mock_tx_service.get_transaction_sources.return_value = []

    mock_classification_service = MagicMock()
    mock_classification_service.classify_transactions.return_value = {}

    mock_group_service = MagicMock()
    mock_group_service.get_all_groups.return_value = []

    patches = {
        "cat": patch(
            "presentation.web.blueprints.transactions.get_category_service",
            return_value=mock_category_service,
        ),
        "settings": patch(
            "presentation.web.blueprints.transactions.get_user_settings_service",
            return_value=mock_user_settings_service,
        ),
        "tx": patch(
            "presentation.web.blueprints.transactions.get_transaction_service",
            return_value=mock_tx_service,
        ),
        "classify": patch(
            "presentation.web.blueprints.transactions.get_classification_service",
            return_value=mock_classification_service,
        ),
        "groups": patch(
            "presentation.web.blueprints.transactions.get_group_service",
            return_value=mock_group_service,
        ),
        "invalidate": patch(
            "presentation.web.blueprints.transactions.invalidate_service_cache",
        ),
    }

    started = {}
    for key, p in patches.items():
        started[key] = p.start()

    yield {
        "category_service": mock_category_service,
        "user_settings_service": mock_user_settings_service,
        "tx_service": mock_tx_service,
        "classification_service": mock_classification_service,
        "group_service": mock_group_service,
        "patches": started,
    }

    for p in patches.values():
        p.stop()


class TestTransactionsBlueprint:
    """Tests for the transactions blueprint routes."""

    def test_review_page_loads(self, authenticated_client, mock_services):
        """GET /review should return 200."""
        response = authenticated_client.get("/review")
        assert response.status_code == 200

    def test_update_transaction_missing_id(self, authenticated_client, mock_services):
        """POST /update-transaction with empty tx_id should return 400."""
        response = authenticated_client.post(
            "/update-transaction",
            json={
                "tx_id": "",
                "date": "2025-01-01",
                "amount": "1000",
                "description": "Test",
                "comment": "",
                "currency": "JPY",
            },
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False
        assert "Transaction ID" in data["error"]

    def test_update_transaction_invalid_currency(self, authenticated_client, mock_services):
        """POST /update-transaction with unsupported currency should return 400."""
        response = authenticated_client.post(
            "/update-transaction",
            json={
                "tx_id": "tx1",
                "date": "2025-01-01",
                "amount": "1000",
                "description": "Test",
                "comment": "",
                "currency": "INVALID",
            },
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False
        assert "Unsupported currency" in data["error"]

    def test_add_transaction_missing_fields(self, authenticated_client, mock_services):
        """POST /add-transaction with missing required fields should return 400."""
        response = authenticated_client.post(
            "/add-transaction",
            json={
                "date": "",
                "amount": "",
                "description": "",
                "category": "",
                "comment": "",
                "currency": "JPY",
            },
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False
        assert "required" in data["error"].lower()

    def test_add_transaction_invalid_currency(self, authenticated_client, mock_services):
        """POST /add-transaction with unsupported currency should return 400."""
        response = authenticated_client.post(
            "/add-transaction",
            json={
                "date": "2025-01-01",
                "amount": "1000",
                "description": "Lunch",
                "category": "",
                "comment": "",
                "currency": "XYZ",
            },
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False
        assert "Unsupported currency" in data["error"]

    def test_assign_similarity_no_changes(self, authenticated_client, mock_services):
        """POST /assign-similarity with no changed categories should redirect with flash."""
        tx = Transaction(
            id="tx1",
            date=datetime(2025, 1, 15, tzinfo=timezone.utc),
            amount=1000,
            description="Coffee",
            category="food",
            source="Manual",
            currency="JPY",
            category_source=CategorySource.MANUAL,
        )
        mock_services["tx_service"].get_all_transactions.return_value = [tx]

        response = authenticated_client.post(
            "/assign-similarity",
            data={"category_tx1": "food"},
            follow_redirects=False,
        )
        # Should redirect (302) back to review
        assert response.status_code == 302

    def test_assign_similarity_with_changes(self, authenticated_client, mock_services):
        """POST /assign-similarity with a changed category should assign and redirect."""
        tx = Transaction(
            id="tx1",
            date=datetime(2025, 1, 15, tzinfo=timezone.utc),
            amount=1000,
            description="Coffee",
            category="food",
            source="Manual",
            currency="JPY",
            category_source=CategorySource.SIMILARITY,
        )
        mock_services["tx_service"].get_all_transactions.return_value = [tx]

        response = authenticated_client.post(
            "/assign-similarity",
            data={"category_tx1": "beverage"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        mock_services["tx_service"].assign_categories_bulk.assert_called_once_with(
            {"tx1": "beverage"}
        )

    def test_assign_similarity_redirect_to_groups(self, authenticated_client, mock_services):
        """POST /assign-similarity with redirect_to=groups should redirect to groups page."""
        tx = Transaction(
            id="tx1",
            date=datetime(2025, 1, 15, tzinfo=timezone.utc),
            amount=1000,
            description="Coffee",
            category="food",
            source="Manual",
            currency="JPY",
            category_source=CategorySource.SIMILARITY,
        )
        mock_services["tx_service"].get_all_transactions.return_value = [tx]

        response = authenticated_client.post(
            "/assign-similarity",
            data={"category_tx1": "new_cat", "redirect_to": "groups"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/groups" in response.headers["Location"]

    def test_manual_transaction_autocomplete_empty(self, authenticated_client, mock_services):
        """GET /api/manual-transaction-autocomplete with no manual txs should return empty."""
        mock_services["tx_service"].get_all_transactions.return_value = []
        mock_services["tx_service"].get_transactions_by_source.return_value = []

        response = authenticated_client.get("/api/manual-transaction-autocomplete")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["suggestions"] == []

    def test_manual_transaction_autocomplete_with_data(self, authenticated_client, mock_services):
        """GET /api/manual-transaction-autocomplete should group by description."""
        tx1 = Transaction(
            id="tx1",
            date=datetime(2025, 1, 15, tzinfo=timezone.utc),
            amount=500,
            description="Coffee",
            category="food",
            source="Manual",
            currency="JPY",
            category_source=CategorySource.MANUAL,
        )
        tx2 = Transaction(
            id="tx2",
            date=datetime(2025, 1, 16, tzinfo=timezone.utc),
            amount=600,
            description="Coffee",
            category="food",
            source="Manual",
            currency="JPY",
            category_source=CategorySource.MANUAL,
        )
        mock_services["tx_service"].get_all_transactions.return_value = [tx1, tx2]
        mock_services["tx_service"].get_transactions_by_source.return_value = [tx1, tx2]
        mock_services["category_service"].categories = {}

        response = authenticated_client.get("/api/manual-transaction-autocomplete")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert len(data["suggestions"]) == 1
        assert data["suggestions"][0]["description"] == "Coffee"

    def test_update_transaction_success(self, authenticated_client, mock_services):
        """POST /update-transaction with valid data should return success."""
        mock_services["tx_service"].update_transaction.return_value = (True, "")
        response = authenticated_client.post(
            "/update-transaction",
            json={
                "tx_id": "tx1",
                "date": "2025-01-01",
                "amount": "1000",
                "description": "Updated",
                "comment": "",
                "currency": "JPY",
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

    def test_add_transaction_success(self, authenticated_client, mock_services):
        """POST /add-transaction with valid data should return success."""
        mock_services["tx_service"].add_new_transaction.return_value = (True, "")
        response = authenticated_client.post(
            "/add-transaction",
            json={
                "date": "2025-01-01",
                "amount": "1000",
                "description": "Lunch",
                "category": "food",
                "comment": "",
                "currency": "JPY",
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

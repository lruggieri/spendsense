"""Tests for the groups blueprint routes."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from domain.entities.group import Group
from domain.entities.transaction import Transaction


@pytest.fixture
def mock_services():
    """Set up mock services for the groups blueprint."""
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

    mock_tx_service = MagicMock()
    mock_tx_service.get_all_transactions.return_value = []
    mock_tx_service.get_all_transactions_filtered.return_value = []
    mock_tx_service.get_transactions_by_group.return_value = []

    mock_classification_service = MagicMock()
    mock_classification_service.classify_transactions.return_value = {}

    mock_group_service = MagicMock()
    mock_group_service.get_all_groups.return_value = []

    patches = {
        "cat": patch(
            "presentation.web.blueprints.groups.get_category_service",
            return_value=mock_category_service,
        ),
        "settings": patch(
            "presentation.web.blueprints.groups.get_user_settings_service",
            return_value=mock_user_settings_service,
        ),
        "tx": patch(
            "presentation.web.blueprints.groups.get_transaction_service",
            return_value=mock_tx_service,
        ),
        "classify": patch(
            "presentation.web.blueprints.groups.get_classification_service",
            return_value=mock_classification_service,
        ),
        "groups": patch(
            "presentation.web.blueprints.groups.get_group_service",
            return_value=mock_group_service,
        ),
        "tree_to_dict": patch(
            "presentation.web.blueprints.groups.tree_to_dict",
            return_value={"id": "all", "name": "All", "total": 0, "children": []},
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


class TestGroupsBlueprint:
    """Tests for the groups blueprint routes."""

    def test_groups_page_loads(self, authenticated_client, mock_services):
        """GET /groups should return 200."""
        response = authenticated_client.get("/groups")
        assert response.status_code == 200

    def test_create_group_missing_name(self, authenticated_client, mock_services):
        """POST /api/create-group with empty name should return 400."""
        response = authenticated_client.post(
            "/api/create-group",
            json={"name": ""},
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False
        assert "required" in data["error"].lower()

    def test_create_group_success(self, authenticated_client, mock_services):
        """POST /api/create-group with valid name should return success."""
        mock_services["group_service"].create_group.return_value = (True, None, "group-123")
        response = authenticated_client.post(
            "/api/create-group",
            json={"name": "My Group"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["group_id"] == "group-123"

    def test_update_group_missing_fields(self, authenticated_client, mock_services):
        """POST /api/update-group with missing group_id or name should return 400."""
        response = authenticated_client.post(
            "/api/update-group",
            json={"group_id": "", "name": ""},
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False

    def test_delete_group_missing_id(self, authenticated_client, mock_services):
        """POST /api/delete-group with missing group_id should return 400."""
        response = authenticated_client.post(
            "/api/delete-group",
            json={"group_id": ""},
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False

    def test_add_group_to_transaction_missing(self, authenticated_client, mock_services):
        """POST /api/add-group-to-transaction with missing fields should return 400."""
        response = authenticated_client.post(
            "/api/add-group-to-transaction",
            json={"tx_id": "", "group_id": ""},
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False

    def test_bulk_add_group_missing(self, authenticated_client, mock_services):
        """POST /api/bulk-add-group with missing fields should return 400."""
        response = authenticated_client.post(
            "/api/bulk-add-group",
            json={"tx_ids": [], "group_id": ""},
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False

    def test_groups_page_with_selected_group(self, authenticated_client, mock_services):
        """GET /groups?group_id=g1 should render the page with selected group transactions."""
        from domain.entities.category import Category

        group = Group(id="g1", name="Travel")
        mock_services["group_service"].get_all_groups.return_value = [group]

        tx = Transaction(
            id="tx1",
            date=datetime(2025, 1, 15, tzinfo=timezone.utc),
            amount=5000,
            description="Flight to Tokyo",
            category="transport",
            source="Manual",
            currency="JPY",
            groups=["g1"],
        )
        mock_services["tx_service"].get_all_transactions.return_value = [tx]
        mock_services["tx_service"].get_transactions_by_group.return_value = [tx]

        # CategoryTree expects a dict with an "internal" key containing Category objects
        transport_cat = Category(id="transport", name="Transport", description="", parent_id="all")
        mock_services["category_service"].get_categories_as_dict_list.return_value = {
            "internal": [transport_cat]
        }

        response = authenticated_client.get("/groups?group_id=g1")
        assert response.status_code == 200

    def test_groups_page_with_nonexistent_group(self, authenticated_client, mock_services):
        """GET /groups?group_id=missing should render without transactions."""
        mock_services["group_service"].get_all_groups.return_value = []

        response = authenticated_client.get("/groups?group_id=missing")
        assert response.status_code == 200

    def test_update_group_success(self, authenticated_client, mock_services):
        """POST /api/update-group with valid data should return success."""
        mock_services["group_service"].update_group.return_value = (True, None)
        response = authenticated_client.post(
            "/api/update-group",
            json={"group_id": "g1", "name": "Updated Name"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

    def test_delete_group_success(self, authenticated_client, mock_services):
        """POST /api/delete-group with valid data should return success."""
        mock_services["group_service"].delete_group.return_value = (True, None)
        response = authenticated_client.post(
            "/api/delete-group",
            json={"group_id": "g1"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

    def test_add_group_to_transaction_success(self, authenticated_client, mock_services):
        """POST /api/add-group-to-transaction with valid data should return success."""
        mock_services["group_service"].add_transaction_to_group.return_value = (True, None)
        response = authenticated_client.post(
            "/api/add-group-to-transaction",
            json={"tx_id": "tx1", "group_id": "g1"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

    def test_remove_group_from_transaction_missing(self, authenticated_client, mock_services):
        """POST /api/remove-group-from-transaction with missing fields should return 400."""
        response = authenticated_client.post(
            "/api/remove-group-from-transaction",
            json={"tx_id": "", "group_id": ""},
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False

    def test_remove_group_from_transaction_success(self, authenticated_client, mock_services):
        """POST /api/remove-group-from-transaction with valid data should return success."""
        mock_services["group_service"].remove_transaction_from_group.return_value = (True, None)
        response = authenticated_client.post(
            "/api/remove-group-from-transaction",
            json={"tx_id": "tx1", "group_id": "g1"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

    def test_bulk_add_group_success(self, authenticated_client, mock_services):
        """POST /api/bulk-add-group with valid data should return success."""
        mock_services["group_service"].add_transactions_to_group.return_value = (True, None, 3)
        response = authenticated_client.post(
            "/api/bulk-add-group",
            json={"tx_ids": ["tx1", "tx2", "tx3"], "group_id": "g1"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["count"] == 3

    def test_bulk_remove_group_missing(self, authenticated_client, mock_services):
        """POST /api/bulk-remove-group with missing fields should return 400."""
        response = authenticated_client.post(
            "/api/bulk-remove-group",
            json={"tx_ids": [], "group_id": ""},
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False

    def test_bulk_remove_group_success(self, authenticated_client, mock_services):
        """POST /api/bulk-remove-group with valid data should return success."""
        mock_services["group_service"].remove_transactions_from_group.return_value = (True, None, 2)
        response = authenticated_client.post(
            "/api/bulk-remove-group",
            json={"tx_ids": ["tx1", "tx2"], "group_id": "g1"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["count"] == 2

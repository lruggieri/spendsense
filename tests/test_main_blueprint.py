"""Tests for the main blueprint routes."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_services():
    """Set up mock services for the main blueprint."""
    mock_category_service = MagicMock()
    mock_category_service.get_categories_hierarchical.return_value = []
    mock_category_service.categories = {}
    mock_category_service.get_categories_as_dict_list.return_value = []
    mock_category_service.get_descendant_category_ids.return_value = set()

    mock_user_settings = MagicMock(currency="JPY", language="en", browser_settings={})
    mock_user_settings_service = MagicMock()
    mock_user_settings_service.get_user_settings.return_value = mock_user_settings
    mock_user_settings_service.get_currency_symbol.return_value = "\u00a5"
    mock_user_settings_service.get_currency_converter.return_value = MagicMock(
        convert=lambda a, f, t, d=None: a
    )
    mock_user_settings_service.get_supported_currencies.return_value = ["JPY", "USD", "EUR"]

    mock_tx_service = MagicMock()
    mock_tx_service.get_all_transactions.return_value = []
    mock_tx_service.get_all_transactions_filtered.return_value = []

    mock_classification_service = MagicMock()
    mock_classification_service.classify_transactions.return_value = {}

    tree_data = {"id": "all", "name": "All", "total": 0, "children": []}

    patches = {
        "cat": patch(
            "presentation.web.blueprints.main.get_category_service",
            return_value=mock_category_service,
        ),
        "settings": patch(
            "presentation.web.blueprints.main.get_user_settings_service",
            return_value=mock_user_settings_service,
        ),
        "tx": patch(
            "presentation.web.blueprints.main.get_transaction_service",
            return_value=mock_tx_service,
        ),
        "classify": patch(
            "presentation.web.blueprints.main.get_classification_service",
            return_value=mock_classification_service,
        ),
        "tree": patch(
            "presentation.web.blueprints.main.build_category_tree_data",
            return_value=tree_data,
        ),
        "invalidate": patch(
            "presentation.web.blueprints.main.invalidate_service_cache",
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
        "tree_data": tree_data,
        "patches": started,
    }

    for p in patches.values():
        p.stop()


class TestMainBlueprint:
    """Tests for the main blueprint routes."""

    def test_index_redirects_to_review(self, authenticated_client, mock_services):
        """GET / should redirect (302) to the review page."""
        response = authenticated_client.get("/")
        assert response.status_code == 302
        assert "/review" in response.headers["Location"]

    def test_recategorize_redirects(self, authenticated_client, mock_services):
        """POST /recategorize should redirect (302) back to review."""
        response = authenticated_client.post("/recategorize", data={})
        assert response.status_code == 302
        assert "/review" in response.headers["Location"]

    def test_charts_default_dates(self, authenticated_client, mock_services):
        """GET /charts without date params should return 200 with default dates."""
        response = authenticated_client.get("/charts")
        assert response.status_code == 200

    def test_charts_custom_dates(self, authenticated_client, mock_services):
        """GET /charts with explicit date range should return 200."""
        response = authenticated_client.get("/charts?from_date=2025-01-01&to_date=2025-12-31")
        assert response.status_code == 200

    def test_api_tree_data(self, authenticated_client, mock_services):
        """GET /api/tree-data should return JSON with tree data."""
        response = authenticated_client.get("/api/tree-data")
        assert response.status_code == 200
        data = response.get_json()
        assert data["id"] == "all"
        assert data["name"] == "All"
        assert data["total"] == 0
        assert "children" in data

    def test_trends_default(self, authenticated_client, mock_services):
        """GET /trends without date params should return 200."""
        response = authenticated_client.get("/trends")
        assert response.status_code == 200

    def test_api_debug_info(self, authenticated_client, mock_services):
        """GET /api/debug-info should return JSON with debug information."""
        with patch(
            "domain.services.currency_converter.CurrencyConverterService"
        ) as mock_currency_cls:
            mock_instance = MagicMock()
            mock_instance.converter = None
            mock_currency_cls.get_instance.return_value = mock_instance

            response = authenticated_client.get("/api/debug-info")

        assert response.status_code == 200
        data = response.get_json()
        assert "ecb_first_date" in data
        assert "ecb_last_date" in data

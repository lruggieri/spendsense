"""Tests for the 3 new client-side Gmail REST API endpoints."""

from unittest.mock import MagicMock, patch

import pytest


class TestEmailConfig:
    """Tests for GET /api/email/config"""

    def test_returns_302_when_unauthenticated(self, client, mock_session_datasource):
        """Endpoint requires login."""
        with patch(
            "presentation.web.decorators.get_session_datasource",
            return_value=mock_session_datasource,
        ):
            response = client.get("/api/email/config")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_returns_client_id_and_fetchers(self, authenticated_client):
        """Should return client_id, fetchers list, and default_fetch_date."""
        mock_fetcher_svc = MagicMock()
        mock_fetcher = MagicMock()
        mock_fetcher.id = "fetcher-uuid"
        mock_fetcher.name = "Chase"
        mock_fetcher.from_emails = ["alerts@chase.com"]
        mock_fetcher.subject_filter = "Your transaction"
        mock_fetcher.amount_pattern = r"\$(\d+\.\d{2})"
        mock_fetcher.merchant_pattern = None
        mock_fetcher.currency_pattern = None
        mock_fetcher.default_currency = "USD"
        mock_fetcher.negate_amount = False
        mock_fetcher_svc.get_enabled_fetchers.return_value = [mock_fetcher]

        mock_tx_svc = MagicMock()
        mock_tx_svc.get_last_transaction_date.return_value = None

        mock_creds_loader = MagicMock()
        mock_creds_loader.get_client_config.return_value = {"client_id": "test-client-id"}

        with patch(
            "presentation.web.blueprints.gmail.get_fetcher_service",
            return_value=mock_fetcher_svc,
        ), patch(
            "presentation.web.blueprints.gmail.get_transaction_service",
            return_value=mock_tx_svc,
        ), patch(
            "presentation.web.blueprints.gmail.get_credentials_loader_instance",
            return_value=mock_creds_loader,
        ):
            response = authenticated_client.get("/api/email/config")

        assert response.status_code == 200
        data = response.get_json()
        assert data["client_id"] == "test-client-id"
        assert isinstance(data["fetchers"], list)
        assert len(data["fetchers"]) == 1
        assert data["fetchers"][0]["id"] == "fetcher-uuid"
        assert data["fetchers"][0]["name"] == "Chase"
        assert "default_fetch_date" in data


class TestEmailCheckImported:
    """Tests for POST /api/email/check-imported"""

    def test_returns_302_when_unauthenticated(self, client, mock_session_datasource):
        """Endpoint requires login."""
        with patch(
            "presentation.web.decorators.get_session_datasource",
            return_value=mock_session_datasource,
        ):
            response = client.post(
                "/api/email/check-imported",
                json={"mail_ids": ["abc"]},
            )
        assert response.status_code == 302

    def test_filters_already_imported_ids(self, authenticated_client):
        """Should return only IDs already in the database."""
        mock_tx_svc = MagicMock()
        mock_tx_svc.get_processed_mail_ids.return_value = {"abc123", "xyz789"}

        with patch(
            "presentation.web.blueprints.gmail.get_transaction_service",
            return_value=mock_tx_svc,
        ):
            response = authenticated_client.post(
                "/api/email/check-imported",
                json={"mail_ids": ["abc123", "def456", "xyz789"]},
            )

        assert response.status_code == 200
        data = response.get_json()
        assert set(data["imported_ids"]) == {"abc123", "xyz789"}

    def test_returns_400_for_non_list_input(self, authenticated_client):
        """mail_ids must be a list."""
        response = authenticated_client.post(
            "/api/email/check-imported",
            json={"mail_ids": "not-a-list"},
        )
        assert response.status_code == 400

    def test_returns_empty_list_when_none_imported(self, authenticated_client):
        """If no IDs are already imported, imported_ids should be empty."""
        mock_tx_svc = MagicMock()
        mock_tx_svc.get_processed_mail_ids.return_value = set()

        with patch(
            "presentation.web.blueprints.gmail.get_transaction_service",
            return_value=mock_tx_svc,
        ):
            response = authenticated_client.post(
                "/api/email/check-imported",
                json={"mail_ids": ["new1", "new2"]},
            )

        assert response.status_code == 200
        data = response.get_json()
        assert data["imported_ids"] == []


class TestEmailImport:
    """Tests for POST /api/email/import"""

    def _make_tx(self, fetcher_id="f1"):
        return {
            "fetcher_id": fetcher_id,
            "mail_id": "msg1",
            "date_iso": "2025-01-15T10:30:00Z",
            "amount_str": "15.99",
            "description": "Starbucks",
            "currency": "USD",
            "source": "Chase",
        }

    def _mock_fetcher(self, fid="f1", currency="USD"):
        f = MagicMock()
        f.id = fid
        f.name = "Chase"
        f.default_currency = currency
        return f

    def test_returns_302_when_unauthenticated(self, client, mock_session_datasource):
        """Endpoint requires login."""
        with patch(
            "presentation.web.decorators.get_session_datasource",
            return_value=mock_session_datasource,
        ):
            response = client.post("/api/email/import", json={"transactions": []})
        assert response.status_code == 302

    def test_saves_transactions_and_returns_count(self, authenticated_client):
        """Valid transactions should be saved; response includes imported count."""
        fetcher = self._mock_fetcher()
        mock_fetcher_svc = MagicMock()
        mock_fetcher_svc.get_enabled_fetchers.return_value = [fetcher]

        mock_tx_svc = MagicMock()
        mock_tx_svc.add_transactions_batch.return_value = 1

        mock_cache = MagicMock()

        with patch(
            "presentation.web.blueprints.gmail.get_fetcher_service",
            return_value=mock_fetcher_svc,
        ), patch(
            "presentation.web.blueprints.gmail.get_transaction_service",
            return_value=mock_tx_svc,
        ), patch(
            "presentation.web.blueprints.gmail.get_cache_manager",
            return_value=mock_cache,
        ):
            response = authenticated_client.post(
                "/api/email/import",
                json={"transactions": [self._make_tx()]},
            )

        assert response.status_code == 200
        data = response.get_json()
        assert data["imported"] == 1
        assert data["skipped"] == 0
        mock_tx_svc.add_transactions_batch.assert_called_once()
        mock_cache.invalidate.assert_called_once()

    def test_returns_400_for_empty_list(self, authenticated_client):
        """Empty transactions list should return 400."""
        response = authenticated_client.post(
            "/api/email/import",
            json={"transactions": []},
        )
        assert response.status_code == 400

    def test_returns_400_for_oversized_batch(self, authenticated_client):
        """Batch exceeding MAX limit should return 400."""
        big_batch = [self._make_tx() for _ in range(501)]
        response = authenticated_client.post(
            "/api/email/import",
            json={"transactions": big_batch},
        )
        assert response.status_code == 400

    def test_skips_transactions_with_unknown_fetcher_id(self, authenticated_client):
        """Transactions whose fetcher_id doesn't belong to the user are skipped."""
        mock_fetcher_svc = MagicMock()
        mock_fetcher_svc.get_enabled_fetchers.return_value = []  # no fetchers

        mock_tx_svc = MagicMock()
        mock_tx_svc.add_transactions_batch.return_value = 0

        mock_cache = MagicMock()

        with patch(
            "presentation.web.blueprints.gmail.get_fetcher_service",
            return_value=mock_fetcher_svc,
        ), patch(
            "presentation.web.blueprints.gmail.get_transaction_service",
            return_value=mock_tx_svc,
        ), patch(
            "presentation.web.blueprints.gmail.get_cache_manager",
            return_value=mock_cache,
        ):
            response = authenticated_client.post(
                "/api/email/import",
                json={"transactions": [self._make_tx("unknown-fetcher")]},
            )

        assert response.status_code == 200
        data = response.get_json()
        assert data["imported"] == 0
        assert data["skipped"] == 1
        assert len(data["warnings"]) == 1
        mock_tx_svc.add_transactions_batch.assert_not_called()
        mock_cache.invalidate.assert_not_called()

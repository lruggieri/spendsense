"""Tests for the 3 new client-side Gmail REST API endpoints."""

from datetime import date, datetime, timezone
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
        mock_fetcher_svc.get_earliest_last_fetched_at.return_value = datetime(
            2026, 1, 1, tzinfo=timezone.utc
        )

        mock_tx_svc = MagicMock()
        mock_tx_svc.get_last_email_transaction_date.return_value = None

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
        assert data["user_email"] == "test@example.com"
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
        mock_tx_svc.filter_imported_mail_ids.return_value = {"abc123", "xyz789"}

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
        mock_tx_svc.filter_imported_mail_ids.assert_called_once_with(
            ["abc123", "def456", "xyz789"]
        )

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
        mock_tx_svc.filter_imported_mail_ids.return_value = set()

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


class TestFetchStartDate:
    """Tests for the default Gmail fetch start date."""

    def _calculate(self, app, last_fetched_at, last_email_tx=None):
        from presentation.web.blueprints.gmail import _calculate_fetch_start_date

        mock_tx_svc = MagicMock()
        mock_tx_svc.get_last_email_transaction_date.return_value = last_email_tx
        mock_fetcher_svc = MagicMock()
        mock_fetcher_svc.get_earliest_last_fetched_at.return_value = last_fetched_at
        result = _calculate_fetch_start_date(mock_tx_svc, mock_fetcher_svc)
        return result, mock_tx_svc, mock_fetcher_svc

    def test_uses_last_fetch_time_with_overlap(self, app):
        """Starts one day before the last completed fetch."""
        result, mock_tx_svc, mock_fetcher_svc = self._calculate(
            app, datetime(2026, 10, 14, 9, 0, tzinfo=timezone.utc)
        )
        assert result == "2026-10-13"
        mock_tx_svc.get_last_transaction_date.assert_not_called()

    def test_seeds_and_uses_email_transaction_date_as_baseline(self, app):
        baseline = datetime(2026, 9, 1, tzinfo=timezone.utc)
        _, _, mock_fetcher_svc = self._calculate(app, baseline, baseline)
        mock_fetcher_svc.seed_fetch_baseline.assert_called_once_with(baseline)
        mock_fetcher_svc.get_earliest_last_fetched_at.assert_called_once_with(baseline)

    def test_no_history_baseline_is_start_of_last_year(self, app):
        _, _, mock_fetcher_svc = self._calculate(
            app, datetime(2025, 1, 1, tzinfo=timezone.utc)
        )
        seeded = mock_fetcher_svc.seed_fetch_baseline.call_args[0][0]
        assert (seeded.year, seeded.month, seeded.day) == (datetime.now().year - 1, 1, 1)


class TestEmailFetchCompleted:
    """Tests for POST /api/email/fetch-completed"""

    def test_returns_302_when_unauthenticated(self, client, mock_session_datasource):
        with patch(
            "presentation.web.decorators.get_session_datasource",
            return_value=mock_session_datasource,
        ):
            response = client.post(
                "/api/email/fetch-completed",
                json={"fetcher_ids": ["f1"], "after_date": "2026-01-01"},
            )
        assert response.status_code == 302

    def test_records_completed_fetchers(self, authenticated_client):
        mock_fetcher_svc = MagicMock()
        mock_fetcher_svc.record_fetch_completed.return_value = 2

        with patch(
            "presentation.web.blueprints.gmail.get_fetcher_service",
            return_value=mock_fetcher_svc,
        ):
            response = authenticated_client.post(
                "/api/email/fetch-completed",
                json={"fetcher_ids": ["f1", "f2"], "after_date": "2026-01-10"},
            )

        assert response.status_code == 200
        assert response.get_json() == {"updated": 2}
        mock_fetcher_svc.record_fetch_completed.assert_called_once_with(
            ["f1", "f2"], date(2026, 1, 10), None
        )

    def test_passes_started_at(self, authenticated_client):
        mock_fetcher_svc = MagicMock()
        mock_fetcher_svc.record_fetch_completed.return_value = 1

        with patch(
            "presentation.web.blueprints.gmail.get_fetcher_service",
            return_value=mock_fetcher_svc,
        ):
            response = authenticated_client.post(
                "/api/email/fetch-completed",
                json={
                    "fetcher_ids": ["f1"],
                    "after_date": "2026-01-10",
                    "started_at": "2026-01-12T03:04:05.000Z",
                },
            )

        assert response.status_code == 200
        mock_fetcher_svc.record_fetch_completed.assert_called_once_with(
            ["f1"], date(2026, 1, 10), datetime(2026, 1, 12, 3, 4, 5, tzinfo=timezone.utc)
        )

    @pytest.mark.parametrize(
        "payload",
        [
            {"fetcher_ids": "f1", "after_date": "2026-01-10"},
            {"fetcher_ids": [1], "after_date": "2026-01-10"},
            {"fetcher_ids": ["f1"]},
            {"fetcher_ids": ["f1"], "after_date": "not-a-date"},
            {"fetcher_ids": ["f1"], "after_date": ""},
            {"fetcher_ids": ["f1"], "after_date": "2026-01-10", "started_at": "garbage"},
            ["invalid"],
            "invalid",
            42,
        ],
    )
    def test_returns_400_for_invalid_input(self, authenticated_client, payload):
        mock_fetcher_svc = MagicMock()
        with patch(
            "presentation.web.blueprints.gmail.get_fetcher_service",
            return_value=mock_fetcher_svc,
        ):
            response = authenticated_client.post("/api/email/fetch-completed", json=payload)
        assert response.status_code == 400
        mock_fetcher_svc.record_fetch_completed.assert_not_called()


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

        with patch(
            "presentation.web.blueprints.gmail.get_fetcher_service",
            return_value=mock_fetcher_svc,
        ), patch(
            "presentation.web.blueprints.gmail.get_transaction_service",
            return_value=mock_tx_svc,
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

        with patch(
            "presentation.web.blueprints.gmail.get_fetcher_service",
            return_value=mock_fetcher_svc,
        ), patch(
            "presentation.web.blueprints.gmail.get_transaction_service",
            return_value=mock_tx_svc,
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

    def _import_with_currency(self, authenticated_client, currency):
        """Helper: POST a single transaction with the given currency string."""
        fetcher = self._mock_fetcher(currency="JPY")
        mock_fetcher_svc = MagicMock()
        mock_fetcher_svc.get_enabled_fetchers.return_value = [fetcher]
        mock_tx_svc = MagicMock()
        mock_tx_svc.add_transactions_batch.return_value = 1

        with patch(
            "presentation.web.blueprints.gmail.get_fetcher_service",
            return_value=mock_fetcher_svc,
        ), patch(
            "presentation.web.blueprints.gmail.get_transaction_service",
            return_value=mock_tx_svc,
        ):
            tx = {**self._make_tx(), "currency": currency}
            response = authenticated_client.post(
                "/api/email/import",
                json={"transactions": [tx]},
            )
        return response.get_json(), mock_tx_svc

    def test_currency_kanji_yen_normalized(self, authenticated_client):
        """円 (kanji) should be normalized to JPY without a warning."""
        data, mock_tx_svc = self._import_with_currency(authenticated_client, "円")
        assert data["imported"] == 1
        assert data["warnings"] == []
        tx_saved = mock_tx_svc.add_transactions_batch.call_args[0][0][0]
        assert tx_saved.currency == "JPY"

    def test_currency_fullwidth_yen_normalized(self, authenticated_client):
        """￥ (fullwidth) should be normalized to JPY without a warning."""
        data, mock_tx_svc = self._import_with_currency(authenticated_client, "￥")
        assert data["imported"] == 1
        assert data["warnings"] == []
        tx_saved = mock_tx_svc.add_transactions_batch.call_args[0][0][0]
        assert tx_saved.currency == "JPY"

    def test_currency_name_yen_normalized(self, authenticated_client):
        """'Yen' (name) should be normalized to JPY without a warning."""
        data, mock_tx_svc = self._import_with_currency(authenticated_client, "Yen")
        assert data["imported"] == 1
        assert data["warnings"] == []
        tx_saved = mock_tx_svc.add_transactions_batch.call_args[0][0][0]
        assert tx_saved.currency == "JPY"

    def test_truly_unknown_currency_warns_and_falls_back(self, authenticated_client):
        """A currency string that can't be recognized should warn and use the fetcher default."""
        data, mock_tx_svc = self._import_with_currency(authenticated_client, "ZORKMID")
        assert data["imported"] == 1
        assert len(data["warnings"]) == 1
        assert "ZORKMID" in data["warnings"][0]
        tx_saved = mock_tx_svc.add_transactions_batch.call_args[0][0][0]
        assert tx_saved.currency == "JPY"  # fetcher default_currency

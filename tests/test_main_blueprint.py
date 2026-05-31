"""Tests for the main blueprint routes."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

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
    mock_user_settings_service.get_supported_currencies.return_value = [
        {"code": "JPY", "symbol": "¥", "name": "Japanese Yen", "minor_units": 0},
        {"code": "USD", "symbol": "$", "name": "US Dollar", "minor_units": 2},
        {"code": "EUR", "symbol": "€", "name": "Euro", "minor_units": 2},
    ]

    mock_tx_service = MagicMock()
    mock_tx_service.get_all_transactions.return_value = []
    mock_tx_service.get_all_transactions_filtered.return_value = []

    mock_classification_service = MagicMock()
    mock_classification_service.classify_transactions.return_value = {}

    mock_fetcher_service = MagicMock()
    mock_fetcher_service.get_all_fetchers.return_value = []

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
        "fetcher": patch(
            "presentation.web.blueprints.main.get_fetcher_service",
            return_value=mock_fetcher_service,
        ),
        "tree": patch(
            "presentation.web.blueprints.main.build_category_tree_data",
            return_value=tree_data,
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
        "fetcher_service": mock_fetcher_service,
        "tree_data": tree_data,
        "patches": started,
    }

    for p in patches.values():
        p.stop()


class TestLandingPage:
    """Tests for the public landing page and related public routes."""

    def test_index_unauthenticated_shows_landing(self, client):
        """GET / without a session cookie should render the landing page."""
        response = client.get("/")
        assert response.status_code == 200
        assert b"SpendSense" in response.data

    def test_index_with_session_cookie_redirects_to_review(self, client):
        """GET / with any session_token cookie should redirect to /review."""
        client.set_cookie("session_token", "some_token")
        response = client.get("/")
        assert response.status_code == 302
        assert "/review" in response.headers["Location"]

    def test_robots_txt_content_type(self, client):
        """GET /robots.txt should return text/plain."""
        response = client.get("/robots.txt")
        assert response.status_code == 200
        assert response.content_type.startswith("text/plain")

    def test_robots_txt_disallows_app_routes(self, client):
        """GET /robots.txt should disallow app routes for all crawlers including AI bots."""
        response = client.get("/robots.txt")
        data = response.data.decode()
        # Each User-agent block (*, GPTBot, Google-Extended, PerplexityBot) must
        # include the disallow rules — not just the general User-agent: * block.
        assert data.count("Disallow: /review") == 4
        assert data.count("Disallow: /api/") == 4

    def test_robots_txt_includes_sitemap(self, client):
        """GET /robots.txt should reference the sitemap."""
        response = client.get("/robots.txt")
        assert b"Sitemap:" in response.data
        assert b"sitemap.xml" in response.data

    def test_sitemap_xml_content_type(self, client):
        """GET /sitemap.xml should return application/xml."""
        response = client.get("/sitemap.xml")
        assert response.status_code == 200
        assert response.content_type.startswith("application/xml")

    def test_sitemap_xml_includes_public_urls(self, client):
        """GET /sitemap.xml should list / and /privacy-policy."""
        response = client.get("/sitemap.xml")
        assert b"<loc>" in response.data
        assert b"/privacy-policy" in response.data


class TestMainBlueprint:
    """Tests for the main blueprint routes."""

    def test_index_redirects_to_review(self, authenticated_client, mock_services):
        """GET / should redirect (302) to the review page when authenticated."""
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

    def test_charts_default_dates_with_tz_cookie(self, authenticated_client, mock_services):
        """GET /charts with tz cookie uses client timezone for default month."""
        # Simulate March 31 23:30 UTC — which is April 1 08:30 JST
        fake_now = datetime(2026, 3, 31, 23, 30, 0, tzinfo=timezone.utc)
        with patch("presentation.web.utils.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now.astimezone(ZoneInfo("Asia/Tokyo"))
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            authenticated_client.set_cookie("tz", "Asia/Tokyo")
            response = authenticated_client.get("/charts")
        assert response.status_code == 200
        html = response.data.decode()
        # The date inputs should show April (local month), not March (UTC month)
        assert 'value="2026-04-01"' in html
        assert 'value="2026-04-30"' in html

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

    def test_trends_includes_fetcher_usage(self, authenticated_client, mock_services):
        """GET /trends builds per-bank fetcher usage datasets without error."""
        from domain.entities.fetcher import Fetcher
        from domain.entities.transaction import Transaction

        fetcher = Fetcher(
            id="f-v1",
            user_id="test-user",
            name="My Bank",
            from_emails=["bank@example.com"],
            group_id="g-bank",
            version=1,
        )
        mock_services["fetcher_service"].get_all_fetchers.return_value = [fetcher]

        txs = [
            Transaction(
                id="t1",
                date=datetime(2024, 1, 15, tzinfo=timezone.utc),
                amount=1000,
                description="d",
                category="cat",
                source="src",
                currency="USD",
                fetcher_id="f-v1",
            ),
        ]
        mock_services["tx_service"].get_all_transactions_filtered.return_value = txs

        response = authenticated_client.get(
            "/trends?from_date=2024-01-01&to_date=2024-02-01"
        )
        assert response.status_code == 200
        assert b"My Bank" in response.data

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
        assert "app_version" in data
        assert "ecb_first_date" in data
        assert "ecb_last_date" in data


class TestGetClientTimezone:
    """Tests for get_client_timezone and get_client_now utilities."""

    def test_returns_none_without_cookie(self, app):
        """No tz cookie should return None."""
        from presentation.web.utils import get_client_timezone

        with app.test_request_context():
            assert get_client_timezone() is None

    def test_returns_zoneinfo_with_valid_cookie(self, app):
        """Valid tz cookie should return matching ZoneInfo."""
        from presentation.web.utils import get_client_timezone

        with app.test_request_context(headers={"Cookie": "tz=Asia/Tokyo"}):
            tz = get_client_timezone()
            assert tz is not None
            assert str(tz) == "Asia/Tokyo"

    def test_returns_none_with_invalid_cookie(self, app):
        """Invalid timezone name should return None, not raise."""
        from presentation.web.utils import get_client_timezone

        with app.test_request_context(headers={"Cookie": "tz=Not/A/Zone"}):
            assert get_client_timezone() is None

    def test_get_client_now_uses_cookie_timezone(self, app):
        """get_client_now should return time in the cookie's timezone."""
        from presentation.web.utils import get_client_now

        with app.test_request_context(headers={"Cookie": "tz=Asia/Tokyo"}):
            now = get_client_now()
            assert str(now.tzinfo) == "Asia/Tokyo"

    def test_get_client_now_falls_back_to_utc(self, app):
        """Without tz cookie, get_client_now should return UTC."""
        from presentation.web.utils import get_client_now

        with app.test_request_context():
            now = get_client_now()
            assert now.tzinfo == timezone.utc


class TestBuildFetcherUsageDatasets:
    """Unit tests for the build_fetcher_usage_datasets helper."""

    @staticmethod
    def _tx(tx_id, date_str, amount, fetcher_id, currency="USD"):
        from domain.entities.transaction import Transaction

        return Transaction(
            id=tx_id,
            date=datetime.fromisoformat(date_str),
            amount=amount,
            description="desc",
            category="cat",
            source="src",
            currency=currency,
            fetcher_id=fetcher_id,
        )

    @staticmethod
    def _converter():
        # Identity converter: returns the major-unit amount unchanged.
        return MagicMock(convert=lambda a, f, t, d=None: a)

    def test_returns_empty_list_for_no_transactions(self):
        from presentation.web.blueprints.main import build_fetcher_usage_datasets

        result = build_fetcher_usage_datasets([], {}, {}, self._converter(), "USD", [])
        assert result == []

    def test_groups_by_group_id_across_months(self):
        from presentation.web.blueprints.main import build_fetcher_usage_datasets

        # USD has 2 minor units, so amount=1000 -> 10.00 major units.
        txs = [
            self._tx("t1", "2024-01-15", 1000, "f-v1"),
            self._tx("t2", "2024-01-20", 2000, "f-v1"),
            self._tx("t3", "2024-02-10", 500, "f-v1"),
        ]
        fetcher_id_to_group = {"f-v1": "g-bank-a"}
        group_to_name = {"g-bank-a": "Bank A"}
        months = ["2024-01", "2024-02"]

        result = build_fetcher_usage_datasets(
            txs, fetcher_id_to_group, group_to_name, self._converter(), "USD", months
        )

        assert len(result) == 1
        ds = result[0]
        assert ds["label"] == "Bank A"
        assert ds["group_id"] == "g-bank-a"
        assert ds["count_data"] == [2, 1]
        assert ds["amount_data"] == [30.0, 5.0]

    def test_unresolvable_and_none_fetcher_go_to_unknown_bucket(self):
        from presentation.web.blueprints.main import (
            UNKNOWN_FETCHER_GROUP,
            UNKNOWN_FETCHER_LABEL,
            build_fetcher_usage_datasets,
        )

        txs = [
            self._tx("t1", "2024-01-15", 1000, None),
            self._tx("t2", "2024-01-20", 1000, "missing-id"),
        ]
        result = build_fetcher_usage_datasets(
            txs, {}, {}, self._converter(), "USD", ["2024-01"]
        )

        assert len(result) == 1
        ds = result[0]
        assert ds["group_id"] == UNKNOWN_FETCHER_GROUP
        assert ds["label"] == UNKNOWN_FETCHER_LABEL
        assert ds["count_data"] == [2]
        assert ds["amount_data"] == [20.0]

    def test_unknown_bucket_absent_when_all_resolvable(self):
        from presentation.web.blueprints.main import (
            UNKNOWN_FETCHER_GROUP,
            build_fetcher_usage_datasets,
        )

        txs = [self._tx("t1", "2024-01-15", 1000, "f-v1")]
        result = build_fetcher_usage_datasets(
            txs, {"f-v1": "g-a"}, {"g-a": "Bank A"}, self._converter(), "USD", ["2024-01"]
        )

        assert all(ds["group_id"] != UNKNOWN_FETCHER_GROUP for ds in result)

    def test_named_banks_sorted_then_unknown_last(self):
        from presentation.web.blueprints.main import (
            UNKNOWN_FETCHER_GROUP,
            build_fetcher_usage_datasets,
        )

        txs = [
            self._tx("t1", "2024-01-15", 1000, "f-z"),
            self._tx("t2", "2024-01-15", 1000, "f-a"),
            self._tx("t3", "2024-01-15", 1000, None),
        ]
        fetcher_id_to_group = {"f-z": "g-z", "f-a": "g-a"}
        group_to_name = {"g-z": "Zebra Bank", "g-a": "Apple Bank"}

        result = build_fetcher_usage_datasets(
            txs, fetcher_id_to_group, group_to_name, self._converter(), "USD", ["2024-01"]
        )

        assert [ds["label"] for ds in result[:2]] == ["Apple Bank", "Zebra Bank"]
        assert result[-1]["group_id"] == UNKNOWN_FETCHER_GROUP

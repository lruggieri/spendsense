"""Tests for the login_required decorator's redirect-to-login behavior."""

from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse


class TestLoginRequiredNextPreservation:
    def test_no_session_cookie_redirects_with_next(self, client):
        """Hitting a protected route while logged out must preserve the
        originally requested URL as ?next=... on the /login redirect, so the
        user lands back where they started after signing in."""
        with patch("presentation.web.decorators.get_session_datasource") as mock_ds:
            mock_ds.return_value.get_session.return_value = None
            response = client.get("/mcp-consent?txn=abc123")

        assert response.status_code == 302
        location = urlparse(response.headers["Location"])
        assert location.path == "/login"
        next_param = parse_qs(location.query)["next"][0]
        assert next_param == "/mcp-consent?txn=abc123"

    def test_expired_session_redirects_with_next(self, client):
        """An invalid/expired session cookie must also preserve ?next=..."""
        with patch("presentation.web.decorators.get_session_datasource") as mock_ds:
            mock_ds.return_value.get_session.return_value = None
            client.set_cookie("session_token", "stale_token")
            response = client.get("/mcp-consent?txn=abc123")

        assert response.status_code == 302
        location = urlparse(response.headers["Location"])
        assert location.path == "/login"
        next_param = parse_qs(location.query)["next"][0]
        assert next_param == "/mcp-consent?txn=abc123"

    def test_no_query_string_omits_trailing_question_mark(self, client):
        """A protected route with no query string must not produce next=/path?"""
        with patch("presentation.web.decorators.get_session_datasource") as mock_ds:
            mock_ds.return_value.get_session.return_value = None
            response = client.get("/mcp-consent")

        location = urlparse(response.headers["Location"])
        next_param = parse_qs(location.query)["next"][0]
        assert next_param == "/mcp-consent"

    def test_logged_in_but_not_onboarded_stashes_next_for_after_onboarding(
        self, client, mock_session_datasource
    ):
        """A logged-in user who hasn't finished onboarding must have their
        original destination (e.g. an MCP OAuth consent screen) preserved
        across the onboarding detour, not silently dropped."""
        settings_obj = MagicMock()
        settings_obj.browser_settings = {"onboarding_step": 1}
        settings_svc = MagicMock()
        settings_svc.get_user_settings.return_value = settings_obj

        with patch(
            "presentation.web.decorators.get_session_datasource",
            return_value=mock_session_datasource,
        ), patch(
            "presentation.web.decorators.get_user_settings_service",
            return_value=settings_svc,
        ):
            client.set_cookie("session_token", "valid_test_token")
            response = client.get("/mcp-consent?txn=abc123")

        assert response.status_code == 302
        assert response.headers["Location"] == "/onboarding"
        with client.session_transaction() as sess:
            assert sess["oauth_next"] == "/mcp-consent?txn=abc123"

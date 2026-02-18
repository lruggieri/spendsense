"""Integration tests for Flask blueprint HTTP request/response cycles."""

from unittest.mock import MagicMock, patch

import pytest


class TestUnauthenticatedAccess:
    """Tests for routes that don't require authentication."""

    def test_login_page_accessible_without_auth(self, client):
        """Login page should render without any session."""
        with patch(
            "presentation.web.blueprints.auth.get_session_datasource",
            return_value=MagicMock(get_session=MagicMock(return_value=None)),
        ):
            response = client.get("/login")
        assert response.status_code == 200

    def test_api_supported_currencies_returns_json(self, client):
        """/api/supported-currencies is public and returns a JSON list."""
        response = client.get("/api/supported-currencies")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert isinstance(data["currencies"], list)


class TestAuthRedirects:
    """Tests for authentication enforcement on protected routes."""

    def test_protected_route_redirects_without_auth(
        self,
        client,
        mock_session_datasource,
    ):
        """A protected route should redirect to /login when no session cookie is set."""
        with patch(
            "presentation.web.decorators.get_session_datasource",
            return_value=mock_session_datasource,
        ):
            response = client.get("/settings/fetchers")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_invalid_session_redirects_to_login(
        self,
        client,
        mock_session_datasource,
    ):
        """An invalid session token should redirect to /login."""
        with patch(
            "presentation.web.decorators.get_session_datasource",
            return_value=mock_session_datasource,
        ):
            client.set_cookie("session_token", "invalid_token")
            response = client.get("/settings/fetchers")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]


class TestAuthenticatedAccess:
    """Tests for routes accessed with a valid session."""

    def test_protected_route_accessible_with_valid_session(
        self,
        authenticated_client,
    ):
        """A protected route should return 200 when a valid session exists."""
        mock_fetcher_service = MagicMock()
        mock_fetcher_service.get_enabled_fetchers_for_list.return_value = []
        with patch(
            "presentation.web.blueprints.fetchers.get_fetcher_service",
            return_value=mock_fetcher_service,
        ):
            response = authenticated_client.get("/settings/fetchers")
        assert response.status_code == 200

    def test_fetchers_page_uses_service_factory(self, authenticated_client):
        """The fetchers page should call get_fetcher_service to build its data."""
        mock_fetcher_service = MagicMock()
        mock_fetcher_service.get_enabled_fetchers_for_list.return_value = []
        with patch(
            "presentation.web.blueprints.fetchers.get_fetcher_service",
            return_value=mock_fetcher_service,
        ) as patched:
            authenticated_client.get("/settings/fetchers")
        patched.assert_called_once()


class TestLogout:
    """Tests for the logout flow."""

    def test_logout_clears_session_cookie(
        self,
        client,
        mock_session_datasource,
    ):
        """Logout should clear the session cookie and redirect to /login."""
        with patch(
            "presentation.web.blueprints.auth.get_session_datasource",
            return_value=mock_session_datasource,
        ):
            client.set_cookie("session_token", "valid_test_token")
            response = client.get("/logout")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]
        # The session cookie should be cleared (set to empty with expires=0)
        set_cookie_headers = response.headers.getlist("Set-Cookie")
        cookie_str = " ".join(set_cookie_headers)
        assert "session_token=" in cookie_str

    def test_logout_clears_encryption_cookie(
        self,
        client,
        mock_session_datasource,
    ):
        """Logout should clear the encryption_key cookie to prevent cross-user DEK leakage."""
        with patch(
            "presentation.web.blueprints.auth.get_session_datasource",
            return_value=mock_session_datasource,
        ):
            client.set_cookie("session_token", "valid_test_token")
            client.set_cookie("encryption_key", "some-dek-value")
            response = client.get("/logout")
        set_cookie_headers = response.headers.getlist("Set-Cookie")
        cookie_str = " ".join(set_cookie_headers)
        assert "encryption_key=" in cookie_str

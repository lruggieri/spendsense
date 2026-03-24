"""Tests for the settings blueprint routes."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_services():
    """Set up mock services for the settings blueprint."""
    mock_user_settings = MagicMock(currency="JPY", language="en", browser_settings={})
    mock_user_settings_service = MagicMock()
    mock_user_settings_service.get_user_settings.return_value = mock_user_settings
    mock_user_settings_service.get_supported_currencies.return_value = [
        {"code": "JPY", "symbol": "¥", "name": "Japanese Yen", "minor_units": 0},
        {"code": "USD", "symbol": "$", "name": "US Dollar", "minor_units": 2},
        {"code": "EUR", "symbol": "€", "name": "Euro", "minor_units": 2},
    ]
    mock_user_settings_service.update_user_settings.return_value = (True, None)

    patches = {
        "settings": patch(
            "presentation.web.blueprints.settings.get_user_settings_service",
            return_value=mock_user_settings_service,
        ),
    }

    started = {}
    for key, p in patches.items():
        started[key] = p.start()

    yield {
        "user_settings_service": mock_user_settings_service,
        "patches": started,
    }

    for p in patches.values():
        p.stop()


class TestSettingsBlueprint:
    """Tests for the settings blueprint routes."""

    def test_settings_page_loads(self, authenticated_client, mock_services):
        """GET /settings should return 200."""
        response = authenticated_client.get("/settings")
        assert response.status_code == 200

    def test_update_settings(self, authenticated_client, mock_services):
        """POST /api/update-settings with valid data should return success JSON."""
        response = authenticated_client.post(
            "/api/update-settings",
            json={"language": "en", "currency": "USD"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

    def test_update_browser_settings_merges_keys(self, authenticated_client, mock_services):
        """PUT /api/user-settings/browser should merge into existing browser_settings."""
        svc = mock_services["user_settings_service"]

        # Simulate existing browser_settings with onboarding state
        existing = MagicMock(
            currency="USD",
            language="en",
            browser_settings={
                "onboarding_step": 3,
                "onboarding_started_at": "2026-01-01T00:00:00Z",
            },
        )
        svc.get_user_settings.return_value = existing

        # Client sends only fetcher_advanced_mode
        response = authenticated_client.put(
            "/api/user-settings/browser",
            json={"browser_settings": {"fetcher_advanced_mode": True}},
        )
        assert response.status_code == 200

        # Verify the update was called with merged settings
        call_kwargs = svc.update_user_settings.call_args[1]
        saved = call_kwargs["browser_settings"]
        assert saved["fetcher_advanced_mode"] is True
        assert saved["onboarding_step"] == 3
        assert saved["onboarding_started_at"] == "2026-01-01T00:00:00Z"

    def test_update_browser_settings_overwrites_existing_key(
        self, authenticated_client, mock_services
    ):
        """PUT /api/user-settings/browser should overwrite keys that are sent."""
        svc = mock_services["user_settings_service"]
        existing = MagicMock(
            currency="USD",
            language="en",
            browser_settings={"fetcher_advanced_mode": False, "onboarding_step": 2},
        )
        svc.get_user_settings.return_value = existing

        response = authenticated_client.put(
            "/api/user-settings/browser",
            json={"browser_settings": {"fetcher_advanced_mode": True}},
        )
        assert response.status_code == 200

        call_kwargs = svc.update_user_settings.call_args[1]
        saved = call_kwargs["browser_settings"]
        assert saved["fetcher_advanced_mode"] is True
        assert saved["onboarding_step"] == 2

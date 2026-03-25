"""Tests for the onboarding blueprint."""

import json
from unittest.mock import MagicMock, patch

import pytest

from presentation.web.blueprints.onboarding import ONBOARDING_STEPS, ONBOARDING_VERSION


class TestOnboardingStepDefinitions:
    """Test onboarding step configuration."""

    def test_step_4_exists(self):
        """Step 4 (encryption) should be defined."""
        assert len(ONBOARDING_STEPS) == 4
        step4 = ONBOARDING_STEPS[3]
        assert step4["key"] == "encryption"
        assert step4.get("optional") is True

    def test_version_bumped(self):
        """ONBOARDING_VERSION should be 2 to surface new step to existing users."""
        assert ONBOARDING_VERSION == 2

    def test_required_steps_unchanged(self):
        """First 3 steps should still be required (no 'optional' flag)."""
        for step in ONBOARDING_STEPS[:3]:
            assert step.get("optional") is not True


class TestOnboardingStep4:
    """Test step 4 page and advance behavior."""

    @pytest.fixture
    def _mock_services(self):
        """Patch service factories used in onboarding routes."""
        with patch(
            "presentation.web.blueprints.onboarding.get_user_settings_service"
        ) as mock_settings, patch(
            "presentation.web.blueprints.onboarding.get_fetcher_service"
        ) as mock_fetcher, patch(
            "presentation.web.blueprints.onboarding.get_category_service"
        ) as mock_category, patch(
            "presentation.web.blueprints.onboarding.get_pattern_service"
        ) as mock_pattern, patch(
            "presentation.web.blueprints.onboarding.get_encryption_service"
        ) as mock_enc:

            # settings service returns in-progress onboarding at step 4
            settings_svc = MagicMock()
            settings_obj = MagicMock()
            settings_obj.browser_settings = {
                "onboarding_step": 4,
                "onboarding_started_at": "2025-01-01",
            }
            settings_svc.get_user_settings.return_value = settings_obj
            settings_svc.update_user_settings.return_value = (True, None)
            mock_settings.return_value = settings_svc

            # other services with items (previous steps complete)
            fetcher_svc = MagicMock()
            fetcher_svc.count_fetchers.return_value = 1
            mock_fetcher.return_value = fetcher_svc

            cat_svc = MagicMock()
            cat_svc.count_categories.return_value = 5
            mock_category.return_value = cat_svc

            pattern_svc = MagicMock()
            pattern_svc.count_patterns.return_value = 3
            mock_pattern.return_value = pattern_svc

            enc_svc = MagicMock()
            enc_svc.has_encryption.return_value = False
            mock_enc.return_value = enc_svc

            yield {
                "settings": settings_svc,
                "enc": enc_svc,
            }

    def test_step4_renders(self, authenticated_client, _mock_services):
        """Step 4 page should render with encryption content."""
        response = authenticated_client.get("/onboarding/step/4")
        assert response.status_code == 200
        assert b"Protect Your Data" in response.data

    def test_advance_past_optional_step(self, authenticated_client, _mock_services):
        """Advancing past optional step 4 should succeed even with count=0."""
        response = authenticated_client.post(
            "/api/onboarding/advance",
            data=json.dumps({"current_step": 4}),
            content_type="application/json",
        )
        data = response.get_json()
        assert data["success"] is True
        assert data["next_step"] == 0  # completed

    def test_advance_returns_error_when_db_write_fails(
        self, authenticated_client, _mock_services
    ):
        """Advance should return 500 when the DB write fails (e.g., database locked)."""
        _mock_services["settings"].update_user_settings.return_value = (False, "database is locked")
        response = authenticated_client.post(
            "/api/onboarding/advance",
            data=json.dumps({"current_step": 4}),
            content_type="application/json",
        )
        assert response.status_code == 500
        data = response.get_json()
        assert data["success"] is False

    def test_step4_shows_existing_credentials(self, authenticated_client, _mock_services):
        """Step 4 should display already registered passkeys."""
        _mock_services["enc"].has_encryption.return_value = True
        _mock_services["enc"].get_credentials_for_user.return_value = [
            {"device_name": "macOS", "created_at": "2025-06-01T00:00:00Z", "credential_id": "abc"},
        ]
        response = authenticated_client.get("/onboarding/step/4")
        assert response.status_code == 200
        assert b"Registered Passkeys" in response.data
        assert b"macOS" in response.data
        assert b"2025-06-01" in response.data
        assert b"Add Another Passkey" in response.data

    def test_step4_no_credentials_shows_register(self, authenticated_client, _mock_services):
        """Step 4 with no credentials should show 'Register Passkey' button."""
        _mock_services["enc"].has_encryption.return_value = False
        _mock_services["enc"].get_credentials_for_user.return_value = []
        response = authenticated_client.get("/onboarding/step/4")
        assert response.status_code == 200
        assert b"Registered Passkeys" not in response.data
        assert b"Register Passkey" in response.data


class TestEncryptionBannerSuppression:
    """Test that encryption banners are hidden during onboarding."""

    @pytest.fixture
    def _mock_services_with_banner(self):
        """Patch services so encryption banner would normally show."""
        with patch(
            "presentation.web.blueprints.onboarding.get_user_settings_service"
        ) as mock_settings, patch(
            "presentation.web.blueprints.onboarding.get_fetcher_service"
        ) as mock_fetcher, patch(
            "presentation.web.blueprints.onboarding.get_category_service"
        ) as mock_category, patch(
            "presentation.web.blueprints.onboarding.get_pattern_service"
        ) as mock_pattern, patch(
            "presentation.web.blueprints.onboarding.get_encryption_service"
        ) as mock_enc, patch(
            "presentation.web.utils.get_encryption_service"
        ) as mock_ctx_enc, patch(
            "presentation.web.utils.get_user_settings_service"
        ) as mock_ctx_settings:

            # Settings: onboarding at step 1
            settings_svc = MagicMock()
            settings_obj = MagicMock()
            settings_obj.browser_settings = {
                "onboarding_step": 1,
                "onboarding_started_at": "2025-01-01",
            }
            settings_svc.get_user_settings.return_value = settings_obj
            settings_svc.update_user_settings.return_value = (True, None)
            mock_settings.return_value = settings_svc

            # Context processor settings (banner not dismissed)
            ctx_settings_svc = MagicMock()
            ctx_settings_obj = MagicMock()
            ctx_settings_obj.browser_settings = {}
            ctx_settings_svc.get_user_settings.return_value = ctx_settings_obj
            mock_ctx_settings.return_value = ctx_settings_svc

            # Encryption not set up -> banner would show
            enc_svc = MagicMock()
            enc_svc.has_encryption.return_value = False
            enc_svc.get_credentials_for_user.return_value = []
            mock_enc.return_value = enc_svc
            mock_ctx_enc.return_value = enc_svc

            fetcher_svc = MagicMock()
            fetcher_svc.count_fetchers.return_value = 0
            fetcher_svc.get_enabled_fetchers_for_list.return_value = []
            mock_fetcher.return_value = fetcher_svc

            cat_svc = MagicMock()
            cat_svc.count_categories.return_value = 0
            mock_category.return_value = cat_svc

            pattern_svc = MagicMock()
            pattern_svc.count_patterns.return_value = 0
            mock_pattern.return_value = pattern_svc

            yield

    def test_encryption_banner_hidden_during_onboarding(
        self, authenticated_client, _mock_services_with_banner
    ):
        """Encryption setup banner should not appear on onboarding pages."""
        response = authenticated_client.get("/onboarding/step/1")
        assert response.status_code == 200
        assert b"Protect your data with end-to-end encryption" not in response.data

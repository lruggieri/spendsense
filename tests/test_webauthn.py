"""Tests for the WebAuthn blueprint and encryption middleware."""

import base64
import json
import os
from unittest.mock import MagicMock, patch

import pytest
from flask import request

# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def mock_encryption_service():
    """Create a mock encryption service."""
    service = MagicMock()
    service.has_encryption.return_value = False
    service.get_credentials_for_user.return_value = []
    service.get_credential.return_value = None
    return service


@pytest.fixture
def mock_webauthn_services(mock_encryption_service):
    """Set up mock services for the webauthn blueprint."""
    patches = {
        "encryption": patch(
            "presentation.web.blueprints.webauthn.get_encryption_service",
            return_value=mock_encryption_service,
        ),
    }

    started = {}
    for key, p in patches.items():
        started[key] = p.start()

    yield {
        "encryption_service": mock_encryption_service,
        "patches": started,
    }

    for p in patches.values():
        p.stop()


# =========================================================================
# Registration endpoint tests
# =========================================================================


class TestRegisterOptions:
    """Tests for /api/webauthn/register/options."""

    def test_returns_valid_json(self, authenticated_client, mock_webauthn_services):
        with patch(
            "presentation.web.blueprints.webauthn.generate_registration_options"
        ) as mock_gen, patch(
            "presentation.web.blueprints.webauthn.options_to_json"
        ) as mock_to_json:
            mock_to_json.return_value = json.dumps(
                {
                    "challenge": "dGVzdC1jaGFsbGVuZ2U",
                    "rp": {"name": "SpendSense", "id": "localhost"},
                    "user": {"id": "dXNlcg", "name": "test@example.com", "displayName": "Test"},
                    "pubKeyCredParams": [{"type": "public-key", "alg": -7}],
                    "authenticatorSelection": {},
                    "timeout": 60000,
                }
            )

            response = authenticated_client.get("/api/webauthn/register/options")
            assert response.status_code == 200
            data = response.get_json()
            assert "challenge" in data
            assert "rp" in data
            assert "extensions" in data
            assert data["extensions"].get("prf") == {}

    def test_excludes_existing_credentials(self, authenticated_client, mock_webauthn_services):
        mock_webauthn_services["encryption_service"].get_credentials_for_user.return_value = [
            {"credential_id": base64.b64encode(b"existing-cred").decode("ascii")},
        ]

        with patch(
            "presentation.web.blueprints.webauthn.generate_registration_options"
        ) as mock_gen, patch(
            "presentation.web.blueprints.webauthn.options_to_json"
        ) as mock_to_json:
            mock_to_json.return_value = json.dumps(
                {
                    "challenge": "dGVzdA",
                    "rp": {"name": "Test", "id": "localhost"},
                    "user": {"id": "dQ", "name": "test", "displayName": "Test"},
                    "pubKeyCredParams": [],
                    "authenticatorSelection": {},
                    "timeout": 60000,
                }
            )

            authenticated_client.get("/api/webauthn/register/options")
            call_kwargs = mock_gen.call_args
            assert len(call_kwargs.kwargs.get("exclude_credentials", [])) == 1


class TestRegisterVerify:
    """Tests for /api/webauthn/register/verify."""

    def test_no_data_returns_400(self, authenticated_client, mock_webauthn_services):
        response = authenticated_client.post(
            "/api/webauthn/register/verify",
            content_type="application/json",
            data=json.dumps(None),
        )
        assert response.status_code == 400

    def test_no_challenge_returns_400(self, authenticated_client, mock_webauthn_services):
        response = authenticated_client.post(
            "/api/webauthn/register/verify",
            content_type="application/json",
            data=json.dumps({"credential": {}}),
        )
        assert response.status_code == 400
        data = response.get_json()
        assert "challenge" in data["error"].lower()

    def test_first_passkey_calls_setup_encryption(
        self, authenticated_client, mock_webauthn_services
    ):
        """First passkey registration should generate a new DEK via setup_encryption."""
        enc_svc = mock_webauthn_services["encryption_service"]
        enc_svc.has_encryption.return_value = False
        enc_svc.setup_encryption.return_value = "new_dek_b64"

        with authenticated_client.session_transaction() as sess:
            sess["webauthn_register_challenge"] = "dGVzdC1jaGFsbGVuZ2U"

        with patch(
            "presentation.web.blueprints.webauthn.verify_registration_response"
        ) as mock_verify:
            mock_verify.return_value = MagicMock(
                credential_id=b"cred-id-bytes",
                credential_public_key=b"pub-key",
                sign_count=0,
            )

            response = authenticated_client.post(
                "/api/webauthn/register/verify",
                content_type="application/json",
                data=json.dumps(
                    {
                        "credential": {
                            "id": "abc",
                            "rawId": "abc",
                            "response": {
                                "attestationObject": "YQ",
                                "clientDataJSON": "YQ",
                            },
                            "type": "public-key",
                        },
                        "kek": "kek_value",
                        "prfSalt": "salt_value",
                        "deviceName": "Test Device",
                    }
                ),
            )

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["dek"] == "new_dek_b64"
        enc_svc.setup_encryption.assert_called_once()
        enc_svc.add_passkey_wrapper.assert_not_called()

    def test_additional_passkey_calls_add_passkey_wrapper(
        self, authenticated_client, mock_webauthn_services
    ):
        """Adding another passkey should re-wrap the existing DEK, not generate a new one."""
        enc_svc = mock_webauthn_services["encryption_service"]
        enc_svc.has_encryption.return_value = True

        with authenticated_client.session_transaction() as sess:
            sess["webauthn_register_challenge"] = "dGVzdC1jaGFsbGVuZ2U"

        with patch(
            "presentation.web.blueprints.webauthn.verify_registration_response"
        ) as mock_verify:
            mock_verify.return_value = MagicMock(
                credential_id=b"cred-id-bytes",
                credential_public_key=b"pub-key",
                sign_count=0,
            )

            response = authenticated_client.post(
                "/api/webauthn/register/verify",
                content_type="application/json",
                data=json.dumps(
                    {
                        "credential": {
                            "id": "abc",
                            "rawId": "abc",
                            "response": {
                                "attestationObject": "YQ",
                                "clientDataJSON": "YQ",
                            },
                            "type": "public-key",
                        },
                        "kek": "kek_value",
                        "prfSalt": "salt_value",
                        "deviceName": "Test Device",
                        "existingDek": "existing_dek_b64",
                    }
                ),
            )

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["dek"] == "existing_dek_b64"
        enc_svc.add_passkey_wrapper.assert_called_once()
        enc_svc.setup_encryption.assert_not_called()

    def test_additional_passkey_without_existing_dek_rejected(
        self, authenticated_client, mock_webauthn_services
    ):
        """Adding a passkey when encryption exists but user isn't unlocked should be rejected."""
        enc_svc = mock_webauthn_services["encryption_service"]
        enc_svc.has_encryption.return_value = True

        with authenticated_client.session_transaction() as sess:
            sess["webauthn_register_challenge"] = "dGVzdC1jaGFsbGVuZ2U"

        with patch(
            "presentation.web.blueprints.webauthn.verify_registration_response"
        ) as mock_verify:
            mock_verify.return_value = MagicMock(
                credential_id=b"cred-id-bytes",
                credential_public_key=b"pub-key",
                sign_count=0,
            )

            response = authenticated_client.post(
                "/api/webauthn/register/verify",
                content_type="application/json",
                data=json.dumps(
                    {
                        "credential": {
                            "id": "abc",
                            "rawId": "abc",
                            "response": {
                                "attestationObject": "YQ",
                                "clientDataJSON": "YQ",
                            },
                            "type": "public-key",
                        },
                        "kek": "kek_value",
                        "prfSalt": "salt_value",
                        "deviceName": "Test Device",
                        # No existingDek — user isn't unlocked
                    }
                ),
            )

        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False
        assert "unlock" in data["error"].lower()
        enc_svc.setup_encryption.assert_not_called()
        enc_svc.add_passkey_wrapper.assert_not_called()


# =========================================================================
# Authentication endpoint tests
# =========================================================================


class TestAuthenticateOptions:
    """Tests for /api/webauthn/authenticate/options."""

    def test_no_passkeys_returns_404(self, authenticated_client, mock_webauthn_services):
        mock_webauthn_services["encryption_service"].get_credentials_for_user.return_value = []
        response = authenticated_client.get("/api/webauthn/authenticate/options")
        assert response.status_code == 404

    def test_returns_options_with_prf_salts(self, authenticated_client, mock_webauthn_services):
        cred_id = base64.b64encode(b"test-cred").decode("ascii")
        mock_webauthn_services["encryption_service"].get_credentials_for_user.return_value = [
            {"credential_id": cred_id},
        ]
        mock_webauthn_services["encryption_service"].get_prf_salt.return_value = "test-salt"

        with patch(
            "presentation.web.blueprints.webauthn.generate_authentication_options"
        ) as mock_gen, patch(
            "presentation.web.blueprints.webauthn.options_to_json"
        ) as mock_to_json:
            mock_to_json.return_value = json.dumps(
                {
                    "challenge": "dGVzdA",
                    "rpId": "localhost",
                    "allowCredentials": [{"id": cred_id, "type": "public-key"}],
                    "userVerification": "required",
                    "timeout": 60000,
                }
            )

            response = authenticated_client.get("/api/webauthn/authenticate/options")
            assert response.status_code == 200
            data = response.get_json()
            assert "prfSalts" in data
            assert cred_id in data["prfSalts"]
            assert data["prfSalts"][cred_id] == "test-salt"


class TestAuthenticateVerify:
    """Tests for /api/webauthn/authenticate/verify."""

    def test_no_data_returns_400(self, authenticated_client, mock_webauthn_services):
        response = authenticated_client.post(
            "/api/webauthn/authenticate/verify",
            content_type="application/json",
            data=json.dumps(None),
        )
        assert response.status_code == 400

    def test_no_challenge_returns_400(self, authenticated_client, mock_webauthn_services):
        response = authenticated_client.post(
            "/api/webauthn/authenticate/verify",
            content_type="application/json",
            data=json.dumps({"credentialId": "abc", "credential": {}}),
        )
        assert response.status_code == 400
        data = response.get_json()
        assert "challenge" in data["error"].lower()


# =========================================================================
# DEK unwrap endpoint tests
# =========================================================================


class TestUnwrapDek:
    """Tests for /api/encryption/unwrap-dek."""

    def test_missing_fields_returns_400(self, authenticated_client, mock_webauthn_services):
        response = authenticated_client.post(
            "/api/encryption/unwrap-dek",
            content_type="application/json",
            data=json.dumps({"kek": "abc"}),
        )
        assert response.status_code == 400

    def test_valid_unwrap(self, authenticated_client, mock_webauthn_services):
        mock_webauthn_services["encryption_service"].unwrap_dek.return_value = "dek_base64_value"

        response = authenticated_client.post(
            "/api/encryption/unwrap-dek",
            content_type="application/json",
            data=json.dumps({"kek": "kek_value", "credentialId": "cred1"}),
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["dek"] == "dek_base64_value"

    def test_unwrap_failure(self, authenticated_client, mock_webauthn_services):
        mock_webauthn_services["encryption_service"].unwrap_dek.side_effect = ValueError("bad key")

        response = authenticated_client.post(
            "/api/encryption/unwrap-dek",
            content_type="application/json",
            data=json.dumps({"kek": "bad_kek", "credentialId": "cred1"}),
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False


# =========================================================================
# Page route tests
# =========================================================================


class TestPasskeyPages:
    """Tests for passkey setup and login pages."""

    def test_setup_page(self, authenticated_client, mock_webauthn_services):
        response = authenticated_client.get("/passkey/setup")
        assert response.status_code == 200

    def test_login_page(self, authenticated_client, mock_webauthn_services):
        response = authenticated_client.get("/passkey/login")
        assert response.status_code == 200


# =========================================================================
# Dismiss banner endpoint tests
# =========================================================================


class TestDismissEncryptionBanner:
    """Tests for /api/encryption/dismiss-banner."""

    def test_dismisses_banner(self, authenticated_client, mock_webauthn_services):
        """Should set encryption_banner_dismissed in user settings."""
        mock_settings_service = MagicMock()
        mock_settings = MagicMock()
        mock_settings.browser_settings = {}
        mock_settings_service.get_user_settings.return_value = mock_settings

        with patch(
            "presentation.web.blueprints.webauthn.get_user_settings_service",
            return_value=mock_settings_service,
        ):
            response = authenticated_client.post("/api/encryption/dismiss-banner")

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        mock_settings_service.update_user_settings.assert_called_once_with(
            browser_settings={"encryption_banner_dismissed": True},
        )

    def test_preserves_existing_browser_settings(
        self, authenticated_client, mock_webauthn_services
    ):
        """Should merge into existing browser_settings, not overwrite them."""
        mock_settings_service = MagicMock()
        mock_settings = MagicMock()
        mock_settings.browser_settings = {"some_other_setting": "value"}
        mock_settings_service.get_user_settings.return_value = mock_settings

        with patch(
            "presentation.web.blueprints.webauthn.get_user_settings_service",
            return_value=mock_settings_service,
        ):
            response = authenticated_client.post("/api/encryption/dismiss-banner")

        assert response.status_code == 200
        mock_settings_service.update_user_settings.assert_called_once_with(
            browser_settings={"some_other_setting": "value", "encryption_banner_dismissed": True},
        )

    def test_returns_500_on_error(self, authenticated_client, mock_webauthn_services):
        """Should return 500 with generic error on failure."""
        with patch(
            "presentation.web.blueprints.webauthn.get_user_settings_service",
            side_effect=RuntimeError("db error"),
        ):
            response = authenticated_client.post("/api/encryption/dismiss-banner")

        assert response.status_code == 500
        data = response.get_json()
        assert data["success"] is False
        assert "db error" not in data["error"].lower()


# =========================================================================
# Migration endpoint tests
# =========================================================================


class TestMigrateEncrypt:
    """Tests for /api/encryption/migrate."""

    @pytest.fixture
    def unlocked_client(self, app, mock_webauthn_services):
        """Authenticated client with encryption key set (user is unlocked)."""
        from flask import g as flask_g

        @app.before_request
        def set_encryption_key():
            flask_g.encryption_key = "test-encryption-key-b64"

        with patch(
            "presentation.web.decorators.get_session_datasource",
        ) as mock_ds_factory, patch(
            "presentation.web.decorators._check_onboarding_required",
            return_value=None,
        ):
            from datetime import datetime, timedelta, timezone

            from domain.entities.session import Session

            mock_ds = MagicMock()
            valid_session = Session(
                session_token="valid_test_token",
                user_id="test@example.com",
                expiration=datetime.now(timezone.utc) + timedelta(days=7),
                user_profile={"user_name": "Test User", "user_picture": ""},
                created_at=datetime.now(timezone.utc),
            )
            mock_ds.get_session.side_effect = lambda token: (
                valid_session if token == "valid_test_token" else None
            )
            mock_ds_factory.return_value = mock_ds

            client = app.test_client()
            client.set_cookie("session_token", "valid_test_token")
            yield client

    def test_returns_400_without_encryption_key(self, authenticated_client, mock_webauthn_services):
        """Migrate should fail if user is not unlocked (no encryption key)."""
        response = authenticated_client.post("/api/encryption/migrate")
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False
        assert "not available" in data["error"].lower()

    def test_migrates_transactions(self, unlocked_client, mock_webauthn_services):
        """Migrate should encrypt plaintext transactions."""
        mock_enc_svc = mock_webauthn_services["encryption_service"]
        mock_enc_svc.migrate_to_encrypted.return_value = 5

        unlocked_client.set_cookie("session_token", "valid_test_token")
        response = unlocked_client.post("/api/encryption/migrate")

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["transactions_migrated"] == 5
        mock_enc_svc.migrate_to_encrypted.assert_called_once_with("valid_test_token")

    def test_migrate_called_even_with_zero_transactions(
        self, unlocked_client, mock_webauthn_services
    ):
        """migrate_to_encrypted should be called even if there are no transactions."""
        mock_enc_svc = mock_webauthn_services["encryption_service"]
        mock_enc_svc.migrate_to_encrypted.return_value = 0

        unlocked_client.set_cookie("session_token", "valid_test_token")
        response = unlocked_client.post("/api/encryption/migrate")

        assert response.status_code == 200
        data = response.get_json()
        assert data["transactions_migrated"] == 0
        mock_enc_svc.migrate_to_encrypted.assert_called_once()


# =========================================================================
# Decrypt-all endpoint tests
# =========================================================================


class TestDecryptAll:
    """Tests for /api/encryption/decrypt-all."""

    @pytest.fixture
    def unlocked_client(self, app, mock_webauthn_services):
        """Authenticated client with encryption key set (user is unlocked)."""
        from flask import g as flask_g

        @app.before_request
        def set_encryption_key():
            flask_g.encryption_key = "test-encryption-key-b64"

        with patch(
            "presentation.web.decorators.get_session_datasource",
        ) as mock_ds_factory, patch(
            "presentation.web.decorators._check_onboarding_required",
            return_value=None,
        ):
            from datetime import datetime, timedelta, timezone

            from domain.entities.session import Session

            mock_ds = MagicMock()
            valid_session = Session(
                session_token="valid_test_token",
                user_id="test@example.com",
                expiration=datetime.now(timezone.utc) + timedelta(days=7),
                user_profile={"user_name": "Test User", "user_picture": ""},
                created_at=datetime.now(timezone.utc),
            )
            mock_ds.get_session.side_effect = lambda token: (
                valid_session if token == "valid_test_token" else None
            )
            mock_ds_factory.return_value = mock_ds

            client = app.test_client()
            client.set_cookie("session_token", "valid_test_token")
            yield client

    def test_returns_400_without_encryption_key(self, authenticated_client, mock_webauthn_services):
        """Decrypt-all should fail if user is not unlocked."""
        response = authenticated_client.post("/api/encryption/decrypt-all")
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False

    def test_decrypts_transactions(self, unlocked_client, mock_webauthn_services):
        """Should decrypt all transactions."""
        mock_enc_svc = mock_webauthn_services["encryption_service"]
        mock_enc_svc.migrate_to_plaintext.return_value = 7

        unlocked_client.set_cookie("session_token", "valid_test_token")
        response = unlocked_client.post("/api/encryption/decrypt-all")

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["transactions_decrypted"] == 7
        mock_enc_svc.migrate_to_plaintext.assert_called_once_with("valid_test_token")


# =========================================================================
# Middleware tests
# =========================================================================


class TestEncryptionMiddleware:
    """Tests for the encryption key extraction middleware."""

    @pytest.fixture(scope="class")
    def middleware_app(self):
        """Use the real app with its actual encryption middleware."""
        from unittest.mock import patch

        from presentation.web.app import create_app

        # Mock init_extensions to skip loading the ML model and background
        # threads — none of which are needed to test the request middleware.
        with patch("presentation.web.extensions.init_extensions"):
            app = create_app()
        app.config["TESTING"] = True
        return app

    def test_extracts_key_from_header(self, middleware_app):
        """Middleware should extract key from X-Encryption-Key header."""
        from flask import g

        with middleware_app.test_request_context(
            "/",
            headers={"X-Encryption-Key": "test-key-123"},
        ):
            middleware_app.preprocess_request()
            assert g.get("encryption_key") == "test-key-123"

    def test_extracts_key_from_cookie(self, middleware_app):
        """Middleware should extract key from encryption_key cookie."""
        from flask import g

        client = middleware_app.test_client()
        client.set_cookie("encryption_key", "cookie-key-456")

        with middleware_app.test_request_context(
            "/some-page",
            headers={"Cookie": "encryption_key=cookie-key-456"},
        ):
            middleware_app.preprocess_request()
            assert g.get("encryption_key") == "cookie-key-456"

    def test_extracts_url_encoded_key_from_cookie(self, middleware_app):
        """Middleware should URL-decode cookie value (JS uses encodeURIComponent)."""
        from flask import g

        # Base64 key with padding: abc+def/ghi== → encodeURIComponent → abc%2Bdef%2Fghi%3D%3D
        with middleware_app.test_request_context(
            "/some-page",
            headers={"Cookie": "encryption_key=abc%2Bdef%2Fghi%3D%3D"},
        ):
            middleware_app.preprocess_request()
            assert g.get("encryption_key") == "abc+def/ghi=="

    def test_header_takes_precedence_over_cookie(self, middleware_app):
        """Header should take precedence when both are present."""
        from flask import g

        with middleware_app.test_request_context(
            "/",
            headers={
                "X-Encryption-Key": "header-key",
                "Cookie": "encryption_key=cookie-key",
            },
        ):
            middleware_app.preprocess_request()
            assert g.get("encryption_key") == "header-key"

    def test_extracts_key_on_login_routes(self, middleware_app):
        """Login routes should extract encryption key so /login/callback can encrypt sessions."""
        from flask import g

        with middleware_app.test_request_context(
            "/login/callback",
            headers={"Cookie": "encryption_key=my-dek-key"},
        ):
            middleware_app.preprocess_request()
            assert g.get("encryption_key") == "my-dek-key"

    def test_skips_static_endpoints(self, middleware_app):
        """Middleware should skip /static/ paths."""
        from flask import g

        with middleware_app.test_request_context("/static/css/main.css"):
            middleware_app.preprocess_request()
            assert g.get("encryption_key") is None

    def test_skips_webauthn_endpoints(self, middleware_app):
        """Middleware should skip /api/webauthn/ paths."""
        from flask import g

        with middleware_app.test_request_context("/api/webauthn/register/options"):
            middleware_app.preprocess_request()
            assert g.get("encryption_key") is None

    def test_no_key_sets_none(self, middleware_app):
        """When no key is provided, g.encryption_key should be None."""
        from flask import g

        with middleware_app.test_request_context("/"):
            middleware_app.preprocess_request()
            assert g.get("encryption_key") is None

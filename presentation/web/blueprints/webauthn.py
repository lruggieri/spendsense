"""
WebAuthn blueprint.

Handles passkey registration, authentication with PRF extension,
and encryption key management for end-to-end encryption.
"""

import base64
import ipaddress
import json
import logging
import os

from flask import Blueprint, g, jsonify, render_template, request, session
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from presentation.web.decorators import login_required
from presentation.web.utils import get_encryption_service, get_user_settings_service

logger = logging.getLogger(__name__)

webauthn_bp = Blueprint("webauthn", __name__)


def _b64url_encode(data: bytes) -> str:
    """Encode bytes to base64url (no padding), matching the client-side encoding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    """Decode base64url string (with or without padding) to bytes."""
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


def _is_ip_address(hostname: str) -> bool:
    """Check if a hostname is an IP address (v4 or v6)."""
    try:
        ipaddress.ip_address(hostname.strip("[]"))
        return True
    except ValueError:
        return False


def _get_rp_id() -> str:
    """Get the WebAuthn Relying Party ID from environment or current request host."""
    env_rp_id = os.environ.get("WEBAUTHN_RP_ID")
    if env_rp_id:
        return env_rp_id
    # Derive from request hostname (strip port)
    return request.host.split(":")[0]


def _get_rp_name() -> str:
    """Get the WebAuthn Relying Party name."""
    return os.environ.get("WEBAUTHN_RP_NAME", "SpendSense")


def _get_origin() -> str:
    """Get the expected WebAuthn origin from the current request."""
    return request.host_url.rstrip("/")


# =========================================================================
# Registration
# =========================================================================


@webauthn_bp.route("/api/webauthn/register/options")
@login_required
def register_options():
    """Generate WebAuthn registration options for passkey creation."""
    hostname = request.host.split(":")[0]
    if _is_ip_address(hostname):
        return (
            jsonify(
                {
                    "success": False,
                    "error": f"WebAuthn requires a domain name, not an IP address. "
                    f'Use http://localhost:{request.host.split(":")[-1]} instead of '
                    f"http://{request.host}",
                }
            ),
            400,
        )

    user_id = request.user_id
    encryption_service = get_encryption_service()

    # Get existing credentials to exclude
    existing_creds = encryption_service.get_credentials_for_user(user_id)
    exclude_credentials = [
        PublicKeyCredentialDescriptor(id=_b64url_decode(c["credential_id"])) for c in existing_creds
    ]

    options = generate_registration_options(
        rp_id=_get_rp_id(),
        rp_name=_get_rp_name(),
        user_id=user_id.encode("utf-8"),
        user_name=user_id,
        user_display_name=getattr(request, "user_name", user_id),
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=exclude_credentials,
    )

    # Store challenge in session for verification
    options_json = json.loads(options_to_json(options))
    session["webauthn_register_challenge"] = options_json["challenge"]

    # Inject PRF extension into the options for the client
    options_json["extensions"] = {"prf": {}}

    return jsonify(options_json)


@webauthn_bp.route("/api/webauthn/register/verify", methods=["POST"])
@login_required
def register_verify():
    """Verify WebAuthn registration response and set up encryption."""
    user_id = request.user_id
    data = request.get_json()

    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400

    challenge = session.pop("webauthn_register_challenge", None)
    if not challenge:
        return jsonify({"success": False, "error": "No registration challenge found"}), 400

    try:
        credential = verify_registration_response(
            credential=data.get("credential", {}),
            expected_challenge=_b64url_decode(challenge),
            expected_rp_id=_get_rp_id(),
            expected_origin=_get_origin(),
            require_user_verification=True,
        )
    except Exception as e:
        logger.warning(f"WebAuthn registration verification failed: {e}")
        return jsonify({"success": False, "error": "Registration verification failed"}), 400

    credential_id_b64 = _b64url_encode(credential.credential_id)

    # Store the WebAuthn credential
    encryption_service = get_encryption_service()
    encryption_service.store_credential(
        user_id=user_id,
        credential_id=credential_id_b64,
        public_key=credential.credential_public_key,
        sign_count=credential.sign_count,
        device_name=data.get("deviceName"),
    )

    # If KEK is provided, set up encryption
    kek_b64 = data.get("kek")
    prf_salt = data.get("prfSalt")
    existing_dek = data.get("existingDek")
    dek_b64 = None

    if kek_b64 and prf_salt:
        if encryption_service.has_encryption(user_id):
            if not existing_dek:
                # User has encryption but isn't unlocked — can't wrap without the DEK
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "Unlock your existing passkey first before adding another",
                        }
                    ),
                    400,
                )
            # Adding another passkey — wrap the existing DEK with the new KEK
            encryption_service.add_passkey_wrapper(
                user_id=user_id,
                credential_id=credential_id_b64,
                dek_b64=existing_dek,
                kek_b64=kek_b64,
                prf_salt=prf_salt,
            )
            dek_b64 = existing_dek
        else:
            # First passkey — generate a new DEK
            dek_b64 = encryption_service.setup_encryption(
                user_id=user_id,
                credential_id=credential_id_b64,
                kek_b64=kek_b64,
                prf_salt=prf_salt,
            )

    return jsonify(
        {
            "success": True,
            "credentialId": credential_id_b64,
            "dek": dek_b64,
        }
    )


# =========================================================================
# Authentication
# =========================================================================


@webauthn_bp.route("/api/webauthn/authenticate/options")
@login_required
def authenticate_options():
    """Generate WebAuthn authentication options with PRF salt."""
    hostname = request.host.split(":")[0]
    if _is_ip_address(hostname):
        return (
            jsonify(
                {
                    "success": False,
                    "error": f"WebAuthn requires a domain name, not an IP address. "
                    f'Use http://localhost:{request.host.split(":")[-1]} instead of '
                    f"http://{request.host}",
                }
            ),
            400,
        )

    user_id = request.user_id
    encryption_service = get_encryption_service()

    # Get user's registered credentials
    credentials = encryption_service.get_credentials_for_user(user_id)
    if not credentials:
        return jsonify({"success": False, "error": "No passkeys registered"}), 404

    allow_credentials = [
        PublicKeyCredentialDescriptor(id=_b64url_decode(c["credential_id"])) for c in credentials
    ]

    options = generate_authentication_options(
        rp_id=_get_rp_id(),
        allow_credentials=allow_credentials,
        user_verification=UserVerificationRequirement.REQUIRED,
    )

    options_json = json.loads(options_to_json(options))
    session["webauthn_auth_challenge"] = options_json["challenge"]

    # Inject PRF extension with salts for each credential
    prf_salts = {}
    for cred in credentials:
        salt = encryption_service.get_prf_salt(user_id, cred["credential_id"])
        if salt:
            prf_salts[cred["credential_id"]] = salt

    options_json["extensions"] = {"prf": {}}
    options_json["prfSalts"] = prf_salts

    return jsonify(options_json)


@webauthn_bp.route("/api/webauthn/authenticate/verify", methods=["POST"])
@login_required
def authenticate_verify():
    """Verify WebAuthn authentication response."""
    request.user_id
    data = request.get_json()

    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400

    challenge = session.pop("webauthn_auth_challenge", None)
    if not challenge:
        return jsonify({"success": False, "error": "No authentication challenge found"}), 400

    credential_id_b64 = data.get("credentialId")
    if not credential_id_b64:
        return jsonify({"success": False, "error": "No credential ID provided"}), 400

    encryption_service = get_encryption_service()
    stored_cred = encryption_service.get_credential(credential_id_b64)
    if not stored_cred:
        return jsonify({"success": False, "error": "Unknown credential"}), 400

    try:
        auth_verification = verify_authentication_response(
            credential=data.get("credential", {}),
            expected_challenge=_b64url_decode(challenge),
            expected_rp_id=_get_rp_id(),
            expected_origin=_get_origin(),
            credential_public_key=stored_cred["public_key"],
            credential_current_sign_count=stored_cred["sign_count"],
            require_user_verification=True,
        )
    except Exception as e:
        logger.warning(f"WebAuthn authentication verification failed: {e}")
        return jsonify({"success": False, "error": "Authentication verification failed"}), 400

    # Update sign count
    encryption_service.update_sign_count(
        credential_id_b64,
        auth_verification.new_sign_count,
    )

    return jsonify({"success": True})


# =========================================================================
# DEK Management
# =========================================================================


@webauthn_bp.route("/api/encryption/unwrap-dek", methods=["POST"])
@login_required
def unwrap_dek():
    """Receive KEK from client, unwrap and return DEK."""
    user_id = request.user_id
    data = request.get_json()

    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400

    kek_b64 = data.get("kek")
    credential_id = data.get("credentialId")

    if not kek_b64 or not credential_id:
        return jsonify({"success": False, "error": "Missing kek or credentialId"}), 400

    encryption_service = get_encryption_service()

    try:
        dek_b64 = encryption_service.unwrap_dek(user_id, credential_id, kek_b64)
    except Exception as e:
        logger.warning(f"DEK unwrap failed for user {user_id}: {e}")
        return jsonify({"success": False, "error": "Failed to unwrap encryption key"}), 400

    return jsonify({"success": True, "dek": dek_b64})


# =========================================================================
# Pages
# =========================================================================


@webauthn_bp.route("/api/encryption/dismiss-banner", methods=["POST"])
@login_required
def dismiss_encryption_banner():
    """Dismiss the encryption setup banner."""
    try:
        settings_service = get_user_settings_service()
        settings = settings_service.get_user_settings()
        browser_settings = settings.browser_settings or {}
        browser_settings["encryption_banner_dismissed"] = True
        settings_service.update_user_settings(browser_settings=browser_settings)
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error dismissing encryption banner: {e}", exc_info=True)
        return jsonify({"success": False, "error": "Internal error"}), 500


@webauthn_bp.route("/api/encryption/migrate", methods=["POST"])
@login_required
def migrate_encrypt():
    """Encrypt all plaintext transactions."""
    encryption_key = getattr(g, "encryption_key", None)
    if not encryption_key:
        return jsonify({"success": False, "error": "Encryption key not available"}), 400

    try:
        encryption_service = get_encryption_service()
        session_token = request.cookies.get("session_token")
        count = encryption_service.migrate_to_encrypted(session_token)
        return jsonify({"success": True, "transactions_migrated": count})
    except Exception as e:
        logger.error(f"Encryption migration failed: {e}", exc_info=True)
        return jsonify({"success": False, "error": "Encryption migration failed"}), 500


@webauthn_bp.route("/api/encryption/decrypt-all", methods=["POST"])
@login_required
def decrypt_all():
    """Revert all encrypted data back to plaintext (escape hatch)."""
    encryption_key = getattr(g, "encryption_key", None)
    if not encryption_key:
        return jsonify({"success": False, "error": "Encryption key required to decrypt"}), 400

    try:
        encryption_service = get_encryption_service()
        session_token = request.cookies.get("session_token")
        count = encryption_service.migrate_to_plaintext(session_token)
        return jsonify({"success": True, "transactions_decrypted": count})
    except Exception as e:
        logger.error(f"Decryption migration failed: {e}", exc_info=True)
        return jsonify({"success": False, "error": "Decryption failed"}), 500


@webauthn_bp.route("/passkey/setup")
@login_required
def passkey_setup():
    """Passkey setup page for enabling encryption."""
    encryption_service = get_encryption_service()
    has_encryption = encryption_service.has_encryption(request.user_id)
    credentials = encryption_service.get_credentials_for_user(request.user_id)

    return render_template(
        "passkey_setup.html",
        has_encryption=has_encryption,
        credentials=credentials,
    )


@webauthn_bp.route("/passkey/login")
@login_required
def passkey_login():
    """Passkey authentication page for unlocking encrypted data."""
    return render_template("passkey_login.html")

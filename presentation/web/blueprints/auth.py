"""
Authentication blueprint.

Handles login, logout, and OAuth callback routes.
"""

import base64
import json
import logging
from datetime import datetime, timedelta, timezone

from flask import (
    Blueprint,
    flash,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from google_auth_oauthlib.flow import Flow

from presentation.web.blueprints.onboarding import (
    _get_onboarding_status_for_user,
    initialize_onboarding,
)
from presentation.web.extensions import (
    SCOPES,
    get_allowed_emails_list,
    get_credentials_loader_instance,
    get_session_datasource,
)

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login")
def login():
    """Display login page."""
    session_datasource = get_session_datasource()

    # If already logged in, redirect to home
    session_token = request.cookies.get("session_token")
    if session_token:
        session_data = session_datasource.get_session(session_token)
        if session_data:
            return redirect(url_for("main.index"))

    # Debug: Show what redirect URI will be used
    debug_redirect_uri = url_for("auth.login_callback", _external=True)
    logger.debug(f"Generated redirect URI: {debug_redirect_uri}")

    return render_template("login.html")


@auth_bp.route("/login/start")
def login_start():
    """Initiate Google OAuth login flow."""
    credentials_loader = get_credentials_loader_instance()

    try:
        # Create flow instance with updated scopes
        client_config = credentials_loader.get_credentials()
        flow = Flow.from_client_config(
            client_config,
            scopes=SCOPES,
            redirect_uri=url_for("auth.login_callback", _external=True),
        )

        # Generate authorization URL
        authorization_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",  # Force consent screen to get refresh token
        )

        # Store state in Flask session for verification
        session["oauth_state"] = state
        session["oauth_flow"] = "login"  # Mark this as login flow

        return redirect(authorization_url)
    except Exception as e:
        flash(f"Error initiating login: {str(e)}", "error")
        return redirect(url_for("auth.login"))


@auth_bp.route("/login/callback")
def login_callback():
    """Handle OAuth callback and create session."""
    session_datasource = get_session_datasource()
    credentials_loader = get_credentials_loader_instance()
    allowed_emails = get_allowed_emails_list()

    try:
        # Verify state
        state = session.get("oauth_state")
        if not state:
            flash("Invalid OAuth state", "error")
            return redirect(url_for("auth.login"))

        # Verify this is a login flow
        if session.get("oauth_flow") != "login":
            flash("Invalid OAuth flow", "error")
            return redirect(url_for("auth.login"))

        # Create flow instance
        client_config = credentials_loader.get_credentials()
        flow = Flow.from_client_config(
            client_config,
            scopes=SCOPES,
            state=state,
            redirect_uri=url_for("auth.login_callback", _external=True),
        )

        # Fetch token using the authorization response
        flow.fetch_token(authorization_response=request.url)

        # Get credentials
        credentials = flow.credentials

        # Decode ID token (JWT) to get user info
        id_token = credentials.id_token
        if not id_token:
            flash("Failed to retrieve ID token", "error")
            return redirect(url_for("auth.login"))

        # Decode JWT manually (it's base64-encoded JSON)
        # JWT format: header.payload.signature
        # We only need the payload (middle part)
        try:
            # Split JWT into parts
            parts = id_token.split(".")
            if len(parts) != 3:
                raise ValueError("Invalid JWT format")

            # Decode payload (add padding if needed)
            payload = parts[1]
            # Add padding if necessary
            padding = 4 - (len(payload) % 4)
            if padding != 4:
                payload += "=" * padding

            decoded_bytes = base64.urlsafe_b64decode(payload)
            decoded_token = json.loads(decoded_bytes)

            user_email = decoded_token.get("email")
            user_name = decoded_token.get("name", "")  # Full name
            user_picture = decoded_token.get("picture", "")  # Profile picture URL
            token_exp = decoded_token.get("exp")  # Unix timestamp

            if not user_email:
                flash("Failed to retrieve user email from token", "error")
                return redirect(url_for("auth.login"))

            # Check if email is allowed (if access control is enabled)
            if allowed_emails is not None and user_email.lower() not in allowed_emails:
                logger.warning(f"Access denied for email: {user_email}")
                return (
                    render_template(
                        "error.html",
                        error_code=403,
                        error_message="Access Denied",
                        error_details=f"Your email address ({user_email}) is not authorized to access this application.",
                    ),
                    403,
                )

            # Google ID tokens (JWT) typically expire in 1 hour
            # Extract the actual JWT expiration for reference
            if token_exp:
                token_expiration = datetime.fromtimestamp(token_exp)
            else:
                token_expiration = datetime.now(timezone.utc) + timedelta(hours=1)

            # Session cookie expiration: We use 7 days for better UX
            # Note: While the JWT expires in ~1 hour, we have a refresh_token that allows
            # us to obtain new access tokens without re-authentication. This means we can
            # maintain a longer session (7 days) while periodically refreshing the access
            # token behind the scenes when needed for Gmail API calls.
            expiration = datetime.now(timezone.utc) + timedelta(days=7)

        except Exception as e:
            flash(f"Failed to decode ID token: {str(e)}", "error")
            return redirect(url_for("auth.login"))

        # Create session in database with user profile only (no OAuth tokens stored server-side)
        session_token = session_datasource.create_session(
            user_id=user_email,
            user_profile={"user_name": user_name, "user_picture": user_picture},
            expiration=expiration,
        )

        # Clear OAuth session data
        session.pop("oauth_state", None)
        session.pop("oauth_flow", None)

        # Determine redirect destination based on onboarding status
        # Temporarily set request.user_id so service factory can work
        request.user_id = user_email
        from presentation.web.utils import get_user_settings_service

        settings_service = get_user_settings_service()
        onboarding_status = _get_onboarding_status_for_user(settings_service)
        if onboarding_status["step"] is None:
            # New user - initialize onboarding
            initialize_onboarding(settings_service)
            redirect_url = url_for("onboarding.step", step_num=1)
        elif onboarding_status["step"] > 0:
            # User in progress - continue from where they left off
            redirect_url = url_for("onboarding.step", step_num=onboarding_status["step"])
        else:
            # Onboarding complete or skipped
            redirect_url = url_for("main.index")

        # Set secure cookie with session token
        response = make_response(redirect(redirect_url))
        response.set_cookie(
            "session_token",
            session_token,
            httponly=True,  # Prevent JavaScript access
            secure=False,  # Set to True in production with HTTPS
            samesite="Lax",
            expires=expiration,
        )

        flash(f"Successfully signed in as {user_email}", "success")
        return response

    except Exception as e:
        flash(f"Login error: {str(e)}", "error")
        return redirect(url_for("auth.login"))


@auth_bp.route("/logout")
def logout():
    """Log out user and clear session."""
    session_datasource = get_session_datasource()
    session_token = request.cookies.get("session_token")

    if session_token:
        # Delete session from database
        session_datasource.delete_session(session_token)

    # Clear cookies and redirect to login
    response = make_response(redirect(url_for("auth.login")))
    response.set_cookie("session_token", "", expires=0)
    response.set_cookie("encryption_key", "", expires=0, path="/")
    flash("Successfully signed out", "success")

    return response

"""
Decorators for the Flask application.

Contains authentication and authorization decorators used across blueprints.
"""

from functools import wraps

from flask import flash, g, make_response, redirect, request, session, url_for

from presentation.web.auth_utils import ONBOARDING_VERSION, needs_onboarding
from presentation.web.extensions import get_session_datasource
from presentation.web.utils import get_user_settings_service


def login_required(f):
    """
    Decorator to protect routes requiring authentication.
    Checks for valid session token in cookies.
    Also enforces onboarding completion for non-onboarding routes.
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        session_datasource = get_session_datasource()
        session_token = request.cookies.get("session_token")

        if not session_token:
            flash("Please sign in to access this page.", "error")
            return redirect(url_for("auth.login"))

        session_data = session_datasource.get_session(session_token)
        if not session_data:
            # Session invalid or expired
            flash("Your session has expired. Please sign in again.", "error")
            response = make_response(redirect(url_for("auth.login")))
            response.set_cookie("session_token", "", expires=0)  # Clear invalid cookie
            return response

        # Store user info in request context for use in routes and templates
        request.user_id = session_data.user_id
        request.session_data = session_data

        # Extract user info from user_profile for template use
        user_profile = session_data.user_profile or {}
        request.user_name = user_profile.get("user_name", session_data.user_id)
        request.user_picture = user_profile.get("user_picture", "")

        # Enforce onboarding completion (skip for onboarding routes and API calls)
        # API calls are skipped because they return JSON - the UI enforcement is sufficient
        if request.blueprint != "onboarding" and not request.path.startswith("/api/"):
            redirect_response = _check_onboarding_required(request.user_id)
            if redirect_response:
                return redirect_response

        return f(*args, **kwargs)

    return decorated_function


def _check_onboarding_required(user_id: str):
    """
    Check if user needs to complete onboarding.
    Uses session caching with versioning for performance.

    Returns:
        Redirect response if onboarding needed, None otherwise.
    """
    # Fast path: session cache says onboarding is complete for current version
    if session.get("onboarding_version") == ONBOARDING_VERSION:
        return None

    # Slow path: check database
    # Note: request.user_id is already set by the login_required decorator at this point
    settings_service = get_user_settings_service()
    if needs_onboarding(settings_service):
        return redirect(url_for("onboarding.onboarding_index"))

    # Cache completion in session
    session["onboarding_version"] = ONBOARDING_VERSION
    return None

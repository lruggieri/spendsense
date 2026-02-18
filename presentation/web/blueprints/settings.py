"""
Settings blueprint.

Handles user settings routes including language, currency, and browser settings.
"""

from flask import Blueprint, jsonify, make_response, render_template, request

from presentation.web.decorators import login_required
from presentation.web.utils import get_user_settings_service

settings_bp = Blueprint("settings", __name__)


@settings_bp.route("/settings")
@login_required
def settings():
    """User settings page."""
    settings_service = get_user_settings_service()
    current_settings = settings_service.get_user_settings()

    # Language display names for template
    language_names = {
        "en": "English",
        "es": "Espanol",
        "fr": "Francais",
        "de": "Deutsch",
        "it": "Italiano",
        "pt": "Portugues",
        "ja": "Japanese",
        "zh": "Chinese",
        "ko": "Korean",
        "ru": "Russian",
        "ar": "Arabic",
        "hi": "Hindi",
        "nl": "Nederlands",
        "sv": "Svenska",
        "no": "Norsk",
        "da": "Dansk",
        "fi": "Suomi",
        "pl": "Polski",
        "tr": "Turkce",
        "th": "Thai",
        "vi": "Tieng Viet",
    }

    response = make_response(
        render_template(
            "settings.html",
            current_settings=current_settings,
            language_names=language_names,
            supported_currencies=settings_service.get_supported_currencies(),
        )
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@settings_bp.route("/api/update-settings", methods=["POST"])
@login_required
def update_settings_api():
    """API endpoint to update user settings."""
    data = request.get_json()

    language = data.get("language")  # Entity field name, not DB column
    currency = data.get("currency")  # Entity field name, not DB column

    if not language and not currency:
        return jsonify({"success": False, "error": "No settings provided"})

    settings_service = get_user_settings_service()
    success, error = settings_service.update_user_settings(language=language, currency=currency)

    if success:
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "error": error})


@settings_bp.route("/api/user-settings/browser", methods=["GET"])
@login_required
def get_browser_settings():
    """Get browser-specific settings for current user."""
    settings_service = get_user_settings_service()
    current_settings = settings_service.get_user_settings()
    return jsonify(current_settings.browser_settings or {})


@settings_bp.route("/api/user-settings/browser", methods=["PUT"])
@login_required
def update_browser_settings():
    """Update browser-specific settings for current user."""
    data = request.get_json()
    browser_settings = data.get("browser_settings", {})

    # Validate JSON structure
    if not isinstance(browser_settings, dict):
        return jsonify({"error": "browser_settings must be an object"}), 400

    settings_service = get_user_settings_service()
    current_settings = settings_service.get_user_settings()
    success, error = settings_service.update_user_settings(
        language=current_settings.language,
        currency=current_settings.currency,
        browser_settings=browser_settings,
    )

    if success:
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "error": error}), 500

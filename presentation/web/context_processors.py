"""
Context processors for the Flask application.

Contains functions that inject variables into all templates.
"""

import logging

from flask import g, request

logger = logging.getLogger(__name__)


def register_context_processors(app):
    """
    Register all context processors with the Flask app.

    Args:
        app: Flask application instance
    """

    @app.context_processor
    def inject_user_info():
        """Make user info available to all templates."""
        return {
            "user_name": getattr(request, "user_name", ""),
            "user_picture": getattr(request, "user_picture", ""),
            "user_id": getattr(request, "user_id", ""),
        }

    @app.context_processor
    def inject_onboarding_status():
        """
        Make onboarding status available to all templates.

        Returns dict with:
        - show_onboarding_banner: True if user should see onboarding reminder
        """
        # Banner no longer needed - users must complete onboarding
        # Keeping context processor for backward-compatibility
        return {"show_onboarding_banner": False}

    @app.context_processor
    def inject_encryption_status():
        """
        Make encryption status available to all templates.

        Returns dict with:
        - has_encryption: True if user has encryption set up
        - show_encryption_banner: True if user should see encryption setup banner
        """
        user_id = getattr(request, "user_id", None)
        if not user_id:
            return {}

        try:
            from presentation.web.utils import get_encryption_service, get_user_settings_service

            encryption_service = get_encryption_service()
            encrypted = encryption_service.has_encryption(user_id)

            if encrypted:
                is_unlocked = bool(getattr(g, "encryption_key", None))
                return {
                    "show_encryption_banner": False,
                    "show_unlock_banner": not is_unlocked,
                    "has_encryption": True,
                }

            # Check if banner was dismissed
            settings_service = get_user_settings_service()
            settings = settings_service.get_user_settings()
            browser_settings = settings.browser_settings or {}
            dismissed = browser_settings.get("encryption_banner_dismissed", False)

            return {
                "show_encryption_banner": not dismissed,
                "show_unlock_banner": False,
                "has_encryption": False,
            }
        except Exception:
            logger.debug("Could not determine encryption status", exc_info=True)
            return {
                "show_encryption_banner": False,
                "show_unlock_banner": False,
                "has_encryption": False,
            }

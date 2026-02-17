"""
Authentication utility functions.

Shared utilities for authentication and onboarding checks.
Avoids circular dependencies between decorators and onboarding blueprints.
"""

# Onboarding version - increment when adding new required steps for existing users
ONBOARDING_VERSION = 2


def needs_onboarding(settings_service) -> bool:
    """
    Check if user needs to go through onboarding.

    Returns True if:
    - onboarding_step is None (never started)
    - onboarding_step is > 0 (in progress)

    Returns False if:
    - onboarding_step is 0 (completed or skipped)

    Args:
        settings_service: UserSettingsService instance

    Returns:
        True if user should be redirected to onboarding
    """
    try:
        settings = settings_service.get_user_settings()
        browser_settings = settings.browser_settings or {}
        step = browser_settings.get("onboarding_step", None)

        # None means never started, > 0 means in progress
        if step is None or step > 0:
            return True

        return False
    except Exception:
        # If we can't determine status, assume onboarding needed for safety
        return True

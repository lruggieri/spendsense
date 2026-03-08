"""
Fetchers blueprint.

Handles fetcher configuration routes for LLM-based pattern generation.
"""

import logging

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from config import SUPPORTED_CURRENCIES
from infrastructure.email.fetchers.pattern_parser import parse_transactions_with_patterns
from infrastructure.llm.gemini_provider import GeminiProvider
from infrastructure.rate_limiter import LLMRateLimiter
from presentation.web.decorators import login_required
from presentation.web.utils import (
    get_fetcher_service,
    get_user_settings_service,
)

logger = logging.getLogger(__name__)

fetchers_bp = Blueprint("fetchers", __name__)


@fetchers_bp.route("/settings/fetchers")
@login_required
def fetchers():
    """Display list of all fetchers for the user (shows only enabled versions)."""
    fetcher_service = get_fetcher_service()
    fetchers_data = fetcher_service.get_enabled_fetchers_for_list()

    # Format fetchers for template
    fetchers_list = []
    for f in fetchers_data:
        from_emails = f.from_emails or []
        fetchers_list.append(
            {
                "id": f.id,
                "name": f.name,
                "from_emails": from_emails,
                "from_emails_display": ", ".join(from_emails[:2])
                + ("..." if len(from_emails) > 2 else ""),
                "subject_filter": f.subject_filter or "-",
                "enabled": f.enabled,
                "group_id": f.group_id,
                "version": f.version,
            }
        )

    # Sort alphabetically by name (case-insensitive)
    fetchers_list.sort(key=lambda x: x["name"].lower())

    return render_template("fetchers.html", mode="list", fetchers=fetchers_list)


@fetchers_bp.route("/settings/fetchers/new")
@login_required
def create_fetcher():
    """Create new fetcher configuration."""
    return render_template("fetchers.html", mode="create")


@fetchers_bp.route("/settings/fetchers/<fetcher_id>")
@login_required
def edit_fetcher(fetcher_id):
    """Edit existing fetcher configuration."""
    fetcher_service = get_fetcher_service()
    fetcher = fetcher_service.get_fetcher_by_id(fetcher_id)

    if not fetcher:
        flash("Fetcher not found", "error")
        return redirect(url_for("settings.settings"))

    # Render same template with edit mode
    return render_template("fetchers.html", mode="edit", fetcher=fetcher)


@fetchers_bp.route("/api/fetchers/generate-patterns", methods=["POST"])
@login_required
def api_fetchers_generate_patterns():
    """
    API endpoint to generate fetcher patterns from email text using LLM.

    The client fetches the email body client-side (using the GIS token) and
    POSTs the raw text here. The server passes it to the LLM and returns
    generated patterns. Gmail tokens never reach the server.

    Request JSON:
        {
            "email_texts": ["...", "..."],
            "negate_amount": false
        }

    Response JSON:
        {
            "success": true/false,
            "patterns": {
                "amount_pattern": "...",
                "merchant_pattern": "...",
                "currency_pattern": "..." or null
            },
            "emails_data": [
                {
                    "email_text": "...",
                    "transactions": [
                        {
                            "amount": "1234",
                            "merchant": "Store Name",
                            "currency": "JPY" or null
                        }
                    ]
                }
            ],
            "rate_limit": {
                "remaining": 42,
                "limit": 50
            },
            "error": "..." (only if success=false)
        }
    """
    try:
        # Check rate limit before making LLM call
        user_settings_service = get_user_settings_service()
        rate_limiter = LLMRateLimiter(user_settings_service.datasource)

        allowed, rate_info = rate_limiter.check_rate_limit()
        if not allowed:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Rate limit exceeded. Please try again later.",
                        "rate_limit": rate_info,
                    }
                ),
                429,
            )

        data = request.get_json()
        email_texts = data.get("email_texts", [])
        negate_amount = data.get("negate_amount", False)

        if not email_texts:
            return (
                jsonify({"success": False, "error": "email_texts must be provided"}),
                400,
            )

        _MAX_EMAIL_COUNT = 10
        _MAX_EMAIL_CHARS = 50_000
        if len(email_texts) > _MAX_EMAIL_COUNT:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": f"Too many email examples (max {_MAX_EMAIL_COUNT})",
                    }
                ),
                400,
            )
        for i, text in enumerate(email_texts):
            if len(text) > _MAX_EMAIL_CHARS:
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": f"Email {i + 1} is too long (max {_MAX_EMAIL_CHARS} characters)",
                        }
                    ),
                    400,
                )

        # Combine all email texts with separators for LLM
        combined_email_text = "\n\n===== EMAIL EXAMPLE SEPARATOR =====\n\n".join(email_texts)

        # Generate patterns using LLM (with all examples)
        llm_provider = GeminiProvider()
        patterns = llm_provider.generate_patterns(combined_email_text)

        # Record successful LLM call for rate limiting
        rate_limiter.record_call()

        # Get updated rate limit info for response
        _, rate_info = rate_limiter.check_rate_limit()

        # Parse each email individually with the generated patterns
        emails_data = []
        for email_text in email_texts:
            transactions = parse_transactions_with_patterns(
                email_text,
                patterns["amount_pattern"],
                patterns["merchant_pattern"],
                patterns["currency_pattern"],
                negate_amount,
            )
            emails_data.append({"email_text": email_text, "transactions": transactions})

        return jsonify(
            {
                "success": True,
                "patterns": patterns,
                "emails_data": emails_data,
                "rate_limit": {"remaining": rate_info["remaining"], "limit": rate_info["limit"]},
            }
        )

    except Exception as e:
        logger.error(f"Error generating patterns: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@fetchers_bp.route("/api/supported-currencies", methods=["GET"])
def api_supported_currencies():
    """
    API endpoint to get list of supported currencies.

    Returns:
        JSON with list of currency objects (code, symbol, name)
    """
    try:
        return jsonify({"success": True, "currencies": SUPPORTED_CURRENCIES})
    except Exception as e:
        logger.error(f"Error fetching currencies: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@fetchers_bp.route("/api/fetchers/<fetcher_id>", methods=["GET"])
@login_required
def api_get_fetcher(fetcher_id):
    """Get a single fetcher by ID with user_id verification."""
    try:
        fetcher_service = get_fetcher_service()
        fetcher = fetcher_service.get_fetcher_by_id(fetcher_id)

        if not fetcher:
            return jsonify({"success": False, "error": "Fetcher not found"}), 404

        return jsonify({"success": True, "fetcher": fetcher})
    except Exception as e:
        logger.error(f"Error fetching fetcher: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@fetchers_bp.route("/api/fetchers/<fetcher_id>", methods=["PUT"])
@login_required
def api_update_fetcher(fetcher_id):
    """
    Update a fetcher configuration by creating a new version.

    Uses immutability semantics: creates a new version instead of modifying in place.
    The old version is disabled, and a new version is created with incremented version number.
    """
    try:
        data = request.get_json()
        fetcher_service = get_fetcher_service()

        # Extract fields
        name = data.get("name", "").strip()
        from_emails = data.get("from_emails", [])
        subject_filter = data.get("subject_filter", "").strip()
        amount_pattern = data.get("amount_pattern", "").strip()
        merchant_pattern = data.get("merchant_pattern")
        currency_pattern = data.get("currency_pattern")
        default_currency = data.get("default_currency", "USD")
        negate_amount = data.get("negate_amount", False)

        # Use service to update fetcher (handles validation, versioning, etc.)
        success, error, new_fetcher_id = fetcher_service.update_fetcher(
            fetcher_id=fetcher_id,
            name=name,
            from_emails=from_emails,
            subject_filter=subject_filter,
            amount_pattern=amount_pattern,
            merchant_pattern=merchant_pattern.strip() if merchant_pattern else None,
            currency_pattern=currency_pattern.strip() if currency_pattern else None,
            default_currency=default_currency,
            negate_amount=negate_amount,
        )

        if success:
            # Get the new fetcher to return version info
            new_fetcher = fetcher_service.get_fetcher_by_id(new_fetcher_id)
            logger.info(f"Created new version of fetcher {fetcher_id} -> {new_fetcher_id}")
            return jsonify(
                {
                    "success": True,
                    "fetcher_id": new_fetcher_id,
                    "group_id": new_fetcher.group_id if new_fetcher else None,
                    "version": new_fetcher.version if new_fetcher else None,
                    "message": f'Fetcher updated (version {new_fetcher.version if new_fetcher else "?"})',
                }
            )
        else:
            return jsonify({"success": False, "error": error}), 400

    except Exception as e:
        logger.error(f"Error updating fetcher: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@fetchers_bp.route("/api/fetchers/save", methods=["POST"])
@login_required
def api_save_fetcher():
    """
    API endpoint to save fetcher configuration to database.
    """
    try:
        data = request.get_json()
        fetcher_service = get_fetcher_service()

        # Extract data
        name = data.get("name", "").strip()
        from_emails = data.get("from_emails", [])
        subject_filter = data.get("subject_filter", "").strip()
        amount_pattern = data.get("amount_pattern", "").strip()
        merchant_pattern = data.get("merchant_pattern")
        currency_pattern = data.get("currency_pattern")
        default_currency = data.get("default_currency", "USD")
        negate_amount = data.get("negate_amount", False)

        # Use service to create fetcher (handles validation, UUID, etc.)
        success, error, fetcher_id = fetcher_service.create_fetcher(
            name=name,
            from_emails=from_emails,
            subject_filter=subject_filter,
            amount_pattern=amount_pattern,
            merchant_pattern=merchant_pattern.strip() if merchant_pattern else "",
            currency_pattern=currency_pattern.strip() if currency_pattern else None,
            default_currency=default_currency,
            negate_amount=negate_amount,
        )

        if success:
            logger.info(f"Saved fetcher: {name} (ID: {fetcher_id})")
            return jsonify(
                {
                    "success": True,
                    "fetcher_id": fetcher_id,
                    "group_id": fetcher_id,
                    "version": 1,
                    "message": "Fetcher saved successfully",
                }
            )
        else:
            return jsonify({"success": False, "error": error}), 400

    except Exception as e:
        logger.error(f"Error saving fetcher: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@fetchers_bp.route("/api/fetchers/<fetcher_id>/toggle", methods=["POST"])
@login_required
def api_toggle_fetcher(fetcher_id):
    """
    Toggle fetcher enabled status.

    When enabling a fetcher, disables any other enabled version in the same group
    to ensure only one version per group is enabled at a time.
    """
    try:
        fetcher_service = get_fetcher_service()
        success, error, new_enabled = fetcher_service.toggle_fetcher_enabled(fetcher_id)

        if not success:
            return jsonify({"success": False, "error": error}), 404

        return jsonify({"success": True, "enabled": new_enabled})
    except Exception as e:
        logger.error(f"Error toggling fetcher: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@fetchers_bp.route("/api/fetchers/<fetcher_id>/versions", methods=["GET"])
@login_required
def api_get_fetcher_versions(fetcher_id):
    """Get all versions of a fetcher by its ID (uses the fetcher's group_id)."""
    try:
        fetcher_service = get_fetcher_service()

        # First get the fetcher to find its group_id
        fetcher = fetcher_service.get_fetcher_by_id(fetcher_id)
        if not fetcher:
            return jsonify({"success": False, "error": "Fetcher not found"}), 404

        # Get all versions in this group
        versions = fetcher_service.get_fetcher_versions(fetcher.group_id)

        versions_list = [
            {
                "id": v.id,
                "version": v.version,
                "name": v.name,
                "enabled": v.enabled,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
            for v in versions
        ]

        return jsonify({"success": True, "group_id": fetcher.group_id, "versions": versions_list})
    except Exception as e:
        logger.error(f"Error getting fetcher versions: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

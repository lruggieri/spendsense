"""
Fetchers blueprint.

Handles fetcher configuration routes for LLM-based pattern generation.
"""

import logging

from flask import Blueprint, flash, g, jsonify, redirect, render_template, request, url_for
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from config import SUPPORTED_CURRENCIES
from infrastructure.email.fetchers.pattern_parser import parse_transactions_with_patterns
from infrastructure.email.gmail_utils import get_body_from_message, normalize_gmail_message_id
from infrastructure.llm.gemini_provider import GeminiProvider
from infrastructure.rate_limiter import LLMRateLimiter
from presentation.web.decorators import login_required
from presentation.web.extensions import get_credentials_loader_instance, get_session_datasource
from presentation.web.utils import (
    get_fetcher_service,
    get_user_settings_service,
    refresh_google_token_if_needed,
)

logger = logging.getLogger(__name__)

fetchers_bp = Blueprint("fetchers", __name__)


def _fetch_email_by_id(email_id: str):
    """
    Fetch email text from Gmail using message ID.
    Uses existing Gmail token from user session.

    Args:
        email_id: Gmail message ID (accepts both UI format from URL and API format)

    Returns:
        Email body text or None if fetch fails
    """
    session_datasource = get_session_datasource()
    credentials_loader = get_credentials_loader_instance()

    try:
        # Normalize message ID (converts UI format to API format if needed)
        email_id = normalize_gmail_message_id(email_id)

        # Get user session and credentials
        session_token = request.cookies.get("session_token")
        encryption_key = getattr(g, "encryption_key", None)
        session_data = session_datasource.get_session(session_token, encryption_key=encryption_key)

        if not session_data or not session_data.google_token:
            logger.error("No Google credentials found in session")
            return None

        # Refresh token if needed
        credentials_data = refresh_google_token_if_needed(
            session_token, session_data.google_token, encryption_key=encryption_key
        )

        # Get client config
        client_config = credentials_loader.get_client_config()

        # Build Gmail credentials
        creds = Credentials(
            token=credentials_data["token"],
            refresh_token=credentials_data["refresh_token"],
            token_uri=credentials_data["token_uri"],
            client_id=client_config["client_id"],
            client_secret=client_config["client_secret"],
            scopes=credentials_data["scopes"],
        )

        # Build Gmail service
        gmail_service = build("gmail", "v1", credentials=creds)

        # Fetch message (format='full' to get the full message body)
        message = (
            gmail_service.users().messages().get(userId="me", id=email_id, format="full").execute()
        )

        logger.debug(
            f"Successfully fetched message {email_id}, has payload: {'payload' in message}"
        )

        # Log payload details for debugging
        if message and "payload" in message:
            payload = message["payload"]
            logger.debug(f"Payload mimeType: {payload.get('mimeType')}")
            logger.debug(f"Payload has 'parts': {'parts' in payload}")
            logger.debug(f"Payload body has 'data': {'data' in payload.get('body', {})}")

            if "parts" in payload:
                logger.debug(f"Number of parts: {len(payload['parts'])}")
                for i, part in enumerate(payload["parts"]):
                    logger.debug(
                        f"Part {i}: mimeType={part.get('mimeType')}, has_body_data={'data' in part.get('body', {})}"
                    )

        # Extract body text
        body_text = get_body_from_message(message)

        if body_text:
            logger.debug(f"Extracted {len(body_text)} characters from message body")
        else:
            logger.warning(f"Could not extract body text from message {email_id}")
            logger.debug(f"Message structure: {message.keys() if message else 'None'}")
            if message and "payload" in message:
                logger.debug(f"Payload structure: {message['payload'].keys()}")

        return body_text

    except Exception as e:
        logger.error(f"Error fetching email {email_id}: {e}", exc_info=True)
        return None


def _fetch_emails_with_filters(from_emails, subject_filter="", limit=10):
    """
    Fetch emails from Gmail using search filters.

    Args:
        from_emails: List of email addresses to filter by
        subject_filter: Optional subject line filter
        limit: Maximum number of emails to fetch (default 10)

    Returns:
        List of (email_id, email_body_text) tuples
    """
    session_datasource = get_session_datasource()
    credentials_loader = get_credentials_loader_instance()

    try:
        # Get Gmail service
        session_token = request.cookies.get("session_token")
        if not session_token:
            logger.error("No session token found")
            return []

        encryption_key = getattr(g, "encryption_key", None)
        session_data = session_datasource.get_session(session_token, encryption_key=encryption_key)
        if not session_data or not session_data.google_token:
            logger.error("No Google credentials found in session")
            return []

        # Refresh token if needed
        credentials_data = refresh_google_token_if_needed(
            session_token, session_data.google_token, encryption_key=encryption_key
        )

        # Get client config
        client_config = credentials_loader.get_client_config()

        # Build Gmail credentials
        creds = Credentials(
            token=credentials_data["token"],
            refresh_token=credentials_data["refresh_token"],
            token_uri=credentials_data["token_uri"],
            client_id=client_config["client_id"],
            client_secret=client_config["client_secret"],
            scopes=credentials_data["scopes"],
        )

        # Build Gmail service
        gmail_service = build("gmail", "v1", credentials=creds)

        # Build query
        query_parts = []
        if len(from_emails) == 1:
            query_parts.append(f"from:{from_emails[0]}")
        else:
            from_clause = " OR ".join(from_emails)
            query_parts.append(f"from:({from_clause})")

        if subject_filter:
            query_parts.append(f"subject:{subject_filter}")

        query = " ".join(query_parts)

        logger.info(f"Gmail search query: {query}")

        # Search messages
        results = (
            gmail_service.users().messages().list(userId="me", q=query, maxResults=limit).execute()
        )

        messages = results.get("messages", [])
        logger.info(f"Found {len(messages)} emails")

        # Fetch full message bodies
        email_data = []
        for msg in messages:
            message_detail = (
                gmail_service.users()
                .messages()
                .get(userId="me", id=msg["id"], format="full")
                .execute()
            )

            body_text = get_body_from_message(message_detail)
            if body_text:
                email_data.append((msg["id"], body_text))

        return email_data

    except Exception as e:
        logger.error(f"Error fetching emails with filters: {e}", exc_info=True)
        return []


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


@fetchers_bp.route("/api/test-fetcher", methods=["POST"])
@login_required
def api_test_fetcher():
    """
    API endpoint to test LLM-generated fetcher patterns.

    Request JSON:
        {
            "email_texts": ["...", "..."], (optional if email_ids provided)
            "email_ids": ["...", "..."] (optional if email_texts provided)
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
        email_ids = data.get("email_ids", [])

        # NEW: Gmail search parameters
        from_emails = data.get("from_emails", [])
        subject_filter = data.get("subject_filter", "")
        limit = data.get("limit", 10)

        # Get negate_amount flag
        negate_amount = data.get("negate_amount", False)

        # Fetch emails
        all_email_texts = []

        # Option 1: Gmail search with filters (NEW)
        if from_emails:
            logger.info(f"Using Gmail search with from_emails: {from_emails}")
            fetched_emails = _fetch_emails_with_filters(from_emails, subject_filter, limit)
            all_email_texts = [text for _, text in fetched_emails]
        # Option 2: Manual email input (existing behavior)
        else:
            if not email_texts and not email_ids:
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "Either email_texts, email_ids, or from_emails must be provided",
                        }
                    ),
                    400,
                )

            all_email_texts = list(email_texts)
            for email_id in email_ids:
                fetched_text = _fetch_email_by_id(email_id)
                if not fetched_text:
                    return (
                        jsonify(
                            {
                                "success": False,
                                "error": f"Failed to fetch email with ID: {email_id}",
                            }
                        ),
                        404,
                    )
                all_email_texts.append(fetched_text)

        if not all_email_texts:
            return jsonify({"success": False, "error": "No valid email examples found"}), 400

        # Combine all email texts with separators for LLM
        combined_email_text = "\n\n===== EMAIL EXAMPLE SEPARATOR =====\n\n".join(all_email_texts)

        # Generate patterns using LLM (with all examples)
        llm_provider = GeminiProvider()
        patterns = llm_provider.generate_patterns(combined_email_text)

        # Record successful LLM call for rate limiting
        rate_limiter.record_call()

        # Get updated rate limit info for response
        _, rate_info = rate_limiter.check_rate_limit()

        # Parse each email individually with the generated patterns
        emails_data = []
        for email_text in all_email_texts:
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
        logger.error(f"Error testing fetcher: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@fetchers_bp.route("/api/test-patterns", methods=["POST"])
@login_required
def api_test_patterns():
    """
    API endpoint to test existing patterns against new email examples.

    This endpoint receives patterns (amount, merchant, currency) and test emails,
    then parses the emails using the provided patterns WITHOUT regenerating them.
    """
    try:
        data = request.get_json()

        # Extract patterns
        patterns = data.get("patterns", {})
        amount_pattern = patterns.get("amount_pattern")
        merchant_pattern = patterns.get("merchant_pattern")
        currency_pattern = patterns.get("currency_pattern")
        negate_amount = patterns.get("negate_amount", False)

        # Extract email data
        email_texts = data.get("email_texts", [])
        email_ids = data.get("email_ids", [])

        # NEW: Gmail search parameters
        from_emails = data.get("from_emails", [])
        subject_filter = data.get("subject_filter", "")
        limit = data.get("limit", 10)

        # Validate patterns
        if amount_pattern is None and merchant_pattern is None:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "At least one pattern (amount or merchant) must be provided",
                    }
                ),
                400,
            )

        # Fetch emails
        all_email_texts = []

        # Option 1: Gmail search with filters (NEW)
        if from_emails:
            logger.info(f"Using Gmail search with from_emails: {from_emails}")
            fetched_emails = _fetch_emails_with_filters(from_emails, subject_filter, limit)
            all_email_texts = [text for _, text in fetched_emails]
        # Option 2: Manual email input (existing behavior)
        else:
            if not email_texts and not email_ids:
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "Either email_texts, email_ids, or from_emails must be provided",
                        }
                    ),
                    400,
                )

            all_email_texts = list(email_texts)
            for email_id in email_ids:
                fetched_text = _fetch_email_by_id(email_id)
                if not fetched_text:
                    return (
                        jsonify(
                            {
                                "success": False,
                                "error": f"Failed to fetch email with ID: {email_id}",
                            }
                        ),
                        404,
                    )
                all_email_texts.append(fetched_text)

        if not all_email_texts:
            return jsonify({"success": False, "error": "No valid email examples found"}), 400

        # Parse each test email with the provided patterns
        emails_data = []
        for email_text in all_email_texts:
            transactions = parse_transactions_with_patterns(
                email_text, amount_pattern, merchant_pattern, currency_pattern, negate_amount
            )
            emails_data.append({"email_text": email_text, "transactions": transactions})

        return jsonify({"success": True, "emails_data": emails_data})

    except Exception as e:
        logger.error(f"Error testing patterns: {e}", exc_info=True)
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

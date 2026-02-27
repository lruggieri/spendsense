"""
Gmail blueprint.

Handles Gmail transaction import via client-side OAuth (GIS token).
The server never receives or stores Gmail access tokens; it only receives
already-extracted transaction data from the browser.
"""

import logging
from datetime import datetime, timezone

from flask import Blueprint, jsonify, render_template, request
from uuid6 import uuid7

from config import get_gis_client_id, get_supported_currency_codes, normalize_currency_code
from domain.entities.transaction import Transaction
from domain.services.amount_utils import to_minor_units
from presentation.web.decorators import login_required
from presentation.web.extensions import (
    get_cache_manager,
    get_credentials_loader_instance,
)
from presentation.web.utils import (
    get_fetcher_service,
    get_transaction_service,
)

logger = logging.getLogger(__name__)

gmail_bp = Blueprint("gmail", __name__)

# Maximum number of transactions accepted per /api/email/import call
_MAX_IMPORT_BATCH = 500


def _calculate_fetch_start_date(transaction_service=None) -> str:
    """
    Calculate the start date for Gmail fetch.

    Returns last transaction date if exists, otherwise January 1st of last year.

    Args:
        transaction_service: Optional TransactionService instance.
                            If not provided, creates one from request context.

    Returns:
        Date string in YYYY-MM-DD format
    """
    if transaction_service is None:
        transaction_service = get_transaction_service()

    last_transaction_date = transaction_service.get_last_transaction_date()

    if last_transaction_date:
        # Use last transaction date (included)
        return last_transaction_date.strftime("%Y-%m-%d")
    else:
        # No transactions, use January 1st of last year
        today = datetime.now()
        return datetime(today.year - 1, 1, 1).strftime("%Y-%m-%d")


@gmail_bp.route("/fetch-gmail")
@login_required
def fetch_gmail_page():
    """Display Gmail fetch page."""
    fetcher_service = get_fetcher_service()
    transaction_service = get_transaction_service()

    # Get enabled fetchers using service
    fetchers_data = fetcher_service.get_enabled_fetchers_for_list()

    # Build fetcher objects for template (include enabled for checkbox state)
    fetchers = [
        {
            "id": f.id,
            "name": f.name,
            "description": f'{f.name}: {", ".join(f.from_emails)}',
            "enabled": f.enabled,  # For checkbox default state
        }
        for f in fetchers_data
    ]

    # Sort alphabetically by name (case-insensitive)
    fetchers.sort(key=lambda f: f["name"].lower())

    # Calculate default date based on last transaction date
    default_date = _calculate_fetch_start_date(transaction_service)

    return render_template("fetch_gmail.html", fetchers=fetchers, default_date=default_date)


@gmail_bp.route("/fetch-gmail/progress")
@login_required
def fetch_gmail_progress():
    """Render the import progress page.

    Selected fetcher IDs and after_date travel as URL query params
    (set by the fetch_gmail.html form JS submit handler).
    """
    return render_template("fetch_gmail_progress.html")


# =============================================================================
# REST API endpoints (client-side Gmail OAuth flow)
# =============================================================================


@gmail_bp.route("/api/email/config")
@login_required
def api_email_config():
    """
    Return GIS client_id and enabled fetcher configurations.

    The client uses this to initialise the GIS token client and to know
    which fetchers to run and what patterns to apply client-side.

    Response JSON:
        {
            "client_id": "...",
            "fetchers": [ { id, name, from_emails, subject_filter,
                            amount_pattern, merchant_pattern,
                            currency_pattern, default_currency,
                            negate_amount } ],
            "default_fetch_date": "YYYY-MM-DD"
        }
    """
    credentials_loader = get_credentials_loader_instance()
    fetcher_service = get_fetcher_service()
    transaction_service = get_transaction_service()

    # Prefer a dedicated GIS_CLIENT_ID (Web application type) when set.
    # GIS Token Client requires a Web application OAuth client; Desktop app
    # clients will be rejected by Google with "NATIVE_DESKTOP" error.
    client_id = get_gis_client_id() or credentials_loader.get_client_config()["client_id"]

    fetchers_data = fetcher_service.get_enabled_fetchers()
    fetchers = [
        {
            "id": f.id,
            "name": f.name,
            "from_emails": f.from_emails,
            "subject_filter": f.subject_filter or "",
            "amount_pattern": f.amount_pattern or "",
            "merchant_pattern": f.merchant_pattern,
            "currency_pattern": f.currency_pattern,
            "default_currency": f.default_currency,
            "negate_amount": f.negate_amount,
        }
        for f in fetchers_data
    ]

    default_fetch_date = _calculate_fetch_start_date(transaction_service)

    return jsonify(
        {
            "client_id": client_id,
            "fetchers": fetchers,
            "default_fetch_date": default_fetch_date,
        }
    )


@gmail_bp.route("/api/email/check-imported", methods=["POST"])
@login_required
def api_email_check_imported():
    """
    Deduplication: given a list of Gmail message IDs, return which are already imported.

    Request JSON:  { "mail_ids": ["abc123", "def456", ...] }
    Response JSON: { "imported_ids": ["abc123"] }
    """
    data = request.get_json()
    mail_ids = data.get("mail_ids") if data else None

    if not isinstance(mail_ids, list):
        return jsonify({"error": "mail_ids must be a list"}), 400

    transaction_service = get_transaction_service()
    already_imported = transaction_service.get_processed_mail_ids()

    imported_ids = [mid for mid in mail_ids if mid in already_imported]
    return jsonify({"imported_ids": imported_ids})


@gmail_bp.route("/api/email/import", methods=["POST"])
@login_required
def api_email_import():
    """
    Import extracted transactions.  The browser extracts transaction data
    client-side and POSTs it here; this endpoint validates, converts units,
    and saves to the database.

    Request JSON:
        {
            "transactions": [
                {
                    "fetcher_id": "uuid7",
                    "mail_id":    "abc123",
                    "date_iso":   "2025-01-15T10:30:00Z",
                    "amount_str": "15.99",
                    "description": "Starbucks",
                    "currency":   "USD",
                    "source":     "Chase Credit Card"
                }
            ]
        }
    Response JSON:
        { "imported": 3, "skipped": 0, "warnings": [] }
    """
    data = request.get_json()
    raw_transactions = data.get("transactions") if data else None

    if not isinstance(raw_transactions, list) or len(raw_transactions) == 0:
        return jsonify({"error": "transactions must be a non-empty list"}), 400

    if len(raw_transactions) > _MAX_IMPORT_BATCH:
        return (
            jsonify({"error": f"Batch too large; max {_MAX_IMPORT_BATCH} per request"}),
            400,
        )

    fetcher_service = get_fetcher_service()
    transaction_service = get_transaction_service()
    cache_manager = get_cache_manager()
    supported_currency_codes = get_supported_currency_codes()

    # Pre-load valid fetcher IDs for this user to validate ownership
    enabled_fetchers = {f.id: f for f in fetcher_service.get_enabled_fetchers()}

    transactions = []
    warnings = []
    skipped = 0

    for item in raw_transactions:
        fetcher_id = item.get("fetcher_id")
        fetcher = enabled_fetchers.get(fetcher_id)
        if not fetcher:
            skipped += 1
            warnings.append(f"Unknown or disabled fetcher_id: {fetcher_id}")
            continue

        try:
            date = datetime.fromisoformat(item["date_iso"].replace("Z", "+00:00"))
        except (KeyError, ValueError) as e:
            skipped += 1
            warnings.append(f"Invalid date_iso: {e}")
            continue

        currency = normalize_currency_code(item.get("currency") or fetcher.default_currency)
        if currency not in supported_currency_codes:
            warnings.append(
                f"Unsupported currency {currency}, using {fetcher.default_currency}"
            )
            currency = fetcher.default_currency

        amount_str = item.get("amount_str", "")
        try:
            amount_minor = to_minor_units(amount_str, currency)
        except (ValueError, KeyError) as e:
            skipped += 1
            warnings.append(f"Could not convert amount '{amount_str}': {e}")
            continue

        tx = Transaction(
            id=str(uuid7()),
            date=date,
            amount=amount_minor,
            description=item.get("description") or "Unknown",
            category=None,
            source=item.get("source") or fetcher.name,
            currency=currency,
            category_source=None,
            mail_id=item.get("mail_id"),
            created_at=datetime.now(timezone.utc),
            fetcher_id=fetcher_id,
        )
        transactions.append(tx)

    imported_count = 0
    if transactions:
        imported_count = transaction_service.add_transactions_batch(transactions)
        # Invalidate Redis cache so the next page load re-classifies with new transactions
        from flask import request as flask_request
        cache_manager.invalidate(flask_request.user_id)

    return jsonify(
        {
            "imported": imported_count,
            "skipped": skipped,
            "warnings": warnings,
        }
    )

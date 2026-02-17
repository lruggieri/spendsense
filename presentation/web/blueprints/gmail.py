"""
Gmail blueprint.

Handles Gmail fetch operations including SSE streaming for real-time progress updates.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from flask import Blueprint, Response, render_template, request, redirect, url_for, flash, session, current_app, g
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from uuid6 import uuid7

from config import get_database_path, get_supported_currency_codes
from infrastructure.persistence.sqlite.factory import SQLiteDataSourceFactory
from domain.entities.transaction import Transaction
from presentation.web.decorators import login_required
from presentation.web.extensions import (
    get_session_datasource, get_credentials_loader_instance,
    get_cache_manager
)
from presentation.web.utils import (
    EncryptionKeyRequired,
    refresh_google_token_if_needed,
    get_fetcher_service,
    get_transaction_service
)
from domain.services.amount_utils import to_minor_units
from infrastructure.email.fetchers.db_fetcher_adapter import DBFetcherAdapter


logger = logging.getLogger(__name__)

gmail_bp = Blueprint('gmail', __name__)


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
        return last_transaction_date.strftime('%Y-%m-%d')
    else:
        # No transactions, use January 1st of last year
        today = datetime.now()
        return datetime(today.year - 1, 1, 1).strftime('%Y-%m-%d')


@gmail_bp.route('/fetch-gmail')
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
            'id': f.id,
            'name': f.name,
            'description': f'{f.name}: {", ".join(f.from_emails)}',
            'enabled': f.enabled  # For checkbox default state
        }
        for f in fetchers_data
    ]

    # Sort alphabetically by name (case-insensitive)
    fetchers.sort(key=lambda f: f['name'].lower())

    # Calculate default date based on last transaction date
    default_date = _calculate_fetch_start_date(transaction_service)

    return render_template('fetch_gmail.html', fetchers=fetchers, default_date=default_date)


@gmail_bp.route('/fetch-gmail/start')
@login_required
def fetch_gmail_start():
    """Start Gmail fetch using stored session credentials."""
    transaction_service = get_transaction_service()

    # Calculate fallback date based on last transaction date if not provided
    fallback_date = _calculate_fetch_start_date(transaction_service) if not request.args.get('after_date') else '2025-06-01'

    # Store fetch parameters in Flask session
    session['after_date'] = request.args.get('after_date', fallback_date)

    # Store selected fetchers (if any)
    selected_fetchers = request.args.getlist('fetchers')
    if selected_fetchers:
        session['selected_fetchers'] = selected_fetchers
    else:
        # If none selected, use all
        session['selected_fetchers'] = None

    # Redirect directly to progress page - credentials already available from login
    return render_template('fetch_gmail_progress.html')


@gmail_bp.route('/fetch-gmail/execute-stream')
@login_required
def fetch_gmail_execute_stream():
    """Execute Gmail fetch with real-time progress updates via SSE."""
    session_datasource = get_session_datasource()
    credentials_loader = get_credentials_loader_instance()
    cache_manager = get_cache_manager()

    # Extract all data BEFORE entering generator (request context won't be available in generator)
    # Get credentials from session datasource instead of Flask session
    session_token = request.cookies.get('session_token')
    encryption_key = getattr(g, 'encryption_key', None)
    session_data = session_datasource.get_session(session_token, encryption_key=encryption_key)

    if not session_data:
        flash('Session expired. Please log in again.', 'error')
        return redirect(url_for('auth.login'))

    # Extract user_id before entering generator
    user_id = session_data.user_id

    # Refresh access token if needed (automatically updates database)
    try:
        credentials_data = refresh_google_token_if_needed(session_token, session_data.google_token, encryption_key=encryption_key)
    except EncryptionKeyRequired:
        if encryption_key:
            msg = 'Could not decrypt credentials. Try logging out and back in.'
        else:
            msg = 'Your data is encrypted. Unlock with your passkey first.'
        def locked_error():
            yield f"data: {json.dumps({'status': 'error', 'message': msg})}\n\n"
        return Response(locked_error(), mimetype='text/event-stream')

    # Calculate fallback date based on last transaction date (defensive fallback)
    fallback_date = _calculate_fetch_start_date(user_id) if 'after_date' not in session else '2025-06-01'

    after_date = session.get('after_date', fallback_date)
    selected_fetchers_list = session.get('selected_fetchers', None)

    # Capture encryption key before entering generator (g won't be available)
    encryption_key = getattr(g, 'encryption_key', None)

    def generate():
        """Generator function for server-sent events."""
        try:
            yield f"data: {json.dumps({'status': 'starting', 'message': 'Initializing Gmail fetch...'})}\n\n"

            # Check if credentials exist
            if not credentials_data:
                yield f"data: {json.dumps({'status': 'error', 'message': 'No credentials found'})}\n\n"
                return

            yield f"data: {json.dumps({'status': 'progress', 'message': 'Authenticating with Google...'})}\n\n"

            # Load client credentials from config (NOT from database)
            client_config = credentials_loader.get_client_config()
            client_id = client_config['client_id']
            client_secret = client_config['client_secret']

            # Reconstruct credentials from session data + client config
            creds = Credentials(
                token=credentials_data['token'],
                refresh_token=credentials_data['refresh_token'],
                token_uri=credentials_data['token_uri'],
                client_id=client_id,
                client_secret=client_secret,
                scopes=credentials_data['scopes']
            )

            # Initialize datasources directly — inside SSE generator,
            # Flask request context is unavailable so utils.py factories won't work.
            datasource_path = get_database_path()
            factory = SQLiteDataSourceFactory(datasource_path, user_id, encryption_key=encryption_key)
            datasource = factory.get_transaction_datasource()
            settings_datasource = factory.get_user_settings_datasource()

            # Get user's default currency and supported currencies list
            user_settings = settings_datasource.get_settings()
            user_default_currency = user_settings.currency if user_settings else 'JPY'
            supported_currency_codes = get_supported_currency_codes()

            yield f"data: {json.dumps({'status': 'progress', 'message': 'Building Gmail service...'})}\n\n"

            # Build Gmail service
            gmail_service = build("gmail", "v1", credentials=creds)

            results = []

            # Get fetchers from database
            fetcher_datasource = factory.get_fetcher_datasource()

            if selected_fetchers_list:
                # Get selected fetchers by ID
                db_fetchers = []
                for fetcher_id in selected_fetchers_list:
                    fetcher = fetcher_datasource.get_fetcher_by_id(fetcher_id)
                    if fetcher and fetcher.enabled:
                        db_fetchers.append(fetcher)
                fetchers = [DBFetcherAdapter(f) for f in db_fetchers]
            else:
                # Get all enabled fetchers
                db_fetchers = fetcher_datasource.get_enabled_fetchers()
                fetchers = [DBFetcherAdapter(f) for f in db_fetchers]

            yield f"data: {json.dumps({'status': 'progress', 'message': f'Found {len(fetchers)} fetcher(s) to process'})}\n\n"

            # Helper function to fetch from Gmail using a fetcher
            def fetch_with_fetcher(fetcher):
                yield f"data: {json.dumps({'status': 'progress', 'message': f'Processing {fetcher.name}...', 'source': fetcher.name})}\n\n"

                processed_mail_ids = datasource.get_processed_mail_ids()  # Check globally, not per-source
                mail_filter = fetcher.get_gmail_filter(after_date)

                yield f"data: {json.dumps({'status': 'progress', 'message': f'Querying Gmail for {fetcher.name} messages...', 'source': fetcher.name})}\n\n"

                all_messages = []
                page_token = None

                while True:
                    iteration_messages = gmail_service.users().messages().list(
                        userId="me",
                        q=mail_filter,
                        pageToken=page_token,
                    ).execute()

                    if "messages" in iteration_messages:
                        all_messages.extend(iteration_messages["messages"])
                        yield f"data: {json.dumps({'status': 'progress', 'message': f'Found {len(all_messages)} messages from {fetcher.name}...', 'source': fetcher.name})}\n\n"

                    page_token = iteration_messages.get("nextPageToken", None)
                    if not page_token:
                        break

                if not all_messages:
                    yield f"data: {json.dumps({'status': 'progress', 'message': f'No messages found for {fetcher.name}', 'source': fetcher.name})}\n\n"
                    return {"source": fetcher.name, "total": 0, "new": 0, "written": 0}

                new_messages = [msg for msg in all_messages if msg["id"] not in processed_mail_ids]
                yield f"data: {json.dumps({'status': 'progress', 'message': f'{len(new_messages)} new messages to process for {fetcher.name}', 'source': fetcher.name})}\n\n"

                # Collect new transactions with concurrent message fetching
                new_transactions = []

                def fetch_single_message(msg, credentials):
                    """Fetch a single message detail from Gmail API with thread-local service."""
                    # Each thread creates its own Gmail service to avoid SSL/connection issues
                    thread_service = build("gmail", "v1", credentials=credentials)
                    return thread_service.users().messages().get(userId="me", id=msg["id"]).execute()

                # Use ThreadPoolExecutor to fetch messages concurrently
                # Limit to 20 concurrent requests to respect Gmail API rate limits
                max_workers = min(20, len(new_messages)) if new_messages else 1
                processed_count = 0

                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    # Submit all fetch tasks with credentials for each thread
                    future_to_msg = {executor.submit(fetch_single_message, msg, creds): msg for msg in new_messages}

                    # Process results as they complete
                    for future in as_completed(future_to_msg):
                        msg = future_to_msg[future]
                        processed_count += 1

                        # Update progress every 10 messages
                        if processed_count % 10 == 0:
                            yield f"data: {json.dumps({'status': 'progress', 'message': f'Processing message {processed_count}/{len(new_messages)} for {fetcher.name}...', 'source': fetcher.name})}\n\n"

                        try:
                            message_detail = future.result()

                            if "payload" in message_detail:
                                parsed_transactions = fetcher.parse_transaction(message_detail)
                                # Gmail internalDate is in milliseconds, convert to UTC datetime
                                date = datetime.fromtimestamp(int(message_detail["internalDate"]) / 1000, tz=timezone.utc)

                                # Loop through all transactions from this email (can be multiple)
                                for amount, merchant, currency in parsed_transactions:
                                    if amount:
                                        # Handle currency fallback to fetcher default if not provided
                                        final_currency = currency if currency else fetcher.default_currency

                                        # Validate currency against supported currencies
                                        if final_currency not in supported_currency_codes:
                                            # Log warning and use user's default currency
                                            yield f"data: {json.dumps({'status': 'warning', 'message': f'Unsupported currency {final_currency}, using {user_default_currency} instead'})}\n\n"
                                            final_currency = user_default_currency

                                        # Convert amount string to minor units (e.g., "5.99" USD -> 599 cents)
                                        try:
                                            amount_minor = to_minor_units(amount, final_currency)
                                        except ValueError as e:
                                            logger.error(f"Failed to convert amount '{amount}' for {final_currency}: {e}")
                                            continue

                                        tx = Transaction(
                                            id=str(uuid7()),
                                            date=date,
                                            amount=amount_minor,
                                            description=merchant or "Unknown",
                                            category="",
                                            source=fetcher.name,
                                            currency=final_currency,
                                            category_source=None,
                                            mail_id=msg['id'],
                                            created_at=datetime.now(timezone.utc),
                                            fetcher_id=fetcher.id  # Link to specific fetcher version
                                        )
                                        new_transactions.append(tx)
                        except Exception as e:
                            logger.error(f"Error processing message {msg['id']} for {fetcher.name}: {e}")
                            yield f"data: {json.dumps({'status': 'warning', 'message': f'Error processing message: {str(e)}'})}\n\n"

                yield f"data: {json.dumps({'status': 'progress', 'message': f'Saving {len(new_transactions)} transactions for {fetcher.name}...', 'source': fetcher.name})}\n\n"
                written_count = datasource.add_transactions_batch(new_transactions)

                result = {
                    "source": fetcher.name,
                    "total": len(all_messages),
                    "new": len(new_messages),
                    "written": written_count
                }

                yield f"data: {json.dumps({'status': 'progress', 'message': f'Completed {fetcher.name}: {written_count} transactions saved', 'source': fetcher.name})}\n\n"
                return result

            # Fetch from all selected fetchers
            for fetcher in fetchers:
                result = yield from fetch_with_fetcher(fetcher)
                results.append(result)

            # Invalidate Redis cache so the next page load re-classifies
            # with newly fetched transactions included.
            cache_manager.invalidate(user_id)

            yield f"data: {json.dumps({'status': 'complete', 'message': 'Fetch completed successfully!', 'results': results})}\n\n"

        except HttpError as error:
            yield f"data: {json.dumps({'status': 'error', 'message': f'Gmail API error: {str(error)}'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'status': 'error', 'message': f'Error: {str(e)}'})}\n\n"

    response = current_app.response_class(generate(), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    return response


@gmail_bp.route('/fetch-gmail/execute')
@login_required
def fetch_gmail_execute():
    """Show results page."""
    # Since we can't store results in session from the generator,
    # we'll just show a simple completion page
    return render_template('fetch_gmail_results.html', results=[])

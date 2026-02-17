"""
Transactions blueprint.

Handles transaction review, assignment, and CRUD operations.
"""

import logging
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, make_response

from domain.entities.category_tree import UNKNOWN_CATEGORY_ID
from domain.entities.transaction import CategorySource
from presentation.web.decorators import login_required
from presentation.web.extensions import get_cache_manager
from presentation.web.utils import (
    get_category_service, get_user_settings_service, get_transaction_service,
    get_classification_service, get_group_service,
    invalidate_service_cache, parse_redirect_params, extract_date_part,
    load_and_classify
)
from domain.services.amount_utils import to_major_units_float


logger = logging.getLogger(__name__)

transactions_bp = Blueprint('transactions', __name__)


@transactions_bp.route('/review')
@login_required
def review():
    """Display ALL transactions with filters (default: past 6 months)."""
    t0 = time.time()

    # Build services
    category_service = get_category_service()
    user_settings_service = get_user_settings_service()
    tx_service = get_transaction_service(category_service=category_service, user_settings_service=user_settings_service)
    classification_service = get_classification_service()
    group_service = get_group_service(transaction_service=tx_service)

    logger.debug(f"[REVIEW] service creation took {(time.time() - t0) * 1000:.2f}ms")

    category_id = request.args.get('category')
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    search_query = request.args.get('search', '').strip()  # Keep for URL state preservation
    category_source = request.args.get('category_source', '').strip()  # Filter by category source
    transaction_source = request.args.get('transaction_source', '').strip()  # Filter by transaction source
    sort_by = request.args.get('sort_by', 'date')  # Default to date sorting

    # Default to past 6 months if no dates provided
    if not from_date and not to_date:
        now = datetime.now(timezone.utc)
        # 180 days ago at 00:00:00 UTC
        six_months_ago = now - timedelta(days=180)
        from_dt = six_months_ago.replace(hour=0, minute=0, second=0, microsecond=0)
        from_date = from_dt.isoformat()
        # Today at 23:59:59 UTC
        to_dt = now.replace(hour=23, minute=59, second=59, microsecond=0)
        to_date = to_dt.isoformat()

    # Load and classify all transactions first
    t1 = time.time()
    tx_dict = load_and_classify(tx_service, classification_service)
    logger.debug(f"[REVIEW] classify_transactions() took {(time.time() - t1) * 1000:.2f}ms for {len(tx_dict)} txs")

    # Filter already-classified transactions (category/category_source require classification)
    t2 = time.time()
    transactions = tx_service.get_all_transactions_filtered(
        category_id, from_date, to_date, category_source, transaction_source,
        transactions=list(tx_dict.values())
    )
    logger.debug(f"[REVIEW] filter returned {len(transactions)} transactions in {(time.time() - t2) * 1000:.2f}ms")

    # Sort transactions based on sort_by parameter
    t3 = time.time()
    if sort_by == 'amount':
        transactions = sorted(transactions, key=lambda tx: int(tx.amount), reverse=True)
    else:  # Default to date
        transactions = sorted(transactions, key=lambda tx: tx.date, reverse=True)
    logger.debug(f"[REVIEW] Sorting took {(time.time() - t3) * 1000:.2f}ms")

    t4 = time.time()
    categories = category_service.get_categories_hierarchical()
    logger.debug(f"[REVIEW] get_categories_hierarchical() took {(time.time() - t4) * 1000:.2f}ms")

    # Create a dictionary for quick category lookup
    categories_dict = {cat.id: cat for cat, _ in categories}

    # Get all groups
    t5 = time.time()
    groups = group_service.get_all_groups()
    logger.debug(f"[REVIEW] get_all_groups() took {(time.time() - t5) * 1000:.2f}ms")

    groups_dict = {group.id: group for group in groups}

    # Get all transaction sources
    t6 = time.time()
    transaction_sources = tx_service.get_transaction_sources()
    logger.debug(f"[REVIEW] get_transaction_sources() took {(time.time() - t6) * 1000:.2f}ms")

    # Get user's default currency for display
    user_settings = user_settings_service.get_user_settings()
    default_currency = user_settings.currency if user_settings else 'JPY'
    currency_symbol = user_settings_service.get_currency_symbol(default_currency)

    # Get converter for currency conversion
    converter = user_settings_service.get_currency_converter()

    # Calculate total amount with currency conversion (rounded to 2 decimals)
    total_amount = round(sum(
        converter.convert(to_major_units_float(tx.amount, tx.currency), tx.currency, default_currency, tx.date)
        for tx in transactions
    ), 2)

    # Extract date part for display in date inputs (HTML date inputs expect YYYY-MM-DD)
    from_date_display = extract_date_part(from_date)
    to_date_display = extract_date_part(to_date)

    t7 = time.time()
    response = make_response(render_template(
        'review.html',
        transactions=transactions,
        categories=categories,
        categories_dict=categories_dict,
        groups=groups,
        groups_dict=groups_dict,
        selected_category=category_id or '',
        from_date=from_date_display,
        to_date=to_date_display,
        search_query=search_query,
        category_source=category_source,
        transaction_source=transaction_source,
        transaction_sources=transaction_sources,
        sort_by=sort_by,
        total_amount=total_amount,
        supported_currencies=user_settings_service.get_supported_currencies(),
        get_currency_symbol=user_settings_service.get_currency_symbol,
        currency_symbol=currency_symbol,
        default_currency=default_currency,
        converter=converter
    ))
    logger.debug(f"[REVIEW] render_template() took {(time.time() - t7) * 1000:.2f}ms")

    # Prevent browser caching to ensure fresh data after Gmail fetch
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'

    return response


@transactions_bp.route('/assign-similarity', methods=['POST'])
@login_required
def assign_similarity():
    """Assign categories to transactions."""
    # Build services
    category_service = get_category_service()
    user_settings_service = get_user_settings_service()
    tx_service = get_transaction_service(category_service=category_service, user_settings_service=user_settings_service)
    classification_service = get_classification_service()

    # Load and classify to know current state
    tx_dict = load_and_classify(tx_service, classification_service)

    assignments = {}

    # Parse redirect params once for reuse
    redirect_params = parse_redirect_params(request.form.get('redirect_params', ''))

    # Debug: Print what we received
    category_fields = {k: v for k, v in request.form.items() if k.startswith('category_')}
    logger.debug(f"Received category fields: {category_fields}")

    # Parse form data for all category assignments
    # Format: category_<tx_id> = <category_id>
    # Note: empty string is valid (means remove manual assignment)
    for key, value in request.form.items():
        if key.startswith('category_'):
            tx_id = key.replace('category_', '')

            logger.debug(f"Processing {tx_id}: '{value}' (type: {type(value)})")

            # Ignore attempts to assign "unknown" category
            if value == UNKNOWN_CATEGORY_ID:
                logger.debug(f"Skipping {tx_id} - unknown category")
                continue

            # Get the transaction
            tx = tx_dict.get(tx_id)
            if not tx:
                logger.debug(f"Skipping {tx_id} - transaction not found")
                continue

            logger.debug(f"Transaction {tx_id} current category: '{tx.category}', source: '{tx.category_source}'")

            # Add to assignments if:
            # 1. The category has actually changed, OR
            # 2. The transaction is SIMILARITY-based (this is a confirmation to convert to MANUAL)
            # Empty string is valid - it means remove manual assignment
            if tx.category != value or (tx.category_source == CategorySource.SIMILARITY and value != ''):
                assignments[tx_id] = value
                logger.debug(f"Adding {tx_id} to assignments: '{value}'")
            else:
                logger.debug(f"Skipping {tx_id} - no change")

    logger.debug(f"Final assignments: {assignments}")

    # Assign all categories at once
    if assignments:
        tx_service.assign_categories_bulk(assignments)
        invalidate_service_cache(request.user_id)
        flash(f'Successfully reassigned {len(assignments)} transaction(s).', 'success')
    else:
        flash('No changes detected. No transactions were updated.', 'error')

    # Determine redirect target (default to review page)
    redirect_to = request.form.get('redirect_to', 'review')

    # Preserve all query parameters on redirect
    if redirect_to == 'groups':
        return redirect(url_for('groups.groups', **redirect_params))
    else:
        return redirect(url_for('transactions.review', **redirect_params))


@transactions_bp.route('/api/investigate-similarity/<tx_id>')
@login_required
def investigate_similarity(tx_id):
    """Get similar transactions that influenced the similarity-based categorization."""
    # Build services
    category_service = get_category_service()
    user_settings_service = get_user_settings_service()
    tx_service = get_transaction_service(category_service=category_service, user_settings_service=user_settings_service)
    classification_service = get_classification_service()

    # Load and classify
    tx_dict = load_and_classify(tx_service, classification_service)

    # Get the transaction
    tx = tx_dict.get(tx_id)
    if not tx:
        return jsonify({'success': False, 'error': 'Transaction not found'}), 404

    # Only investigate similarity-based transactions
    if tx.category_source != CategorySource.SIMILARITY:
        return jsonify({'success': False, 'error': 'Transaction was not categorized via similarity'}), 400

    # Use classification service to investigate
    result = classification_service.investigate_similarity(
        tx_id, tx.description, tx_dict, category_service.categories
    )

    if not result['success']:
        return jsonify(result), 500

    categories = category_service.categories
    response = jsonify({
        'success': True,
        'transaction': {
            'id': tx.id,
            'description': tx.description,
            'category': tx.category,
            'category_name': categories.get(tx.category).name if tx.category in categories else 'Unknown'
        },
        'similar_transactions': result['similar_transactions'],
        'threshold': result['threshold']
    })

    # Prevent caching of dynamic data
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'

    return response


@transactions_bp.route('/update-transaction', methods=['POST'])
@login_required
def update_transaction():
    """Update all fields of a transaction."""
    user_settings_service = get_user_settings_service()
    category_service = get_category_service()
    tx_service = get_transaction_service(category_service=category_service, user_settings_service=user_settings_service)
    classification_service = get_classification_service()

    data = request.get_json()

    tx_id = data.get('tx_id', '').strip()
    date = data.get('date', '').strip()
    amount = data.get('amount', '').strip()
    description = data.get('description', '').strip()
    comment = data.get('comment', '').strip()
    currency = data.get('currency', '').strip()

    if not tx_id:
        return jsonify({'success': False, 'error': 'Transaction ID is required'}), 400

    # Validate currency if provided, otherwise use default
    if not currency:
        currency = user_settings_service.get_default_currency()

    if not user_settings_service.validate_currency(currency):
        return jsonify({'success': False, 'error': f'Unsupported currency: {currency}'}), 400

    # Update the transaction, passing embedding datasource for cache invalidation
    success, error_msg = tx_service.update_transaction(
        tx_id, date, amount, description, comment, currency,
        embedding_datasource=classification_service.embedding_datasource
    )

    if success:
        invalidate_service_cache(request.user_id)
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': error_msg}), 400


@transactions_bp.route('/add-transaction', methods=['POST'])
@login_required
def add_transaction():
    """Add a new transaction manually. Transaction ID is auto-generated."""
    user_settings_service = get_user_settings_service()
    category_service = get_category_service()
    tx_service = get_transaction_service(category_service=category_service, user_settings_service=user_settings_service)
    classification_service = get_classification_service()

    data = request.get_json()

    date = data.get('date', '').strip()
    amount = data.get('amount', '').strip()
    description = data.get('description', '').strip()
    category = data.get('category', '').strip()  # Optional
    comment = data.get('comment', '').strip()
    currency = data.get('currency', '').strip()

    # Validate required fields (category is optional)
    if not all([date, amount, description]):
        return jsonify({
            'success': False,
            'error': 'Date, amount, and description are required'
        }), 400

    # Currency defaults to user's default currency if not provided
    if not currency:
        currency = user_settings_service.get_default_currency()

    # Validate currency
    if not user_settings_service.validate_currency(currency):
        return jsonify({'success': False, 'error': f'Unsupported currency: {currency}'}), 400

    # Add the transaction (ID and source are auto-generated in service)
    success, error_msg = tx_service.add_new_transaction(
        date_str=date,
        amount=amount,
        description=description,
        category=category,  # Empty string if not provided
        comment=comment,
        currency=currency,
        classifier=classification_service.classifier if not category else None
    )

    if success:
        invalidate_service_cache(request.user_id)
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': error_msg}), 400


@transactions_bp.route('/api/manual-transaction-autocomplete')
@login_required
def manual_transaction_autocomplete():
    """
    Get autocomplete suggestions based on previously manually-added transactions.
    Groups by description and returns the majority category for each unique description.
    """
    category_service = get_category_service()
    user_settings_service = get_user_settings_service()
    tx_service = get_transaction_service(category_service=category_service, user_settings_service=user_settings_service)
    classification_service = get_classification_service()

    # Load and classify all transactions for category lookup
    tx_dict = load_and_classify(tx_service, classification_service)

    # Get all manual transactions
    manual_transactions = tx_service.get_transactions_by_source('Manual')

    # Group by description and calculate majority category
    # Structure: {description: {'amounts': [amounts], 'categories': [category_ids]}}
    grouped = defaultdict(lambda: {'amounts': [], 'categories': []})

    for tx in manual_transactions:
        # Get the classified version
        tx_with_category = tx_dict.get(tx.id)
        if tx_with_category and tx_with_category.category:
            category_id = tx_with_category.category
        else:
            category_id = ''

        grouped[tx.description]['amounts'].append(int(tx.amount))
        grouped[tx.description]['categories'].append(category_id)

    categories = category_service.categories

    # Build suggestions list with majority category for each description
    suggestions = []
    for description, data in grouped.items():
        # Calculate majority category
        category_counts = Counter(data['categories'])
        majority_category = category_counts.most_common(1)[0][0] if category_counts else ''

        # Use the most recent amount (last in list)
        sample_amount = data['amounts'][-1] if data['amounts'] else 0

        # Get category name
        category_name = ''
        if majority_category and majority_category in categories:
            category_name = categories[majority_category].name

        suggestions.append({
            'description': description,
            'category_id': majority_category,
            'category_name': category_name,
            'amount': sample_amount
        })

    # Sort by description alphabetically
    suggestions.sort(key=lambda x: x['description'].lower())

    response = jsonify({'success': True, 'suggestions': suggestions})

    # Prevent caching of dynamic data
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'

    return response

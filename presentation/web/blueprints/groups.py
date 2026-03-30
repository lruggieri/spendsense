"""
Groups blueprint.

Handles transaction group management routes including CRUD and bulk operations.
"""

import logging

from flask import Blueprint, jsonify, make_response, render_template, request

from domain.entities.category_tree import CategoryTree
from domain.entities.transaction import ENCRYPTED_PLACEHOLDER
from domain.services.amount_utils import to_major_units_float
from presentation.web.decorators import login_required
from presentation.web.utils import (
    get_category_service,
    get_classification_service,
    get_group_service,
    get_transaction_service,
    get_user_settings_service,
    load_and_classify,
    tree_to_dict,
)

logger = logging.getLogger(__name__)

groups_bp = Blueprint("groups", __name__)


@groups_bp.route("/groups")
@login_required
def groups():
    """Display groups management page with optional transaction filtering by group."""
    # Build services
    category_service = get_category_service()
    user_settings_service = get_user_settings_service()
    tx_service = get_transaction_service(
        category_service=category_service, user_settings_service=user_settings_service
    )
    classification_service = get_classification_service()
    group_service = get_group_service(transaction_service=tx_service)

    group_id = request.args.get("group_id")
    search_query = request.args.get("search", "").strip()  # Keep for URL state preservation
    sort_by = request.args.get("sort_by", "date")  # Default to date sorting

    # Get all groups with transaction counts
    all_groups = group_service.get_all_groups()
    group_transaction_counts = {}
    for group in all_groups:
        group_txs = tx_service.get_transactions_by_group(group.id)
        group_transaction_counts[group.id] = len(group_txs)

    # Get selected group and its transactions if group_id provided
    selected_group = None
    transactions = []
    total_amount = 0
    categories_dict = {}
    categories = []
    tree_data = None

    # Get user's default currency for display
    user_settings = user_settings_service.get_user_settings()
    default_currency = user_settings.currency if user_settings else "JPY"
    currency_symbol = user_settings_service.get_currency_symbol(default_currency)

    if group_id:
        # Find the selected group
        selected_group = next((g for g in all_groups if g.id == group_id), None)

        if selected_group:
            # Load and classify all transactions
            tx_dict = load_and_classify(tx_service, classification_service)

            # Get transactions for this group with classification applied
            group_transactions = tx_service.get_transactions_by_group(group_id)
            classified_transactions = []
            for tx in group_transactions:
                if tx.id in tx_dict:
                    classified_transactions.append(tx_dict[tx.id])
                else:
                    classified_transactions.append(tx)

            # Sort transactions based on sort_by parameter
            if sort_by == "amount":
                transactions = sorted(
                    classified_transactions, key=lambda tx: int(tx.amount), reverse=True
                )
            else:  # Default to date
                transactions = sorted(classified_transactions, key=lambda tx: tx.date, reverse=True)

            # Calculate total amount with currency conversion
            converter = user_settings_service.get_currency_converter()
            total_amount = round(
                sum(
                    converter.convert(
                        to_major_units_float(tx.amount, tx.currency),
                        tx.currency,
                        default_currency,
                        tx.date,
                    )
                    for tx in transactions
                ),
                2,
            )

            # Get categories for display and category modal
            categories_dict = category_service.categories
            categories = category_service.get_categories_hierarchical()

            # Generate category tree data for visualization
            categories_dict_list = category_service.get_categories_as_dict_list()
            tree = CategoryTree(categories_dict_list)
            tree.calculate_expenses(
                classified_transactions, None, None, default_currency, converter
            )
            tree_data = tree_to_dict(tree.root)

    # Create groups_dict for easy lookup in template
    groups_dict = {group.id: group for group in all_groups}

    response = make_response(
        render_template(
            "groups.html",
            groups=all_groups,
            groups_dict=groups_dict,
            group_transaction_counts=group_transaction_counts,
            selected_group=selected_group,
            transactions=transactions,
            total_amount=total_amount,
            categories_dict=categories_dict,
            categories=categories,
            tree_data=tree_data,
            search_query=search_query,
            sort_by=sort_by,
            supported_currencies=user_settings_service.get_supported_currencies(),
            get_currency_symbol=user_settings_service.get_currency_symbol,
            currency_symbol=currency_symbol,
            default_currency=default_currency,
            converter=user_settings_service.get_currency_converter(),
            encrypted_placeholder=ENCRYPTED_PLACEHOLDER,
        )
    )

    # Prevent caching
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    return response


@groups_bp.route("/api/add-group-to-transaction", methods=["POST"])
@login_required
def api_add_group_to_transaction():
    """Add a group to a single transaction."""
    data = request.get_json()
    tx_id = data.get("tx_id")
    group_id = data.get("group_id")

    if not tx_id or not group_id:
        return jsonify({"success": False, "error": "Missing tx_id or group_id"}), 400

    try:
        group_service = get_group_service()
        success, error = group_service.add_transaction_to_group(tx_id, group_id)

        if success:
            return jsonify({"success": True})
        else:
            return jsonify(
                {"success": False, "error": error or "Transaction not found or group already added"}
            )

    except Exception as e:
        logger.error(f"Error adding group to transaction: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@groups_bp.route("/api/remove-group-from-transaction", methods=["POST"])
@login_required
def api_remove_group_from_transaction():
    """Remove a group from a single transaction."""
    data = request.get_json()
    tx_id = data.get("tx_id")
    group_id = data.get("group_id")

    if not tx_id or not group_id:
        return jsonify({"success": False, "error": "Missing tx_id or group_id"}), 400

    try:
        group_service = get_group_service()
        success, error = group_service.remove_transaction_from_group(tx_id, group_id)

        if success:
            return jsonify({"success": True})
        else:
            return jsonify(
                {"success": False, "error": error or "Transaction not found or group not present"}
            )

    except Exception as e:
        logger.error(f"Error removing group from transaction: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@groups_bp.route("/api/bulk-add-group", methods=["POST"])
@login_required
def api_bulk_add_group():
    """Add a group to multiple transactions."""
    data = request.get_json()
    tx_ids = data.get("tx_ids", [])
    group_id = data.get("group_id")

    if not tx_ids or not group_id:
        return jsonify({"success": False, "error": "Missing tx_ids or group_id"}), 400

    try:
        group_service = get_group_service()
        success, error, count = group_service.add_transactions_to_group(tx_ids, group_id)

        if success:
            return jsonify({"success": True, "count": count})
        else:
            return jsonify({"success": False, "error": error}), 400

    except Exception as e:
        logger.error(f"Error bulk adding group: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@groups_bp.route("/api/bulk-remove-group", methods=["POST"])
@login_required
def api_bulk_remove_group():
    """Remove a group from multiple transactions."""
    data = request.get_json()
    tx_ids = data.get("tx_ids", [])
    group_id = data.get("group_id")

    if not tx_ids or not group_id:
        return jsonify({"success": False, "error": "Missing tx_ids or group_id"}), 400

    try:
        group_service = get_group_service()
        success, error, count = group_service.remove_transactions_from_group(tx_ids, group_id)

        if success:
            return jsonify({"success": True, "count": count})
        else:
            return jsonify({"success": False, "error": error}), 400

    except Exception as e:
        logger.error(f"Error bulk removing group: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@groups_bp.route("/api/create-group", methods=["POST"])
@login_required
def api_create_group():
    """Create a new group."""
    data = request.get_json()
    name = data.get("name", "").strip()

    if not name:
        return jsonify({"success": False, "error": "Group name is required"}), 400

    try:
        group_service = get_group_service()
        success, error, group_id = group_service.create_group(name)

        if success:
            return jsonify({"success": True, "group_id": group_id})
        else:
            return jsonify({"success": False, "error": error}), 400

    except Exception as e:
        logger.error(f"Error creating group: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@groups_bp.route("/api/update-group", methods=["POST"])
@login_required
def api_update_group():
    """Update a group."""
    data = request.get_json()
    group_id = data.get("group_id")
    name = data.get("name", "").strip()

    if not group_id or not name:
        return jsonify({"success": False, "error": "Group ID and name are required"}), 400

    try:
        group_service = get_group_service()
        success, error = group_service.update_group(group_id, name=name)

        if success:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": error or "Group not found"})

    except Exception as e:
        logger.error(f"Error updating group: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@groups_bp.route("/api/delete-group", methods=["POST"])
@login_required
def api_delete_group():
    """Delete a group and remove it from all transactions."""
    data = request.get_json()
    group_id = data.get("group_id")

    if not group_id:
        return jsonify({"success": False, "error": "Group ID is required"}), 400

    try:
        group_service = get_group_service()
        success, error = group_service.delete_group(group_id, cascade=True)

        if success:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": error or "Group not found"})

    except Exception as e:
        logger.error(f"Error deleting group: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

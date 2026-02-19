"""
Main blueprint.

Handles main pages like index, charts, trends, and utility routes.
"""

import calendar
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from flask import (
    Blueprint,
    current_app,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)

from domain.services.amount_utils import to_major_units_float
from presentation.web.decorators import login_required
from presentation.web.utils import (
    build_category_tree_data,
    extract_date_part,
    get_category_service,
    get_classification_service,
    get_transaction_service,
    get_user_settings_service,
    invalidate_service_cache,
    load_and_classify,
    parse_redirect_params,
)

logger = logging.getLogger(__name__)

main_bp = Blueprint("main", __name__)


@main_bp.route("/privacy-policy")
def privacy_policy():
    """Public privacy policy page."""
    return render_template("privacy_policy.html")


@main_bp.route("/")
@login_required
def index():
    """Redirect to review page (new home)."""
    return redirect(url_for("transactions.review"))


@main_bp.route("/service-worker.js")
def service_worker():
    """Serve the service worker with proper MIME type."""
    response = make_response(current_app.send_static_file("service-worker.js"))
    response.headers["Content-Type"] = "application/javascript"
    # Disable caching for service worker to ensure updates are picked up
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@main_bp.route("/recategorize", methods=["POST"])
@login_required
def recategorize():
    """Trigger re-categorization of all transactions.

    Classification is runtime-computed, so this just invalidates the cache.
    The redirect target (review page) will re-classify on load.
    """
    invalidate_service_cache(request.user_id)
    # Preserve all query parameters when redirecting
    params = parse_redirect_params(request.form.get("redirect_params", ""))
    return redirect(url_for("transactions.review", **params))


@main_bp.route("/charts")
@login_required
def charts():
    """Display expense analysis charts."""
    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")

    # Default to current month if no dates provided
    if not from_date and not to_date:
        now = datetime.now(timezone.utc)
        # First day of current month at 00:00:00 UTC
        from_dt = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        from_date = from_dt.isoformat()
        # Last day of current month at 23:59:59 UTC
        last_day = calendar.monthrange(now.year, now.month)[1]
        to_dt = now.replace(day=last_day, hour=23, minute=59, second=59, microsecond=0)
        to_date = to_dt.isoformat()

    # Build services
    category_service = get_category_service()
    user_settings_service = get_user_settings_service()
    tx_service = get_transaction_service(
        category_service=category_service, user_settings_service=user_settings_service
    )
    classification_service = get_classification_service()

    # Load and classify transactions
    tx_dict = load_and_classify(tx_service, classification_service)
    classified_txs = list(tx_dict.values())

    # Pass full date strings (possibly ISO 8601) for timezone-aware filtering
    tree_data = build_category_tree_data(
        category_service, user_settings_service, classified_txs, from_date, to_date
    )

    # Extract date part (YYYY-MM-DD) for display in HTML date inputs
    from_date_display = extract_date_part(from_date)
    to_date_display = extract_date_part(to_date)

    # Get user's default currency for display
    user_settings = user_settings_service.get_user_settings()
    default_currency = user_settings.currency if user_settings else "JPY"
    currency_symbol = user_settings_service.get_currency_symbol(default_currency)

    response = make_response(
        render_template(
            "charts.html",
            tree_data=tree_data,
            from_date=from_date_display,
            to_date=to_date_display,
            currency_symbol=currency_symbol,
        )
    )

    # Prevent browser caching to ensure fresh data
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    return response


@main_bp.route("/api/tree-data")
@login_required
def api_tree_data():
    """API endpoint to get category tree data."""
    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")

    # Build services
    category_service = get_category_service()
    user_settings_service = get_user_settings_service()
    tx_service = get_transaction_service(
        category_service=category_service, user_settings_service=user_settings_service
    )
    classification_service = get_classification_service()

    # Load and classify transactions
    tx_dict = load_and_classify(tx_service, classification_service)
    classified_txs = list(tx_dict.values())

    tree_data = build_category_tree_data(
        category_service, user_settings_service, classified_txs, from_date, to_date
    )
    response = jsonify(tree_data)

    # Prevent caching of dynamic data
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    return response


@main_bp.route("/api/debug-info")
@login_required
def api_debug_info():
    """API endpoint to get debug information."""
    from domain.services.currency_converter import CurrencyConverterService

    # Set defaults
    debug_info = {"ecb_first_date": None, "ecb_last_date": None}

    # Get ECB currency data date range
    try:
        currency_service = CurrencyConverterService.get_instance()
        if currency_service.converter:
            bounds_dict = getattr(currency_service.converter, "bounds", None)
            if bounds_dict:
                # Assume all bound objects have first_date and last_date
                # If they don't, the AttributeError will be caught by outer try/except
                first_dates = [b.first_date for b in bounds_dict.values()]
                last_dates = [b.last_date for b in bounds_dict.values()]

                if first_dates and last_dates:
                    debug_info["ecb_first_date"] = min(first_dates).isoformat()
                    debug_info["ecb_last_date"] = max(last_dates).isoformat()
    except Exception as e:
        logger.error(f"Error getting ECB date range: {e}")
        debug_info["ecb_error"] = str(e)

    response = jsonify(debug_info)

    # Prevent caching
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    return response


@main_bp.route("/trends")
@login_required
def trends():
    """Display expense trends over time."""
    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")

    # Default to past 12 months if no dates provided
    if not from_date and not to_date:
        now = datetime.now(timezone.utc)
        # 365 days ago at 00:00:00 UTC
        twelve_months_ago = now - timedelta(days=365)
        from_dt = twelve_months_ago.replace(hour=0, minute=0, second=0, microsecond=0)
        from_date = from_dt.isoformat()
        # Today at 23:59:59 UTC
        to_dt = now.replace(hour=23, minute=59, second=59, microsecond=0)
        to_date = to_dt.isoformat()

    # Build services
    category_service = get_category_service()
    user_settings_service = get_user_settings_service()
    tx_service = get_transaction_service(
        category_service=category_service, user_settings_service=user_settings_service
    )
    classification_service = get_classification_service()

    # Load and classify all transactions, then filter
    tx_dict = load_and_classify(tx_service, classification_service)

    # Filter already-classified transactions
    transactions = tx_service.get_all_transactions_filtered(
        None, from_date, to_date, transactions=list(tx_dict.values())
    )

    categories = category_service.get_categories_hierarchical()

    # Get user currency and converter for currency conversion
    user_settings = user_settings_service.get_user_settings()
    user_currency = user_settings.currency if user_settings else "JPY"
    converter = user_settings_service.get_currency_converter()

    # Aggregate by month and category
    # Structure: {month: {category_id: total_amount}}
    monthly_data = defaultdict(lambda: defaultdict(int))

    for tx in transactions:
        month_key = tx.date.strftime("%Y-%m")
        category_id = tx.category or "unknown"

        # Convert from minor units to major units, then convert currency
        amount_major = to_major_units_float(tx.amount, tx.currency)
        converted_amount = converter.convert(amount_major, tx.currency, user_currency, tx.date)
        monthly_data[month_key][category_id] += converted_amount

    # Round all monthly totals to 2 decimals to prevent floating point accumulation
    for month_key in monthly_data:
        for category_id in monthly_data[month_key]:
            monthly_data[month_key][category_id] = round(monthly_data[month_key][category_id], 2)

    # Sort months chronologically
    sorted_months = sorted(monthly_data.keys())

    all_categories = category_service.categories

    # Helper function to find the root ancestor of a category
    def find_root_parent(category_id):
        """Find the top-level parent of a category."""
        cat = all_categories.get(category_id)
        if not cat:
            return None

        # If no parent or parent doesn't exist, this is the root
        if not cat.parent_id or cat.parent_id not in all_categories:
            return category_id

        # Recursively find the parent
        return find_root_parent(cat.parent_id)

    # Get top-level categories only (parent_id is empty or not in categories)
    top_categories = []
    for cat, depth in categories:
        if depth == 0:  # Root level categories
            top_categories.append(cat)

    # Create datasets for each top-level category and ALL their descendant subcategories
    datasets = []
    for cat in top_categories:
        # Get all descendant category IDs
        descendant_ids = category_service.get_descendant_category_ids(cat.id)

        # Aggregate data for this category and its descendants
        monthly_amounts = []
        for month in sorted_months:
            total = sum(monthly_data[month].get(cat_id, 0) for cat_id in descendant_ids)
            monthly_amounts.append(total)

        # Only include categories with at least some data
        if sum(monthly_amounts) > 0:
            datasets.append(
                {
                    "label": cat.name,
                    "data": monthly_amounts,
                    "category_id": cat.id,
                    "is_top_level": True,
                    "parent_id": None,
                    "depth": 0,
                }
            )

            # Add ALL descendant subcategories at ALL levels
            for subcat, depth in categories:
                # Check if this subcategory is a descendant of the current top-level category
                root_parent = find_root_parent(subcat.id)
                if root_parent == cat.id and subcat.id != cat.id:
                    # Get IDs for this subcategory and its descendants
                    sub_descendant_ids = category_service.get_descendant_category_ids(subcat.id)

                    # Aggregate data for this subcategory
                    sub_monthly_amounts = []
                    for month in sorted_months:
                        total = sum(
                            monthly_data[month].get(cat_id, 0) for cat_id in sub_descendant_ids
                        )
                        sub_monthly_amounts.append(total)

                    # Only include if there's data
                    if sum(sub_monthly_amounts) > 0:
                        datasets.append(
                            {
                                "label": subcat.name,
                                "data": sub_monthly_amounts,
                                "category_id": subcat.id,
                                "is_top_level": False,
                                "parent_id": subcat.parent_id,
                                "root_parent_id": cat.id,
                                "depth": depth,
                            }
                        )

    # Calculate moving averages (3-point) for each dataset
    def calculate_moving_average(data, window=3):
        """
        Calculate trailing moving average for a list of values.
        For each point, averages the current point and the previous (window-1) points.
        This ensures we only use historical data, not future data.
        """
        if len(data) == 0:
            return []
        if len(data) == 1:
            return data[:]

        moving_avg = []
        for i in range(len(data)):
            if i == 0:
                # First point: just use the first point
                moving_avg.append(data[0])
            elif i == 1:
                # Second point: average of first 2 points
                moving_avg.append((data[0] + data[1]) / 2)
            else:
                # All other points: trailing 3-point average (previous 2 + current)
                moving_avg.append((data[i - 2] + data[i - 1] + data[i]) / 3)

        return moving_avg

    # Create moving average datasets
    moving_avg_datasets = []
    for dataset in datasets:
        moving_avg_data = calculate_moving_average(dataset["data"])
        moving_avg_datasets.append(
            {
                "label": dataset["label"],
                "data": moving_avg_data,
                "category_id": dataset["category_id"],
                "is_top_level": dataset["is_top_level"],
                "parent_id": dataset.get("parent_id"),
                "root_parent_id": dataset.get("root_parent_id"),
                "depth": dataset["depth"],
            }
        )

    # Calculate monthly totals and their moving average for summary chart
    monthly_totals = []
    for month in sorted_months:
        total = sum(monthly_data[month].values())
        monthly_totals.append(total)

    monthly_totals_moving_avg = calculate_moving_average(monthly_totals)

    # Extract date part for display in date inputs (HTML date inputs expect YYYY-MM-DD)
    from_date_display = extract_date_part(from_date)
    to_date_display = extract_date_part(to_date)

    # Get user's default currency for display
    default_currency = user_settings.currency if user_settings else "JPY"
    currency_symbol = user_settings_service.get_currency_symbol(default_currency)

    response = make_response(
        render_template(
            "trends.html",
            months=sorted_months,
            datasets=datasets,
            moving_avg_datasets=moving_avg_datasets,
            monthly_totals=monthly_totals,
            monthly_totals_moving_avg=monthly_totals_moving_avg,
            from_date=from_date_display,
            to_date=to_date_display,
            currency_symbol=currency_symbol,
        )
    )

    # Prevent browser caching to ensure fresh data
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    return response

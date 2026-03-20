"""
Patterns blueprint.

Handles regex pattern management routes for transaction categorization.
"""

from flask import Blueprint, jsonify, make_response, render_template, request

from presentation.web.decorators import login_required
from presentation.web.utils import (
    get_category_service,
    get_pattern_service,
)

patterns_bp = Blueprint("patterns", __name__)


@patterns_bp.route("/patterns")
@login_required
def patterns():
    """Patterns settings page for managing regex patterns."""
    category_service = get_category_service()
    pattern_service = get_pattern_service(category_service=category_service)
    patterns_data = pattern_service.get_all_patterns()
    categories_hierarchical = category_service.get_categories_hierarchical()

    response = make_response(
        render_template(
            "patterns.html", patterns=patterns_data, all_categories=categories_hierarchical
        )
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@patterns_bp.route("/api/get-pattern/<pattern_id>", methods=["GET"])
@login_required
def get_pattern_api(pattern_id):
    """API endpoint to get a single pattern for editing."""
    pattern_service = get_pattern_service()
    success, error, pattern = pattern_service.get_pattern_by_id(pattern_id)

    if success:
        return jsonify({"success": True, "pattern": pattern})
    else:
        return jsonify({"success": False, "error": error})


@patterns_bp.route("/api/create-pattern", methods=["POST"])
@login_required
def create_pattern_api():
    """API endpoint to create a new pattern."""
    data = request.get_json()
    rules = data.get("rules", [])
    category_id = data.get("category_id", "").strip()
    name = data.get("name", "").strip()

    pattern_service = get_pattern_service()
    success, error, pattern_id = pattern_service.create_pattern(rules, category_id, name)

    if success:
        return jsonify({"success": True, "pattern_id": pattern_id})
    else:
        return jsonify({"success": False, "error": error})


@patterns_bp.route("/api/update-pattern", methods=["POST"])
@login_required
def update_pattern_api():
    """API endpoint to update an existing pattern."""
    data = request.get_json()
    pattern_id = data.get("pattern_id", "").strip()
    rules = data.get("rules", [])
    category_id = data.get("category_id", "").strip()
    name = data.get("name", "").strip()

    pattern_service = get_pattern_service()
    success, error = pattern_service.update_pattern(pattern_id, rules, category_id, name)

    if success:
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "error": error})


@patterns_bp.route("/api/delete-pattern", methods=["POST"])
@login_required
def delete_pattern_api():
    """API endpoint to delete a pattern."""
    data = request.get_json()
    pattern_id = data.get("pattern_id", "").strip()

    pattern_service = get_pattern_service()
    success, error = pattern_service.delete_pattern(pattern_id)

    if success:
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "error": error})


@patterns_bp.route("/api/reorder-patterns", methods=["POST"])
@login_required
def reorder_patterns_api():
    """API endpoint to persist drag-and-drop pattern order."""
    data = request.get_json()
    order_map = data.get("order_map", {})

    pattern_service = get_pattern_service()
    success, error = pattern_service.reorder_patterns(order_map)

    if success:
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "error": error})

"""
Categories blueprint.

Handles category management routes including CRUD operations.
"""

from flask import Blueprint, jsonify, make_response, render_template, request

from presentation.web.decorators import login_required
from presentation.web.utils import get_category_service

categories_bp = Blueprint("categories", __name__)


@categories_bp.route("/categories")
@login_required
def categories():
    """Category settings page for managing categories."""
    category_service = get_category_service()
    categories_hierarchical = category_service.get_categories_hierarchical()

    # Build categories data with protected flag
    categories_data = []
    for cat, depth in categories_hierarchical:
        categories_data.append(
            {
                "id": cat.id,
                "name": cat.name,
                "description": cat.description,
                "parent_id": cat.parent_id,
                "depth": depth,
                "is_protected": cat.id in ["all", "unknown"],
            }
        )

    response = make_response(
        render_template(
            "categories.html", categories=categories_data, all_categories=categories_hierarchical
        )
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@categories_bp.route("/api/create-category", methods=["POST"])
@login_required
def create_category_api():
    """API endpoint to create a new category."""
    data = request.get_json()
    name = data.get("name", "").strip()
    description = data.get("description", "").strip()
    parent_id = data.get("parent_id", "").strip()

    category_service = get_category_service()
    success, error, category_id = category_service.create_category(name, description, parent_id)

    if success:
        return jsonify({"success": True, "category_id": category_id})
    else:
        return jsonify({"success": False, "error": error})


@categories_bp.route("/api/update-category", methods=["POST"])
@login_required
def update_category_api():
    """API endpoint to update an existing category."""
    data = request.get_json()
    category_id = data.get("category_id", "").strip()
    name = data.get("name", "").strip() if "name" in data else None
    description = data.get("description", "").strip() if "description" in data else None
    parent_id = data.get("parent_id", "").strip() if "parent_id" in data else None

    category_service = get_category_service()
    success, error = category_service.update_category(category_id, name, description, parent_id)

    if success:
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "error": error})


@categories_bp.route("/api/delete-category", methods=["POST"])
@login_required
def delete_category_api():
    """API endpoint to delete a category."""
    data = request.get_json()
    category_id = data.get("category_id", "").strip()

    category_service = get_category_service()
    success, error = category_service.delete_category(category_id)

    if success:
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "error": error})

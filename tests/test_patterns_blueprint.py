"""Tests for the patterns blueprint routes."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_services():
    """Set up mock services for the patterns blueprint."""
    mock_category_service = MagicMock()
    mock_category_service.get_categories_hierarchical.return_value = []
    mock_category_service.categories = {}

    mock_pattern_service = MagicMock()
    mock_pattern_service.get_all_patterns.return_value = []

    patches = {
        "cat": patch(
            "presentation.web.blueprints.patterns.get_category_service",
            return_value=mock_category_service,
        ),
        "pattern": patch(
            "presentation.web.blueprints.patterns.get_pattern_service",
            return_value=mock_pattern_service,
        ),
    }

    started = {}
    for key, p in patches.items():
        started[key] = p.start()

    yield {
        "category_service": mock_category_service,
        "pattern_service": mock_pattern_service,
        "patches": started,
    }

    for p in patches.values():
        p.stop()


class TestPatternsBlueprint:
    """Tests for the patterns blueprint routes."""

    def test_patterns_page_loads(self, authenticated_client, mock_services):
        """GET /patterns should return 200."""
        response = authenticated_client.get("/patterns")
        assert response.status_code == 200

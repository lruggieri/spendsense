"""Tests for the categories blueprint routes."""
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_services():
    """Set up mock services for the categories blueprint."""
    mock_category_service = MagicMock()
    mock_category_service.get_categories_hierarchical.return_value = []
    mock_category_service.categories = {}

    patches = {
        'cat': patch(
            'presentation.web.blueprints.categories.get_category_service',
            return_value=mock_category_service,
        ),
        'invalidate': patch(
            'presentation.web.blueprints.categories.invalidate_service_cache',
        ),
    }

    started = {}
    for key, p in patches.items():
        started[key] = p.start()

    yield {
        'category_service': mock_category_service,
        'patches': started,
    }

    for p in patches.values():
        p.stop()


class TestCategoriesBlueprint:
    """Tests for the categories blueprint routes."""

    def test_categories_page_loads(self, authenticated_client, mock_services):
        """GET /categories should return 200."""
        response = authenticated_client.get('/categories')
        assert response.status_code == 200

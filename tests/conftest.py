"""Shared pytest fixtures for integration tests."""
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from domain.entities.session import Session

# Resolve the real template/static directories used by the production app
_WEB_DIR = os.path.join(os.path.dirname(__file__), os.pardir, 'presentation', 'web')
_TEMPLATE_DIR = os.path.abspath(os.path.join(_WEB_DIR, 'templates'))
_STATIC_DIR = os.path.abspath(os.path.join(_WEB_DIR, 'static'))


@pytest.fixture
def app():
    """Create and configure a test Flask application."""
    app = Flask(
        __name__,
        template_folder=_TEMPLATE_DIR,
        static_folder=_STATIC_DIR,
    )
    app.config['TESTING'] = True
    app.config['DATABASE_PATH'] = ':memory:'
    app.secret_key = 'test_secret_key_for_sessions'

    # Register all blueprints for integration tests
    from presentation.web.blueprints import register_blueprints
    register_blueprints(app)

    # Register context processors so templates can render
    from presentation.web.context_processors import register_context_processors
    register_context_processors(app)

    # Register custom Jinja2 filters so templates can render
    from presentation.web.filters import register_filters
    register_filters(app)

    yield app


@pytest.fixture
def client(app):
    """Create a test client for making requests."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """Create a test CLI runner."""
    return app.test_cli_runner()


@pytest.fixture
def app_context(app):
    """Create application context with request.user_id set."""
    with app.test_request_context():
        from flask import request
        request.user_id = "test_user@example.com"
        yield app


@pytest.fixture
def mock_db_path(tmp_path):
    """Provide a temporary database path for testing."""
    db_file = tmp_path / "test.db"
    return str(db_file)


@pytest.fixture
def mock_session_datasource():
    """Create a mock session datasource that validates a test session token."""
    datasource = MagicMock()
    valid_session = Session(
        session_token='valid_test_token',
        user_id='test@example.com',
        expiration=datetime.now(timezone.utc) + timedelta(days=7),
        google_token={'user_name': 'Test User', 'user_picture': ''},
        created_at=datetime.now(timezone.utc),
    )
    datasource.get_session.side_effect = lambda token, encryption_key=None: (
        valid_session if token == 'valid_test_token' else None
    )
    return datasource


@pytest.fixture
def authenticated_client(app, mock_session_datasource):
    """
    Flask test client with a valid session cookie and mocked auth dependencies.

    The session cookie is set to 'valid_test_token' which the mock_session_datasource
    recognises. Onboarding check is bypassed.
    """
    with patch(
        'presentation.web.decorators.get_session_datasource',
        return_value=mock_session_datasource,
    ), patch(
        'presentation.web.decorators._check_onboarding_required',
        return_value=None,
    ):
        client = app.test_client()
        client.set_cookie('session_token', 'valid_test_token')
        yield client

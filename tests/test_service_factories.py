"""Tests for service factory functions in presentation.web.utils."""
from unittest.mock import MagicMock, patch

import pytest
from flask import g

from application.services import (
    CategoryService,
    ClassificationService,
    FetcherService,
    GroupService,
    PatternService,
    TransactionService as SlimTransactionService,
    UserSettingsService,
)
from presentation.web.utils import (
    _get_datasource_factory,
    _get_user_id,
    get_category_service,
    get_classification_service,
    get_fetcher_service,
    get_group_service,
    get_pattern_service,
    get_transaction_service,
    get_user_settings_service,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_factory():
    """Return a MagicMock that behaves like SQLiteDataSourceFactory."""
    factory = MagicMock()
    factory.get_category_datasource.return_value = MagicMock()
    factory.get_transaction_datasource.return_value = MagicMock()
    factory.get_manual_assignment_datasource.return_value = MagicMock()
    factory.get_regexp_datasource.return_value = MagicMock()
    factory.get_embedding_datasource.return_value = MagicMock()
    factory.get_user_settings_datasource.return_value = MagicMock()
    factory.get_fetcher_datasource.return_value = MagicMock()
    factory.get_group_datasource.return_value = MagicMock()
    return factory


@pytest.fixture(autouse=True)
def _patch_factory_and_db(app_context):
    """Patch SQLiteDataSourceFactory and get_database_path for every test."""
    mock_factory = _mock_factory()
    with patch(
        'presentation.web.utils.SQLiteDataSourceFactory',
        return_value=mock_factory,
    ), patch(
        'presentation.web.utils.get_database_path',
        return_value=':memory:',
    ):
        yield mock_factory


# ---------------------------------------------------------------------------
# _get_user_id
# ---------------------------------------------------------------------------

class TestGetUserId:
    def test_returns_request_user_id(self, app_context):
        assert _get_user_id() == "test_user@example.com"

    def test_raises_without_auth(self, app):
        with app.test_request_context():
            with pytest.raises(RuntimeError, match="without authenticated user"):
                _get_user_id()


# ---------------------------------------------------------------------------
# CategoryService factory
# ---------------------------------------------------------------------------

class TestGetCategoryService:
    def test_creates_instance(self):
        result = get_category_service()
        assert isinstance(result, CategoryService)


# ---------------------------------------------------------------------------
# PatternService factory
# ---------------------------------------------------------------------------

class TestGetPatternService:
    def test_creates_instance(self):
        result = get_pattern_service()
        assert isinstance(result, PatternService)

    def test_reuses_provided_category_service(self):
        cat_svc = MagicMock(spec=CategoryService)
        result = get_pattern_service(category_service=cat_svc)
        assert isinstance(result, PatternService)
        assert result._category_service is cat_svc

    def test_creates_category_service_when_none(self):
        result = get_pattern_service()
        assert isinstance(result, PatternService)
        assert result._category_service is not None


# ---------------------------------------------------------------------------
# UserSettingsService factory
# ---------------------------------------------------------------------------

class TestGetUserSettingsService:
    def test_creates_instance(self):
        result = get_user_settings_service()
        assert isinstance(result, UserSettingsService)


# ---------------------------------------------------------------------------
# TransactionService factory
# ---------------------------------------------------------------------------

class TestGetTransactionService:
    def test_creates_instance(self):
        result = get_transaction_service()
        assert isinstance(result, SlimTransactionService)

    def test_reuses_optional_deps(self):
        cat_svc = MagicMock(spec=CategoryService)
        settings_svc = MagicMock(spec=UserSettingsService)
        result = get_transaction_service(
            category_service=cat_svc,
            user_settings_service=settings_svc,
        )
        assert isinstance(result, SlimTransactionService)
        assert result._category_service is cat_svc
        assert result._user_settings_service is settings_svc

    def test_creates_deps_when_none(self):
        result = get_transaction_service()
        assert isinstance(result, SlimTransactionService)
        assert result._category_service is not None
        assert result._user_settings_service is not None


# ---------------------------------------------------------------------------
# ClassificationService factory
# ---------------------------------------------------------------------------

class TestGetClassificationService:
    @patch('presentation.web.utils.get_sentence_model', return_value=MagicMock())
    def test_creates_instance(self, _mock_model):
        result = get_classification_service()
        assert isinstance(result, ClassificationService)

    def test_skip_similarity(self):
        result = get_classification_service(skip_similarity=True)
        assert isinstance(result, ClassificationService)
        assert result._skip_similarity is True
        assert result._similarity_calculator is None


# ---------------------------------------------------------------------------
# FetcherService factory
# ---------------------------------------------------------------------------

class TestGetFetcherService:
    def test_creates_instance(self):
        result = get_fetcher_service()
        assert isinstance(result, FetcherService)

    def test_reuses_user_settings(self):
        settings_svc = MagicMock(spec=UserSettingsService)
        result = get_fetcher_service(user_settings_service=settings_svc)
        assert isinstance(result, FetcherService)
        assert result._user_settings_service is settings_svc


# ---------------------------------------------------------------------------
# GroupService factory
# ---------------------------------------------------------------------------

class TestGetGroupService:
    def test_creates_instance(self):
        result = get_group_service()
        assert isinstance(result, GroupService)

    def test_reuses_transaction_service(self):
        tx_svc = MagicMock(spec=SlimTransactionService)
        result = get_group_service(transaction_service=tx_svc)
        assert isinstance(result, GroupService)
        assert result._transaction_service is tx_svc


# ---------------------------------------------------------------------------
# Encryption key passthrough
# ---------------------------------------------------------------------------

class TestEncryptionKeyPassthrough:
    def test_encryption_key_passed_to_factory(self, app_context):
        """Verify g.encryption_key is passed through to SQLiteDataSourceFactory."""
        g.encryption_key = "test_base64_key=="

        with patch(
            'presentation.web.utils.SQLiteDataSourceFactory'
        ) as MockFactory, patch(
            'presentation.web.utils.get_database_path',
            return_value=':memory:',
        ):
            MockFactory.return_value = _mock_factory()
            _get_datasource_factory()
            MockFactory.assert_called_once_with(
                ':memory:', 'test_user@example.com', encryption_key='test_base64_key=='
            )

    def test_no_encryption_key_passes_none(self, app_context):
        """Verify None is passed when g.encryption_key is not set."""
        # Ensure no encryption_key on g
        if hasattr(g, 'encryption_key'):
            delattr(g, 'encryption_key')

        with patch(
            'presentation.web.utils.SQLiteDataSourceFactory'
        ) as MockFactory, patch(
            'presentation.web.utils.get_database_path',
            return_value=':memory:',
        ):
            MockFactory.return_value = _mock_factory()
            _get_datasource_factory()
            MockFactory.assert_called_once_with(
                ':memory:', 'test_user@example.com', encryption_key=None
            )

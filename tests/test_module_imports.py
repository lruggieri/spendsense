"""Integration tests for module imports - smoke tests to catch import-time errors."""

import pytest


def test_all_services_importable():
    """Test all service modules can be imported without errors."""
    # Arrange & Act - imports should not raise
    try:
        import application.services.base_service
        import application.services.category_service
        import application.services.classification_service
        import application.services.fetcher_service
        import application.services.group_service
        import application.services.pattern_service
        import application.services.transaction_service
        import application.services.user_settings_service
        import application.services.utils
    except (ImportError, NameError) as e:
        # Assert
        pytest.fail(f"Failed to import service: {e}")


def test_all_blueprints_importable():
    """Test all blueprint modules can be imported without errors."""
    # Arrange & Act
    try:
        import presentation.web.blueprints.auth
        import presentation.web.blueprints.categories
        import presentation.web.blueprints.fetchers
        import presentation.web.blueprints.gmail
        import presentation.web.blueprints.groups
        import presentation.web.blueprints.main
        import presentation.web.blueprints.onboarding
        import presentation.web.blueprints.patterns
        import presentation.web.blueprints.settings
        import presentation.web.blueprints.transactions
    except (ImportError, NameError) as e:
        # Assert
        pytest.fail(f"Failed to import blueprint: {e}")


def test_all_abstract_datasources_importable():
    """Test all abstract repository interfaces can be imported."""
    # Arrange & Act
    try:
        import domain.repositories.category_repository
        import domain.repositories.embedding_repository
        import domain.repositories.fetcher_repository
        import domain.repositories.group_repository
        import domain.repositories.manual_assignment_repository
        import domain.repositories.regexp_repository
        import domain.repositories.session_repository
        import domain.repositories.transaction_repository
        import domain.repositories.user_settings_repository
        import infrastructure.persistence.factory
    except (ImportError, NameError) as e:
        # Assert
        pytest.fail(f"Failed to import abstract repository: {e}")


def test_all_sqlite_datasources_importable():
    """Test all SQLite datasource implementations can be imported."""
    # Arrange & Act
    try:
        import infrastructure.persistence.sqlite.factory
        import infrastructure.persistence.sqlite.repositories.category_repository
        import infrastructure.persistence.sqlite.repositories.embedding_repository
        import infrastructure.persistence.sqlite.repositories.fetcher_repository
        import infrastructure.persistence.sqlite.repositories.group_repository
        import infrastructure.persistence.sqlite.repositories.manual_assignment_repository
        import infrastructure.persistence.sqlite.repositories.regexp_repository
        import infrastructure.persistence.sqlite.repositories.session_repository
        import infrastructure.persistence.sqlite.repositories.transaction_repository
        import infrastructure.persistence.sqlite.repositories.user_settings_repository
    except (ImportError, NameError) as e:
        # Assert
        pytest.fail(f"Failed to import SQLite datasource: {e}")


def test_frontend_utils_importable():
    """Test frontend.utils module can be imported without errors."""
    # Arrange & Act
    try:
        import presentation.web.utils
    except (ImportError, NameError) as e:
        # Assert
        pytest.fail(f"Failed to import frontend.utils: {e}")


def test_frontend_decorators_importable():
    """Test frontend.decorators module can be imported without errors."""
    # Arrange & Act
    try:
        import presentation.web.decorators
    except (ImportError, NameError) as e:
        # Assert
        pytest.fail(f"Failed to import frontend.decorators: {e}")


def test_frontend_extensions_importable():
    """Test frontend.extensions module can be imported without errors."""
    # Arrange & Act
    try:
        import presentation.web.extensions
    except (ImportError, NameError) as e:
        # Assert
        pytest.fail(f"Failed to import frontend.extensions: {e}")


def test_service_type_hints_dont_cause_nameerror():
    """Test that type hints in services don't cause NameError on import."""
    # This specifically tests for Error #1: type hint NameError
    # Services should import without NameError even if type hints reference other modules

    # Arrange & Act
    try:
        # Import services that use type hints
        from application.services.classification_service import ClassificationService
        from application.services.group_service import GroupService
        from application.services.transaction_service import TransactionService

        # If we got here, type hints are valid
        assert ClassificationService is not None
        assert TransactionService is not None
        assert GroupService is not None

    except NameError as e:
        # Assert
        pytest.fail(f"Type hint caused NameError on import: {e}")


def test_factory_functions_importable():
    """Test that all factory functions can be imported."""
    # Arrange & Act
    try:
        from presentation.web.utils import (
            get_category_service,
            get_classification_service,
            get_fetcher_service,
            get_group_service,
            get_pattern_service,
            get_transaction_service,
            get_user_settings_service,
        )

        # Assert - Functions are callable
        assert callable(get_category_service)
        assert callable(get_pattern_service)
        assert callable(get_user_settings_service)
        assert callable(get_transaction_service)
        assert callable(get_classification_service)
        assert callable(get_fetcher_service)
        assert callable(get_group_service)

    except (ImportError, NameError) as e:
        pytest.fail(f"Failed to import factory function: {e}")


def test_no_circular_import_in_services():
    """Test that importing services doesn't cause circular import errors."""
    # Arrange & Act
    try:
        # Import all services at once - would fail if circular imports exist
        from application.services import (
            CategoryService,
            ClassificationService,
            FetcherService,
            GroupService,
            PatternService,
            TransactionService,
            UserSettingsService,
        )

        # Assert
        assert all(
            [
                CategoryService,
                PatternService,
                UserSettingsService,
                TransactionService,
                ClassificationService,
                FetcherService,
                GroupService,
            ]
        )

    except ImportError as e:
        if "circular import" in str(e).lower():
            pytest.fail(f"Circular import detected: {e}")
        else:
            pytest.fail(f"Import error: {e}")


def test_entity_classes_importable():
    """Test that entity classes can be imported."""
    # Arrange & Act
    try:
        from domain.entities.category import Category
        from domain.entities.fetcher import Fetcher
        from domain.entities.group import Group
        from domain.entities.regexp import Regexp
        from domain.entities.session import Session
        from domain.entities.transaction import Transaction

        # Assert
        assert all([Transaction, Category, Regexp, Session, Fetcher, Group])

    except (ImportError, NameError) as e:
        pytest.fail(f"Failed to import entity class: {e}")


def test_logic_modules_importable():
    """Test that domain service modules can be imported."""
    # Arrange & Act
    try:
        import domain.services.amount_utils
        import domain.services.classifier
        import domain.services.embedding_similarity_calculator

        # Assert
        assert domain.services.classifier is not None
        assert domain.services.embedding_similarity_calculator is not None
        assert domain.services.amount_utils is not None

    except (ImportError, NameError) as e:
        pytest.fail(f"Failed to import domain service module: {e}")

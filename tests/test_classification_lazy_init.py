"""Tests for ClassificationService lazy initialization of the classifier."""

from unittest.mock import MagicMock, patch

import pytest

from application.services.classification_service import ClassificationService


@pytest.fixture
def mock_datasources():
    """Return mock datasources needed by ClassificationService."""
    manual = MagicMock()
    regexp = MagicMock()
    regexp.get_all_regexps.return_value = []
    embedding = MagicMock()
    return manual, regexp, embedding


@pytest.fixture
def service(mock_datasources):
    """Create a ClassificationService with skip_similarity=True (no ML model)."""
    manual, regexp, embedding = mock_datasources
    return ClassificationService(
        user_id="test@example.com",
        manual_assignment_datasource=manual,
        regexp_datasource=regexp,
        embedding_datasource=embedding,
        db_path=":memory:",
        skip_similarity=True,
    )


class TestClassifierNotInitializedOnCreation:
    def test_classifier_is_none_after_init(self, service):
        assert service._classifier is None


class TestClassifierLazyInit:
    def test_lazily_initialized_on_classify(self, service):
        assert service._classifier is None
        service.classify("tx1", "some description")
        assert service._classifier is not None

    def test_lazily_initialized_on_classify_batch(self, service):
        assert service._classifier is None
        service.classify_batch([("tx1", "desc1"), ("tx2", "desc2")])
        assert service._classifier is not None


class TestClassifierCaching:
    def test_cached_after_first_init(self, service):
        service.classify("tx1", "description")
        first_classifier = service._classifier

        service.classify("tx2", "other description")
        assert service._classifier is first_classifier


class TestReloadPatterns:
    def test_resets_and_reinits_classifier(self, service):
        service.classify("tx1", "description")
        first_classifier = service._classifier
        assert first_classifier is not None

        service.reload_patterns()
        assert service._classifier is not first_classifier
        assert service._classifier is not None


class TestSkipSimilarity:
    def test_prevents_similarity_calculator_creation(self, mock_datasources):
        manual, regexp, embedding = mock_datasources
        svc = ClassificationService(
            user_id="test@example.com",
            manual_assignment_datasource=manual,
            regexp_datasource=regexp,
            embedding_datasource=embedding,
            db_path=":memory:",
            skip_similarity=True,
        )
        svc.classify("tx1", "description")
        # The classifier's similarity_calculator should be None
        assert svc._classifier.similarity_calculator is None

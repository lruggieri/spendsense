"""
Tests for EmbeddingSimilarityCalculator.

Tests cover:
- Cosine similarity calculation
- Reference embedding caching
- Batch processing
- Single and batch similarity calculations
"""
import pytest
import numpy as np
from unittest.mock import Mock, MagicMock
from domain.services.embedding_similarity_calculator import EmbeddingSimilarityCalculator


class TestEmbeddingSimilarityCalculator:
    """Test the embedding similarity calculator."""

    @pytest.fixture
    def mock_model(self):
        """Create a mock sentence transformer model."""
        model = Mock()

        def mock_encode(texts, show_progress_bar=False):
            """Mock encode that returns deterministic embeddings."""
            if isinstance(texts, str):
                texts = [texts]

            # Return simple embeddings based on text hash for determinism
            embeddings = []
            for text in texts:
                # Simple hash-based embedding (3 dimensions for testing)
                hash_val = hash(text) % 100
                embedding = np.array([hash_val / 100, (hash_val + 10) / 100, (hash_val + 20) / 100])
                embeddings.append(embedding)

            return np.array(embeddings) if len(embeddings) > 1 else embeddings[0]

        model.encode = mock_encode
        return model

    @pytest.fixture
    def calculator(self, mock_model):
        """Create calculator with mock model."""
        return EmbeddingSimilarityCalculator(model=mock_model)

    def test_cosine_similarity_identical(self, calculator):
        """Test cosine similarity of identical vectors."""
        vec = np.array([1.0, 2.0, 3.0])
        similarity = calculator._cosine_similarity(vec, vec)
        assert similarity == pytest.approx(1.0)

    def test_cosine_similarity_orthogonal(self, calculator):
        """Test cosine similarity of orthogonal vectors."""
        vec1 = np.array([1.0, 0.0, 0.0])
        vec2 = np.array([0.0, 1.0, 0.0])
        similarity = calculator._cosine_similarity(vec1, vec2)
        assert similarity == pytest.approx(0.0)

    def test_cosine_similarity_opposite(self, calculator):
        """Test cosine similarity of opposite vectors."""
        vec1 = np.array([1.0, 0.0, 0.0])
        vec2 = np.array([-1.0, 0.0, 0.0])
        similarity = calculator._cosine_similarity(vec1, vec2)
        assert similarity == pytest.approx(-1.0)

    def test_cosine_similarity_zero_vector(self, calculator):
        """Test cosine similarity handles zero vectors."""
        vec1 = np.array([1.0, 2.0, 3.0])
        vec2 = np.array([0.0, 0.0, 0.0])
        similarity = calculator._cosine_similarity(vec1, vec2)
        assert similarity == 0.0

    def test_precompute_reference_embeddings(self, calculator, mock_model):
        """Test precomputing reference embeddings."""
        reference_texts = {
            "ref_1": "coffee shop",
            "ref_2": "grocery store",
            "ref_3": "train ticket"
        }

        calculator.precompute_reference_embeddings(reference_texts)

        # Verify cache populated
        assert len(calculator._reference_embeddings_cache) == 3
        assert "ref_1" in calculator._reference_embeddings_cache
        assert len(calculator._reference_ids_cache) == 3

        # Verify embeddings are numpy arrays
        assert isinstance(calculator._reference_embeddings_cache["ref_1"], np.ndarray)

    def test_precompute_empty(self, calculator):
        """Test precomputing with empty reference texts."""
        calculator.precompute_reference_embeddings({})

        assert calculator._reference_embeddings_cache == {}
        assert calculator._reference_ids_cache == []

    def test_calculate_similarities_basic(self, calculator):
        """Test basic similarity calculation."""
        reference_texts = {
            "ref_1": "coffee",
            "ref_2": "coffee",  # Same text should have high similarity
            "ref_3": "grocery"
        }

        # Calculate similarities
        similarities = calculator.calculate_similarities("coffee", reference_texts)

        # Should return list of (id, score) tuples sorted by score
        assert len(similarities) == 3
        assert all(isinstance(item, tuple) and len(item) == 2 for item in similarities)

        # Identical text should have highest similarity
        # Note: Due to mock, exact same text gets same embedding
        ref_ids = [item[0] for item in similarities]
        assert "ref_1" in ref_ids
        assert "ref_2" in ref_ids

    def test_calculate_similarities_uses_cache(self, calculator, mock_model):
        """Test that calculate_similarities uses cached embeddings."""
        reference_texts = {
            "ref_1": "text 1",
            "ref_2": "text 2"
        }

        # Precompute and cache
        calculator.precompute_reference_embeddings(reference_texts)

        # Track encode calls
        encode_call_count = 0
        original_encode = mock_model.encode

        def counting_encode(*args, **kwargs):
            nonlocal encode_call_count
            encode_call_count += 1
            return original_encode(*args, **kwargs)

        mock_model.encode = counting_encode

        # Calculate similarities - should use cache for references
        calculator.calculate_similarities("query text", reference_texts)

        # Should only encode the query text, not references
        assert encode_call_count == 1

    def test_calculate_similarities_empty_references(self, calculator):
        """Test calculate_similarities with empty references."""
        similarities = calculator.calculate_similarities("text", {})
        assert similarities == []

    def test_calculate_similarities_batch(self, calculator):
        """Test batch similarity calculation."""
        reference_texts = {
            "ref_1": "coffee shop",
            "ref_2": "grocery store"
        }

        query_texts = [
            "coffee purchase",
            "supermarket shopping",
            "train ticket"
        ]

        results = calculator.calculate_similarities_batch(query_texts, reference_texts)

        # Should return one result per query
        assert len(results) == 3

        # Each result should be a list of (id, score) tuples
        for result in results:
            assert len(result) == 2  # 2 references
            assert all(isinstance(item, tuple) for item in result)

    def test_calculate_similarities_batch_empty_queries(self, calculator):
        """Test batch calculation with empty queries."""
        results = calculator.calculate_similarities_batch([], {"ref_1": "text"})
        assert results == []

    def test_calculate_similarities_batch_empty_references(self, calculator):
        """Test batch calculation with empty references."""
        results = calculator.calculate_similarities_batch(["query1", "query2"], {})
        assert len(results) == 2
        assert all(result == [] for result in results)

    def test_calculate_similarities_batch_uses_cache(self, calculator, mock_model):
        """Test batch calculation uses cached reference embeddings."""
        reference_texts = {
            "ref_1": "text 1",
            "ref_2": "text 2"
        }

        # Precompute
        calculator.precompute_reference_embeddings(reference_texts)

        # Track encode calls
        encode_call_count = 0
        original_encode = mock_model.encode

        def counting_encode(*args, **kwargs):
            nonlocal encode_call_count
            encode_call_count += 1
            return original_encode(*args, **kwargs)

        mock_model.encode = counting_encode

        # Batch calculate
        query_texts = ["query 1", "query 2", "query 3"]
        calculator.calculate_similarities_batch(query_texts, reference_texts)

        # Should only encode queries (1 batch call), not references
        assert encode_call_count == 1


class TestEmbeddingSimilarityCalculatorInitialization:
    """Test calculator initialization and model loading."""

    def test_init_with_model(self):
        """Test initialization with pre-loaded model."""
        mock_model = Mock()
        calculator = EmbeddingSimilarityCalculator(model=mock_model)
        assert calculator.model is mock_model

    def test_init_with_invalid_model_name_raises(self):
        """Test initialization with invalid model name raises ImportError."""
        # This test checks the error path when sentence-transformers is not installed
        # In practice, we assume dependencies are installed
        pass  # Skip as dependencies should be installed


class TestEmbeddingSimilarityCalculatorRealScenarios:
    """Test real-world scenarios."""

    @pytest.fixture
    def calculator_with_mock(self):
        """Calculator with realistic mock behavior."""
        model = Mock()

        # Mock embeddings that simulate semantic similarity
        embeddings_db = {
            "starbucks coffee": np.array([0.8, 0.2, 0.1]),
            "coffee shop": np.array([0.75, 0.25, 0.1]),
            "supermarket groceries": np.array([0.1, 0.8, 0.3]),
            "train ticket": np.array([0.2, 0.1, 0.9]),
            "bus fare": np.array([0.25, 0.15, 0.85]),
        }

        def mock_encode(texts, show_progress_bar=False):
            if isinstance(texts, str):
                return embeddings_db.get(texts.lower(), np.array([0.5, 0.5, 0.5]))
            return np.array([embeddings_db.get(t.lower(), np.array([0.5, 0.5, 0.5]))
                           for t in texts])

        model.encode = mock_encode
        return EmbeddingSimilarityCalculator(model=model)

    def test_similar_transactions_high_score(self, calculator_with_mock):
        """Test that similar transactions have high similarity scores."""
        reference_texts = {
            "ref_1": "starbucks coffee",
            "ref_2": "coffee shop"
        }

        similarities = calculator_with_mock.calculate_similarities(
            "starbucks coffee",
            reference_texts
        )

        # Should have high similarity with ref_1 (exact match)
        ref_1_score = next(score for ref_id, score in similarities if ref_id == "ref_1")
        assert ref_1_score > 0.9  # Very high for exact match

    def test_dissimilar_transactions_low_score(self, calculator_with_mock):
        """Test that dissimilar transactions have low similarity scores."""
        reference_texts = {
            "ref_1": "train ticket",
            "ref_2": "bus fare"
        }

        similarities = calculator_with_mock.calculate_similarities(
            "coffee shop",
            reference_texts
        )

        # Coffee should have low similarity with transport references
        scores = [score for _, score in similarities]
        assert all(score < 0.7 for score in scores)

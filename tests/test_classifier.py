"""
Comprehensive tests for the Classifier classification logic.

Tests cover:
- Manual assignment priority (highest)
- Regex-based classification (medium)
- Similarity-based classification (fallback)
- Batch processing
- CategorySource tracking
- Priority order enforcement
"""
import re
import pytest
from unittest.mock import Mock
from domain.services.classifier import Classifier
from domain.entities.transaction import CategorySource


class TestClassifierRegexOnly:
    """Test classifier with regex patterns only (no manual/similarity)."""

    @pytest.fixture
    def classifier(self):
        """Create classifier with basic regex patterns."""
        regexps = [
            ("food", re.compile(r"(LAWSON|MARUETSU|FAMILYMART)", re.IGNORECASE)),
            ("transport", re.compile(r"(TRAIN|BUS|TAXI)", re.IGNORECASE)),
            ("entertainment", re.compile(r"(CINEMA|THEATER|NETFLIX)", re.IGNORECASE)),
        ]
        return Classifier(regexps)

    def test_regex_match(self, classifier):
        """Test basic regex matching."""
        category, source = classifier.classify("tx_1", "LAWSON Store Purchase")
        assert category == "food"
        assert source == CategorySource.REGEXP

    def test_regex_case_insensitive(self, classifier):
        """Test regex patterns are case-insensitive."""
        category, source = classifier.classify("tx_2", "lawson convenience store")
        assert category == "food"
        assert source == CategorySource.REGEXP

    def test_regex_no_match(self, classifier):
        """Test transaction with no regex match."""
        category, source = classifier.classify("tx_3", "Unknown merchant")
        assert category is None
        assert source is None

    def test_regex_first_match_wins(self, classifier):
        """Test that first matching regex wins."""
        # This would match multiple patterns, first one wins
        regexps = [
            ("category_a", re.compile(r"TEST")),
            ("category_b", re.compile(r"TEST")),
        ]
        classifier = Classifier(regexps)
        category, source = classifier.classify("tx_4", "TEST description")
        assert category == "category_a"

    def test_regex_multiple_transactions(self, classifier):
        """Test classifying multiple different transactions."""
        transactions = [
            ("tx_1", "Bought lunch at LAWSON"),
            ("tx_2", "Took TRAIN to work"),
            ("tx_3", "Watched movie at CINEMA"),
            ("tx_4", "Unknown merchant"),
        ]

        results = {
            tx_id: classifier.classify(tx_id, desc)
            for tx_id, desc in transactions
        }

        assert results["tx_1"] == ("food", CategorySource.REGEXP)
        assert results["tx_2"] == ("transport", CategorySource.REGEXP)
        assert results["tx_3"] == ("entertainment", CategorySource.REGEXP)
        assert results["tx_4"] == (None, None)


class TestClassifierManualAssignments:
    """Test classifier with manual assignments (highest priority)."""

    @pytest.fixture
    def mock_datasource(self):
        """Create mock manual assignment datasource."""
        datasource = Mock()
        datasource.get_assignments.return_value = {
            "tx_manual_1": "groceries",
            "tx_manual_2": "utilities",
            "tx_manual_3": "coffee",
        }
        return datasource

    @pytest.fixture
    def classifier(self, mock_datasource):
        """Create classifier with manual assignments and regex."""
        regexps = [
            ("food", re.compile(r"LAWSON", re.IGNORECASE)),
            ("transport", re.compile(r"TRAIN", re.IGNORECASE)),
        ]
        return Classifier(regexps, manual_assignment_source=mock_datasource)

    def test_manual_assignment_priority(self, classifier):
        """Test manual assignment takes priority over regex."""
        # Set descriptions (required for similarity)
        classifier.set_manual_descriptions({
            "tx_manual_1": "LAWSON grocery shopping",
            "tx_manual_2": "Electric bill payment",
            "tx_manual_3": "Starbucks coffee",
        })

        # tx_manual_1 has "LAWSON" which matches food regex,
        # but manual assignment should win
        category, source = classifier.classify("tx_manual_1", "LAWSON grocery shopping")
        assert category == "groceries"
        assert source == CategorySource.MANUAL

    def test_manual_assignment_direct(self, classifier):
        """Test direct manual assignment classification."""
        category, source = classifier.classify("tx_manual_2", "Any description")
        assert category == "utilities"
        assert source == CategorySource.MANUAL

    def test_non_manual_falls_to_regex(self, classifier):
        """Test non-manual transaction falls through to regex."""
        category, source = classifier.classify("tx_other", "Took TRAIN to work")
        assert category == "transport"
        assert source == CategorySource.REGEXP

    def test_manual_assignment_count(self, classifier):
        """Test that manual assignments are loaded correctly."""
        assert len(classifier.manual_assignments) == 3
        assert "tx_manual_1" in classifier.manual_assignments
        assert classifier.manual_assignments["tx_manual_1"] == "groceries"


class TestClassifierSimilarity:
    """Test classifier with similarity-based classification."""

    @pytest.fixture
    def mock_datasource(self):
        """Create mock manual assignment datasource."""
        datasource = Mock()
        # Reference transactions that will be used for similarity matching
        datasource.get_assignments.return_value = {
            "ref_1": "coffee",
            "ref_2": "coffee",
            "ref_3": "groceries",
            "ref_4": "transport",
            "ref_5": "transport",
        }
        return datasource

    @pytest.fixture
    def mock_similarity_calculator(self):
        """Create mock similarity calculator."""
        calc = Mock()

        def mock_calculate_similarities(text, reference_texts):
            """Mock similarity calculation - perfect matches only."""
            similarities = []
            for ref_id, ref_text in reference_texts.items():
                # Simple mock: exact match = 1.0, contains = 0.8, else = 0.0
                if text.lower() == ref_text.lower():
                    similarities.append((ref_id, 1.0))
                elif text.lower() in ref_text.lower() or ref_text.lower() in text.lower():
                    similarities.append((ref_id, 0.8))
                else:
                    similarities.append((ref_id, 0.0))
            return sorted(similarities, key=lambda x: x[1], reverse=True)

        calc.calculate_similarities = mock_calculate_similarities

        def mock_precompute(reference_texts):
            """Mock precompute - no-op for testing."""
            pass

        calc.precompute_reference_embeddings = mock_precompute

        return calc

    @pytest.fixture
    def classifier(self, mock_datasource, mock_similarity_calculator):
        """Create classifier with similarity calculator."""
        regexps = [
            ("food_regex", re.compile(r"LAWSON", re.IGNORECASE)),
        ]
        return Classifier(
            regexps,
            manual_assignment_source=mock_datasource,
            similarity_calculator=mock_similarity_calculator,
            similarity_threshold=0.7
        )

    def test_similarity_classification(self, classifier):
        """Test similarity-based classification."""
        # Set reference descriptions
        classifier.set_manual_descriptions({
            "ref_1": "Starbucks coffee",
            "ref_2": "Coffee shop purchase",
            "ref_3": "Supermarket groceries",
            "ref_4": "Train ticket",
            "ref_5": "Bus fare",
        })

        # This should match "Starbucks coffee" and "Coffee shop purchase"
        category, source = classifier.classify("new_tx", "Starbucks coffee")
        assert category == "coffee"
        assert source == CategorySource.SIMILARITY

    def test_similarity_majority_vote(self, classifier):
        """Test majority voting in similarity classification."""
        classifier.set_manual_descriptions({
            "ref_1": "Starbucks",
            "ref_2": "Starbucks",
            "ref_3": "Supermarket",
            "ref_4": "Train",
            "ref_5": "Train",
        })

        # Should match multiple, majority wins
        category, source = classifier.classify("new_tx", "Train")
        assert category == "transport"
        assert source == CategorySource.SIMILARITY

    def test_similarity_below_threshold(self, classifier):
        """Test similarity below threshold returns None."""
        classifier.set_manual_descriptions({
            "ref_1": "Completely different text",
            "ref_2": "Nothing similar here",
        })

        # No similar transactions above threshold (0.7)
        category, source = classifier.classify("new_tx", "Unrelated description")
        assert category is None
        assert source is None

    def test_similarity_priority_below_regex(self, classifier):
        """Test that regex takes priority over similarity."""
        classifier.set_manual_descriptions({
            "ref_1": "LAWSON store",
            "ref_2": "LAWSON purchase",
        })

        # "LAWSON" matches regex for "food_regex", should use regex not similarity
        category, source = classifier.classify("new_tx", "LAWSON store")
        assert category == "food_regex"
        assert source == CategorySource.REGEXP


class TestClassifierBatchProcessing:
    """Test batch processing for performance."""

    @pytest.fixture
    def mock_datasource(self):
        """Create mock datasource."""
        datasource = Mock()
        datasource.get_assignments.return_value = {
            "manual_1": "coffee",
            "manual_2": "groceries",
        }
        return datasource

    @pytest.fixture
    def mock_similarity_calculator(self):
        """Create mock batch similarity calculator."""
        calc = Mock()

        def mock_batch_similarities(texts, reference_texts, text_ids=None):
            """Mock batch similarity calculation."""
            results = []
            for text in texts:
                similarities = []
                for ref_id, ref_text in reference_texts.items():
                    # Check for substring match (case insensitive)
                    text_lower = text.lower()
                    ref_text_lower = ref_text.lower()

                    # Word-based similarity for testing
                    text_words = set(text_lower.split())
                    ref_words = set(ref_text_lower.split())
                    common_words = text_words & ref_words

                    if text_lower == ref_text_lower:
                        score = 1.0  # Exact match
                    elif text_lower in ref_text_lower or ref_text_lower in text_lower:
                        score = 0.9  # Substring match
                    elif common_words:
                        # Word overlap - score based on overlap ratio
                        score = 0.7 + (0.2 * len(common_words) / max(len(text_words), len(ref_words)))
                    else:
                        score = 0.0  # No match

                    similarities.append((ref_id, score))
                results.append(sorted(similarities, key=lambda x: x[1], reverse=True))
            return results

        calc.calculate_similarities_batch = Mock(side_effect=mock_batch_similarities)
        calc.precompute_reference_embeddings = Mock()
        return calc

    @pytest.fixture
    def classifier(self, mock_datasource, mock_similarity_calculator):
        """Create classifier for batch testing."""
        regexps = [
            ("food", re.compile(r"LAWSON", re.IGNORECASE)),
            ("transport", re.compile(r"TRAIN", re.IGNORECASE)),
        ]
        classifier = Classifier(
            regexps,
            manual_assignment_source=mock_datasource,
            similarity_calculator=mock_similarity_calculator,
            similarity_threshold=0.7
        )
        classifier.set_manual_descriptions({
            "manual_1": "Starbucks coffee",
            "manual_2": "Supermarket",
        })
        return classifier

    def test_batch_classify_mixed(self, classifier):
        """Test batch classification with mixed sources."""
        transactions = [
            ("manual_1", "Starbucks coffee"),      # Manual
            ("tx_2", "LAWSON store"),              # Regex
            ("tx_3", "TRAIN ticket"),              # Regex
            ("tx_4", "coffee shop"),               # Similarity
            ("tx_5", "Random merchant"),           # None
        ]

        results = classifier.classify_batch(transactions)

        assert results["manual_1"] == ("coffee", CategorySource.MANUAL)
        assert results["tx_2"] == ("food", CategorySource.REGEXP)
        assert results["tx_3"] == ("transport", CategorySource.REGEXP)
        assert results["tx_4"] == ("coffee", CategorySource.SIMILARITY)
        assert results["tx_5"] == (None, None)

    def test_batch_classify_all_manual(self, classifier):
        """Test batch with all manual assignments."""
        transactions = [
            ("manual_1", "Any description"),
            ("manual_2", "Any description"),
        ]

        results = classifier.classify_batch(transactions)

        assert all(source == CategorySource.MANUAL for _, source in results.values())

    def test_batch_classify_empty(self, classifier):
        """Test batch classification with empty list."""
        results = classifier.classify_batch([])
        assert results == {}

    def test_batch_performance_mock(self, classifier, mock_similarity_calculator):
        """Test that batch processing uses batch similarity calculation."""
        transactions = [
            ("tx_1", "description 1"),
            ("tx_2", "description 2"),
            ("tx_3", "description 3"),
        ]

        classifier.classify_batch(transactions)

        # Verify batch method was called (not individual calls)
        assert mock_similarity_calculator.calculate_similarities_batch.called


class TestClassifierPriorityOrder:
    """Test that classification priority order is enforced correctly."""

    @pytest.fixture
    def mock_datasource(self):
        """Create mock datasource."""
        datasource = Mock()
        datasource.get_assignments.return_value = {"manual_tx": "manual_category"}
        return datasource

    @pytest.fixture
    def mock_similarity_calculator(self):
        """Create mock similarity calculator."""
        calc = Mock()
        calc.calculate_similarities.return_value = [("manual_tx", 0.9)]
        calc.precompute_reference_embeddings = Mock()
        return calc

    def test_priority_manual_over_regex(self, mock_datasource, mock_similarity_calculator):
        """Test manual assignment beats regex."""
        regexps = [
            ("regex_match", re.compile(r"MATCH")),
        ]
        classifier = Classifier(
            regexps,
            manual_assignment_source=mock_datasource,
            similarity_calculator=mock_similarity_calculator,
            similarity_threshold=0.7
        )
        classifier.set_manual_descriptions({"manual_tx": "MATCH in description"})

        # Description contains "MATCH" but manual should win
        category, source = classifier.classify("manual_tx", "MATCH in description")
        assert category == "manual_category"
        assert source == CategorySource.MANUAL

    def test_priority_manual_over_similarity(self, mock_datasource, mock_similarity_calculator):
        """Test manual assignment beats similarity."""
        classifier = Classifier(
            [],
            manual_assignment_source=mock_datasource,
            similarity_calculator=mock_similarity_calculator,
            similarity_threshold=0.7
        )
        classifier.set_manual_descriptions({"manual_tx": "Similar description"})

        # Would match via similarity but manual should win
        category, source = classifier.classify("manual_tx", "Similar description")
        assert category == "manual_category"
        assert source == CategorySource.MANUAL

    def test_priority_regex_over_similarity(self, mock_datasource, mock_similarity_calculator):
        """Test regex beats similarity."""
        regexps = [
            ("regex_category", re.compile(r"REGEX")),
        ]
        classifier = Classifier(
            regexps,
            manual_assignment_source=mock_datasource,
            similarity_calculator=mock_similarity_calculator,
            similarity_threshold=0.7
        )
        classifier.set_manual_descriptions({"manual_tx": "REGEX pattern"})

        # Non-manual transaction with regex match
        category, source = classifier.classify("other_tx", "REGEX pattern match")
        assert category == "regex_category"
        assert source == CategorySource.REGEXP


class TestClassifierEdgeCases:
    """Test edge cases and error handling."""

    def test_classifier_no_regexps(self):
        """Test classifier with empty regex list."""
        classifier = Classifier([])
        category, source = classifier.classify("tx_1", "Any description")
        assert category is None
        assert source is None

    def test_classifier_no_manual_datasource(self):
        """Test classifier without manual assignment datasource."""
        regexps = [("food", re.compile(r"LAWSON"))]
        classifier = Classifier(regexps, manual_assignment_source=None)
        assert classifier.manual_assignments == {}

    def test_classifier_no_similarity_calculator(self):
        """Test classifier without similarity calculator."""
        regexps = [("food", re.compile(r"LAWSON"))]
        classifier = Classifier(regexps, similarity_calculator=None)

        # Should fall back to None for non-matching transactions
        category, source = classifier.classify("tx_1", "Unknown")
        assert category is None
        assert source is None

    def test_empty_description(self):
        """Test classification with empty description."""
        regexps = [("food", re.compile(r"LAWSON"))]
        classifier = Classifier(regexps)
        category, source = classifier.classify("tx_1", "")
        assert category is None
        assert source is None

    def test_set_manual_descriptions_filters(self):
        """Test that set_manual_descriptions only includes assigned transactions."""
        mock_datasource = Mock()
        mock_datasource.get_assignments.return_value = {"tx_1": "food", "tx_2": "transport"}

        classifier = Classifier([], manual_assignment_source=mock_datasource)

        # Pass descriptions including non-assigned transactions
        all_descriptions = {
            "tx_1": "Description 1",
            "tx_2": "Description 2",
            "tx_3": "Description 3",  # Not in manual assignments
        }

        classifier.set_manual_descriptions(all_descriptions)

        # Should only include tx_1 and tx_2
        assert len(classifier.manual_descriptions) == 2
        assert "tx_1" in classifier.manual_descriptions
        assert "tx_2" in classifier.manual_descriptions
        assert "tx_3" not in classifier.manual_descriptions

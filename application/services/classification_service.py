"""
Classification service for transaction categorization.

Orchestrates the full classification pipeline including manual assignments,
regex patterns, and similarity-based classification.
"""

import re
import logging
from typing import Dict, List, Tuple, Optional

from application.services.base_service import BaseService
from domain.repositories.manual_assignment_repository import ManualAssignmentRepository
from domain.repositories.regexp_repository import RegexpRepository
from domain.repositories.embedding_repository import EmbeddingRepository
from domain.services.classifier import Classifier
from domain.services.embedding_similarity_calculator import EmbeddingSimilarityCalculator
from domain.entities.transaction import Transaction, CategorySource, ENCRYPTED_PLACEHOLDER

logger = logging.getLogger(__name__)


class ClassificationService(BaseService):
    """
    Service for classifying transactions into categories.

    Manages the classification pipeline with lazy initialization.
    Supports three classification methods:
    1. Manual assignments (highest priority)
    2. Regex patterns
    3. Similarity-based (fallback)
    """

    def __init__(self, user_id: str,
                 manual_assignment_datasource: ManualAssignmentRepository,
                 regexp_datasource: RegexpRepository,
                 embedding_datasource: EmbeddingRepository,
                 db_path: str = None,
                 similarity_calculator: Optional[EmbeddingSimilarityCalculator] = None,
                 skip_similarity: bool = False):
        """
        Initialize ClassificationService.

        Args:
            user_id: User ID for data isolation
            manual_assignment_datasource: Manual assignment datasource implementation
            regexp_datasource: Regexp datasource implementation
            embedding_datasource: Embedding datasource implementation
            db_path: Optional database path
            similarity_calculator: Optional pre-initialized similarity calculator
            skip_similarity: If True, skip similarity-based classification
        """
        super().__init__(user_id, db_path)
        self._manual_datasource = manual_assignment_datasource
        self._regexp_datasource = regexp_datasource
        self._embedding_datasource = embedding_datasource
        self._similarity_calculator = similarity_calculator
        self._skip_similarity = skip_similarity
        self._classifier: Optional[Classifier] = None

    def _get_classifier(self) -> Classifier:
        """
        Get or create the classifier instance (lazy initialization).

        Returns:
            Classifier instance
        """
        if self._classifier is None:
            self._initialize_classifier()
        return self._classifier

    def _initialize_classifier(self):
        """Initialize the classifier with all necessary components."""
        # Load regex patterns from database
        regexps_raw = self._regexp_datasource.get_all_regexps()

        # Determine similarity calculator
        if self._skip_similarity:
            similarity_calc = None
            logger.debug("Skipping similarity calculator (disabled)")
        elif self._similarity_calculator is not None:
            similarity_calc = self._similarity_calculator
            logger.debug("Using provided similarity calculator")
        else:
            # Create a new calculator (will load model)
            similarity_calc = EmbeddingSimilarityCalculator(
                embedding_datasource=self._embedding_datasource
            )
            logger.debug("Created new similarity calculator")

        # Create classifier
        self._classifier = Classifier(
            [(regexp.internal_category, re.compile(regexp.raw, re.IGNORECASE)) for regexp in regexps_raw],
            manual_assignment_source=self._manual_datasource,
            similarity_calculator=similarity_calc,
            similarity_threshold=0.7
        )

    @property
    def classifier(self) -> Classifier:
        """Get the classifier instance."""
        return self._get_classifier()

    @property
    def embedding_datasource(self) -> Optional[EmbeddingRepository]:
        """Get the embedding datasource (for cache invalidation)."""
        # Ensure classifier is initialized
        self._get_classifier()
        return self._embedding_datasource

    def classify(self, tx_id: str, description: str) -> Tuple[str, CategorySource]:
        """
        Classify a single transaction.

        Args:
            tx_id: Transaction ID
            description: Transaction description

        Returns:
            Tuple of (category_id, CategorySource)
        """
        classifier = self._get_classifier()
        return classifier.classify(tx_id, description)

    def classify_batch(self, transactions: List[Tuple[str, str]]) -> Dict[str, Tuple[str, CategorySource]]:
        """
        Classify multiple transactions in a batch.

        Args:
            transactions: List of (tx_id, description) tuples

        Returns:
            Dictionary mapping tx_id to (category_id, CategorySource)
        """
        classifier = self._get_classifier()
        return classifier.classify_batch(transactions)

    def classify_transactions(self, transactions: Dict[str, Transaction]) -> Dict[str, Transaction]:
        """
        Classify all transactions in a dictionary and update their categories.

        Encrypted transactions whose descriptions are still the placeholder
        ``[Encrypted]`` are skipped entirely — no classification is applied.
        Their category and source are set to None.

        Args:
            transactions: Dictionary of tx_id -> Transaction

        Returns:
            Same dictionary with categories updated
        """
        classifier = self._get_classifier()

        # Partition: encrypted placeholders vs classifiable
        classifiable: Dict[str, Transaction] = {}
        encrypted_placeholders: Dict[str, Transaction] = {}

        for tx_id, tx in transactions.items():
            if tx.encrypted and tx.description == ENCRYPTED_PLACEHOLDER:
                encrypted_placeholders[tx_id] = tx
            else:
                classifiable[tx_id] = tx

        # --- Classifiable transactions: full pipeline ---
        if classifiable:
            tx_descriptions = {tx_id: tx.description for tx_id, tx in classifiable.items()}
            classifier.set_manual_descriptions(tx_descriptions)

            results = classifier.classify_batch([
                (tx_id, classifiable[tx_id].description)
                for tx_id in classifiable.keys()
            ])

            for tx_id, (category, source) in results.items():
                transactions[tx_id].category = category
                transactions[tx_id].category_source = source

        # --- Encrypted placeholders: no classification ---
        for tx_id in encrypted_placeholders:
            transactions[tx_id].category = None
            transactions[tx_id].category_source = None

        return transactions

    def recategorize_all(self, transactions: Dict[str, Transaction]) -> Dict[str, Transaction]:
        """
        Re-categorize all transactions using current classifier.

        Args:
            transactions: Dictionary of tx_id -> Transaction

        Returns:
            Same dictionary with categories updated
        """
        return self.classify_transactions(transactions)

    def set_manual_descriptions(self, descriptions: Dict[str, str]):
        """
        Set transaction descriptions for similarity matching.

        Args:
            descriptions: Dictionary mapping tx_id to description
        """
        classifier = self._get_classifier()
        classifier.set_manual_descriptions(descriptions)

    def reload_patterns(self):
        """Reload regex patterns (reinitialize classifier)."""
        self._classifier = None
        self._get_classifier()

    def get_manual_assignments(self) -> Dict[str, str]:
        """
        Get all manual category assignments.

        Returns:
            Dictionary mapping tx_id to category_id
        """
        classifier = self._get_classifier()
        return classifier.manual_assignments

    @property
    def similarity_threshold(self) -> float:
        """Get the similarity threshold used for classification."""
        classifier = self._get_classifier()
        return classifier.similarity_threshold

    @property
    def has_similarity_calculator(self) -> bool:
        """Check if a similarity calculator is available."""
        classifier = self._get_classifier()
        return classifier.similarity_calculator is not None

    def invalidate_embedding(self, tx_id: str):
        """
        Invalidate cached embedding for a transaction.

        Args:
            tx_id: Transaction ID to invalidate
        """
        if self._embedding_datasource:
            self._embedding_datasource.invalidate_embedding(tx_id)

    def investigate_similarity(self, tx_id: str, description: str,
                               transactions: Dict[str, Transaction],
                               categories: Dict) -> dict:
        """
        Investigate similarity-based categorization for a transaction.

        Returns details about what similar transactions influenced the category.

        Args:
            tx_id: Transaction ID being investigated
            description: Description of the transaction
            transactions: Dict of all transactions (for looking up reference txs)
            categories: Dict of all categories (for names)

        Returns:
            Dictionary with keys: success, error, transaction, similar_transactions, threshold
        """
        classifier = self._get_classifier()

        if not classifier.similarity_calculator or not classifier.manual_descriptions:
            return {'success': False, 'error': 'Similarity calculator not available'}

        similarities = classifier.similarity_calculator.calculate_similarities(
            description,
            classifier.manual_descriptions
        )

        threshold = classifier.similarity_threshold
        similar_transactions = []

        for ref_tx_id, score in similarities:
            if score >= threshold:
                ref_tx = transactions.get(ref_tx_id)
                ref_category = classifier.manual_assignments.get(ref_tx_id)

                if ref_tx and ref_category:
                    category_name = categories.get(ref_category).name if ref_category in categories else 'Unknown'

                    similar_transactions.append({
                        'tx_id': ref_tx_id,
                        'description': ref_tx.description,
                        'date': ref_tx.date.strftime('%Y-%m-%d %H:%M:%S'),
                        'amount': str(ref_tx.amount),
                        'category_id': ref_category,
                        'category_name': category_name,
                        'similarity_score': round(score, 3)
                    })

        # Sort by similarity score descending
        similar_transactions.sort(key=lambda x: x['similarity_score'], reverse=True)

        return {
            'success': True,
            'similar_transactions': similar_transactions,
            'threshold': threshold
        }

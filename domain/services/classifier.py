import logging
import re
from collections import Counter
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from domain.entities.transaction import CategorySource
from domain.repositories.manual_assignment_repository import ManualAssignmentRepository
from domain.services.similarity_calculator import SimilarityCalculator

logger = logging.getLogger(__name__)


@dataclass
class Classifier:
    regexps: list[tuple[str, re.Pattern[str]]]
    manual_assignment_source: ManualAssignmentRepository | None = None
    similarity_calculator: SimilarityCalculator | None = None
    similarity_threshold: float = 0.7

    def __post_init__(self):
        """Load manual assignments if a source is provided."""
        self.manual_assignments = {}
        self.manual_descriptions: Dict[str, str] = {}
        if self.manual_assignment_source:
            self.manual_assignments = self.manual_assignment_source.get_assignments()

    def set_manual_descriptions(self, tx_descriptions: Dict[str, str]) -> None:
        """
        Set descriptions for manually assigned transactions.

        Args:
            tx_descriptions: Dictionary mapping transaction IDs to their descriptions
        """
        self.manual_descriptions = {
            tx_id: tx_descriptions[tx_id]
            for tx_id in self.manual_assignments.keys()
            if tx_id in tx_descriptions
        }

        # Pre-compute embeddings for all manual descriptions
        if self.similarity_calculator and self.manual_descriptions:
            logger.info(
                f"Pre-computing embeddings for {len(self.manual_descriptions)} reference transactions..."
            )
            self.similarity_calculator.precompute_reference_embeddings(self.manual_descriptions)
            logger.info("Reference embeddings cached.")

    def classify(
        self, tx_id: str, description: str
    ) -> Tuple[Optional[str], Optional[CategorySource]]:
        """
        Classify a transaction by its ID and description.

        Priority order:
        1. Manual assignments (highest priority)
        2. Regexp-based classification
        3. Similarity-based classification (fallback for unassigned)

        Args:
            tx_id: Transaction ID
            description: Transaction description

        Returns:
            Tuple of (Category ID or None, CategorySource or None)
        """
        # Check manual assignment first (highest priority)
        if tx_id in self.manual_assignments:
            return (self.manual_assignments[tx_id], CategorySource.MANUAL)

        # Fall back to regexp-based classification
        for category, regexp in self.regexps:
            if regexp.search(description):
                return (category, CategorySource.REGEXP)

        # Final fallback: similarity-based classification
        if self.similarity_calculator and self.manual_descriptions:
            sim_category = self._classify_by_similarity(description)
            if sim_category:
                return (sim_category, CategorySource.SIMILARITY)

        return (None, None)

    def classify_batch(
        self, transactions: list[tuple[str, str]]
    ) -> Dict[str, Tuple[Optional[str], Optional[CategorySource]]]:
        """
        Classify multiple transactions in batch for better performance.

        Priority order (same as classify):
        1. Manual assignments (highest priority)
        2. Regexp-based classification
        3. Similarity-based classification (batch processed)

        Args:
            transactions: List of (tx_id, description) tuples

        Returns:
            Dictionary mapping transaction IDs to (category ID, source) tuples
        """
        import time

        results: Dict[str, Tuple[Optional[str], Optional[CategorySource]]] = {}
        similarity_batch = []  # Transactions that need similarity-based classification

        manual_count = 0
        regexp_count = 0

        for tx_id, description in transactions:
            # Check manual assignment first
            if tx_id in self.manual_assignments:
                results[tx_id] = (self.manual_assignments[tx_id], CategorySource.MANUAL)
                manual_count += 1
                continue

            # Try regexp-based classification
            matched = False
            for category, regexp in self.regexps:
                if regexp.search(description):
                    results[tx_id] = (category, CategorySource.REGEXP)
                    matched = True
                    regexp_count += 1
                    break

            # If no match, add to similarity batch
            if not matched:
                similarity_batch.append((tx_id, description))

        logger.debug(f"Processing {len(transactions)} transactions:")
        logger.debug(f"  - Manual assignments: {manual_count}")
        logger.debug(f"  - Regexp matches: {regexp_count}")
        logger.debug(f"  - Need similarity calculation: {len(similarity_batch)}")

        # Process similarity batch all at once if needed
        if similarity_batch and self.similarity_calculator and self.manual_descriptions:
            similarity_start = time.time()
            # Extract IDs and descriptions separately
            batch_ids = [tx_id for tx_id, _ in similarity_batch]
            batch_descriptions = [desc for _, desc in similarity_batch]
            similarity_results = self._classify_batch_by_similarity(
                batch_descriptions, tx_ids=batch_ids
            )
            similarity_time = (time.time() - similarity_start) * 1000
            logger.debug(f"Similarity calculation took {similarity_time:.2f}ms")

            for (tx_id, _), sim_cat in zip(similarity_batch, similarity_results):
                if sim_cat:
                    results[tx_id] = (sim_cat, CategorySource.SIMILARITY)
                else:
                    results[tx_id] = (None, None)
        else:
            # No similarity calculator, mark as None
            for tx_id, _ in similarity_batch:
                results[tx_id] = (None, None)

        return results

    def _classify_by_similarity(self, description: str) -> str | None:
        """
        Classify by finding similar manually assigned transactions.

        Args:
            description: Transaction description

        Returns:
            Category ID based on majority vote of similar transactions, or None
        """
        # Calculate similarities with all manually assigned transactions
        if self.similarity_calculator is None:
            raise RuntimeError("Similarity calculator not initialized")
        similarities = self.similarity_calculator.calculate_similarities(
            description, self.manual_descriptions
        )

        # Filter by threshold and collect categories
        categories = []
        for tx_id, score in similarities:
            if score >= self.similarity_threshold:
                category = self.manual_assignments.get(tx_id)
                # print(f"Similarity match: {description} ~ {self.manual_descriptions[tx_id]} (score: {score}, category: {category})")
                if category:
                    categories.append(category)

        # Return None if no similar transactions found
        if not categories:
            return None

        # Return the majority category
        category_counts = Counter(categories)
        most_common = category_counts.most_common(1)
        return most_common[0][0] if most_common else None

    def _classify_batch_by_similarity(
        self, descriptions: list[str], tx_ids: Optional[list[str]] = None
    ) -> list[str | None]:
        """
        Classify multiple descriptions by similarity in batch.

        Args:
            descriptions: List of transaction descriptions
            tx_ids: Optional list of transaction IDs (for caching)

        Returns:
            List of category IDs (or None) in the same order as input
        """
        if not descriptions:
            return []

        # Calculate similarities for all descriptions at once
        # Pass tx_ids for persistent caching if available
        if self.similarity_calculator is None:
            raise RuntimeError("Similarity calculator not initialized")
        all_similarities = self.similarity_calculator.calculate_similarities_batch(
            descriptions, self.manual_descriptions, text_ids=tx_ids
        )

        # Process each description's similarities
        results: list[str | None] = []
        for similarities in all_similarities:
            # Filter by threshold and collect categories
            categories = []
            for tx_id, score in similarities:
                if score >= self.similarity_threshold:
                    category = self.manual_assignments.get(tx_id)
                    if category:
                        categories.append(category)

            # Determine category by majority vote
            if not categories:
                results.append(None)
            else:
                category_counts = Counter(categories)
                most_common = category_counts.most_common(1)
                results.append(most_common[0][0] if most_common else None)

        return results

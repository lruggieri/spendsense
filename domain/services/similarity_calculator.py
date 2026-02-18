from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple


class SimilarityCalculator(ABC):
    """Abstract base class for calculating text similarity."""

    def precompute_reference_embeddings(self, reference_texts: Dict[str, str]) -> None:
        """
        Optional method to pre-compute and cache embeddings for reference texts.

        Subclasses can override this to optimize repeated similarity calculations.
        Default implementation is a no-op.

        Args:
            reference_texts: Dictionary mapping IDs to reference texts
        """

    @abstractmethod
    def calculate_similarities(
        self, text: str, reference_texts: Dict[str, str]
    ) -> List[Tuple[str, float]]:
        """
        Calculate similarities between a text and reference texts.

        Args:
            text: The text to compare
            reference_texts: Dictionary mapping IDs to reference texts

        Returns:
            List of tuples (reference_id, similarity_score) sorted by score descending
        """

    def calculate_similarities_batch(
        self, texts: List[str], reference_texts: Dict[str, str], text_ids: Optional[List[str]] = None
    ) -> List[List[Tuple[str, float]]]:
        """
        Calculate similarities for multiple texts at once (batch processing).

        Default implementation calls calculate_similarities for each text.
        Subclasses should override this for better performance.

        Args:
            texts: List of texts to compare
            reference_texts: Dictionary mapping IDs to reference texts

        Returns:
            List of similarity results, one per input text. Each result is a list of
            tuples (reference_id, similarity_score) sorted by score descending.
        """
        return [self.calculate_similarities(text, reference_texts) for text in texts]

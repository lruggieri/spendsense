import logging
from typing import Optional, Dict, List, Tuple

import numpy as np

from domain.services.similarity_calculator import SimilarityCalculator

logger = logging.getLogger(__name__)


class EmbeddingSimilarityCalculator(SimilarityCalculator):
    """Similarity calculator using sentence embeddings and cosine similarity."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2", model=None, embedding_datasource=None):
        """
        Initialize the embedding-based similarity calculator.

        Args:
            model_name: Name of the sentence-transformers model to use (ignored if model is provided)
            model: Optional pre-loaded SentenceTransformer model instance for performance
            embedding_datasource: Optional EmbeddingRepository instance for persistent caching
        """
        if model is not None:
            # Use pre-loaded model (recommended for production)
            self.model = model
        else:
            # Load model on-demand (slower, used for testing or standalone usage)
            try:
                from sentence_transformers import SentenceTransformer

                self.model = SentenceTransformer(model_name)
            except ImportError:
                raise ImportError(
                    "sentence-transformers is required for EmbeddingSimilarityCalculator. "
                    "Install it with: pip install sentence-transformers"
                )

        # Persistent datasource for transaction embeddings (optional)
        self.embedding_datasource = embedding_datasource

        # Cache for pre-computed reference embeddings (in-memory only)
        self._reference_embeddings_cache: Dict[str, np.ndarray] = {}
        self._reference_ids_cache: List[str] = []

    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Calculate cosine similarity between two vectors."""
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)

    def precompute_reference_embeddings(self, reference_texts: Dict[str, str]) -> None:
        """
        Pre-compute and cache embeddings for reference texts.
        Uses persistent SQLite cache if embedding_datasource is available.

        This should be called once before performing multiple similarity calculations
        to avoid re-encoding the same reference texts repeatedly.

        Args:
            reference_texts: Dictionary mapping IDs to reference texts
        """
        import time

        if not reference_texts:
            self._reference_embeddings_cache = {}
            self._reference_ids_cache = []
            return

        self._reference_ids_cache = list(reference_texts.keys())

        # Try to use persistent cache if available
        if self.embedding_datasource:
            logger.debug(f" Checking cache for {len(reference_texts)} reference embeddings...")
            cache_start = time.time()

            # Convert to list of tuples for datasource
            ref_tuples = [(ref_id, reference_texts[ref_id]) for ref_id in self._reference_ids_cache]

            # Get cached embeddings and list of what needs encoding
            cached_embeddings, needs_encoding = self.embedding_datasource.get_cached_embeddings(
                ref_tuples
            )
            cache_time = (time.time() - cache_start) * 1000

            cache_hit_rate = len(cached_embeddings) / len(reference_texts) * 100
            logger.debug(
                f" Reference cache: {len(cached_embeddings)}/{len(reference_texts)} hits ({cache_hit_rate:.1f}%) in {cache_time:.2f}ms"
            )

            # Encode any missing references
            if needs_encoding:
                logger.debug(f" Encoding {len(needs_encoding)} missing reference embeddings...")
                encode_start = time.time()
                texts_to_encode = [desc for _, desc in needs_encoding]
                new_embeddings = self.model.encode(texts_to_encode, show_progress_bar=False)
                encode_time = (time.time() - encode_start) * 1000
                logger.debug(
                    f" Reference encoding took {encode_time:.2f}ms ({encode_time/len(needs_encoding):.2f}ms per reference)"
                )

                # Save newly computed embeddings to persistent cache
                embeddings_to_save = {
                    tx_id: (embedding, desc)
                    for (tx_id, desc), embedding in zip(needs_encoding, new_embeddings)
                }
                self.embedding_datasource.save_embeddings(embeddings_to_save)

                # Add to cached embeddings
                for (tx_id, _), embedding in zip(needs_encoding, new_embeddings):
                    cached_embeddings[tx_id] = embedding

            # Store in memory cache (preserving order)
            self._reference_embeddings_cache = {
                ref_id: cached_embeddings[ref_id] for ref_id in self._reference_ids_cache
            }

        else:
            # No persistent cache - encode all references
            reference_texts_list = [reference_texts[id] for id in self._reference_ids_cache]

            logger.debug(f" Encoding {len(reference_texts_list)} reference embeddings...")
            encode_start = time.time()
            reference_embeddings = self.model.encode(reference_texts_list, show_progress_bar=False)
            encode_time = (time.time() - encode_start) * 1000
            logger.debug(
                f" Reference encoding took {encode_time:.2f}ms ({encode_time/len(reference_texts_list):.2f}ms per reference)"
            )

            # Store in cache
            self._reference_embeddings_cache = {
                ref_id: embedding
                for ref_id, embedding in zip(self._reference_ids_cache, reference_embeddings)
            }

    def calculate_similarities(
        self, text: str, reference_texts: Dict[str, str]
    ) -> List[Tuple[str, float]]:
        """
        Calculate similarities using embeddings and cosine similarity.

        Args:
            text: The text to compare
            reference_texts: Dictionary mapping IDs to reference texts

        Returns:
            List of tuples (reference_id, similarity_score) sorted by score descending
        """
        if not reference_texts:
            return []

        # Use cached embeddings if available and cache matches current references
        use_cache = self._reference_embeddings_cache and set(reference_texts.keys()) == set(
            self._reference_ids_cache
        )

        # Generate embedding for the input text
        text_embedding = self.model.encode(text, show_progress_bar=False)

        # Get reference embeddings from cache or compute them
        if use_cache:
            reference_ids = self._reference_ids_cache
            reference_embeddings = [
                self._reference_embeddings_cache[ref_id] for ref_id in reference_ids
            ]
        else:
            # Fallback: Generate embeddings for all reference texts
            reference_ids = list(reference_texts.keys())
            reference_texts_list = [reference_texts[id] for id in reference_ids]
            reference_embeddings = self.model.encode(reference_texts_list)

        # Calculate cosine similarities using vectorized operations
        reference_embeddings_array = np.array(reference_embeddings)

        # Compute all cosine similarities at once
        dot_products = np.dot(reference_embeddings_array, text_embedding)
        text_norm = np.linalg.norm(text_embedding)
        ref_norms = np.linalg.norm(reference_embeddings_array, axis=1)

        # Avoid division by zero
        denominator = text_norm * ref_norms
        denominator = np.where(denominator == 0, 1e-10, denominator)
        cosine_similarities = dot_products / denominator

        # Build result list and sort by similarity score descending
        similarities = list(zip(reference_ids, cosine_similarities.tolist()))
        similarities.sort(key=lambda x: x[1], reverse=True)

        return similarities

    def calculate_similarities_batch(
        self, texts: List[str], reference_texts: Dict[str, str], text_ids: Optional[List[str]] = None
    ) -> List[List[Tuple[str, float]]]:
        """
        Calculate similarities for multiple texts at once (batch processing).

        Args:
            texts: List of texts to compare
            reference_texts: Dictionary mapping IDs to reference texts
            text_ids: Optional list of IDs corresponding to texts (for caching)

        Returns:
            List of similarity results, one per input text. Each result is a list of
            tuples (reference_id, similarity_score) sorted by score descending.
        """
        import time

        if not texts or not reference_texts:
            return [[] for _ in texts]

        # Use cached embeddings if available and cache matches current references
        use_cache = self._reference_embeddings_cache and set(reference_texts.keys()) == set(
            self._reference_ids_cache
        )

        # Try to load from persistent datasource if available
        text_embeddings_dict = {}
        texts_to_encode = []
        texts_to_encode_indices = []

        if self.embedding_datasource and text_ids:
            logger.debug(f" Checking persistent cache for {len(texts)} transactions...")
            cache_start = time.time()

            # Prepare list of (id, description) tuples
            id_text_pairs = [(text_ids[i], texts[i]) for i in range(len(texts))]

            # Get cached embeddings and list of what needs encoding
            cached, needs_encoding = self.embedding_datasource.get_cached_embeddings(id_text_pairs)

            cache_time = (time.time() - cache_start) * 1000
            logger.debug(f" Cache check took {cache_time:.2f}ms")
            logger.debug(
                f" Cache hits: {len(cached)}/{len(texts)} ({len(cached)/len(texts)*100:.1f}%)"
            )

            # Store cached embeddings
            text_embeddings_dict = cached

            # Track what needs encoding
            for tx_id, description in needs_encoding:
                idx = text_ids.index(tx_id)
                texts_to_encode.append(description)
                texts_to_encode_indices.append(idx)
        else:
            # No datasource available - encode everything
            texts_to_encode = texts
            texts_to_encode_indices = list(range(len(texts)))

        # Encode texts that weren't in cache
        if texts_to_encode:
            logger.debug(f" Encoding {len(texts_to_encode)} transaction descriptions...")
            encode_start = time.time()
            new_embeddings = self.model.encode(texts_to_encode, show_progress_bar=False)
            encode_time = (time.time() - encode_start) * 1000
            logger.debug(
                f" Encoding took {encode_time:.2f}ms ({encode_time/len(texts_to_encode):.2f}ms per transaction)"
            )

            # Store newly encoded embeddings
            embeddings_to_save = {}
            for i, idx in enumerate(texts_to_encode_indices):
                if text_ids:
                    tx_id = text_ids[idx]
                    text_embeddings_dict[tx_id] = new_embeddings[i]
                    embeddings_to_save[tx_id] = (new_embeddings[i], texts[idx])
                else:
                    # No IDs provided, can't use cache
                    text_embeddings_dict[idx] = new_embeddings[i]

            # Save to persistent datasource
            if self.embedding_datasource and text_ids and embeddings_to_save:
                save_start = time.time()
                self.embedding_datasource.save_embeddings(embeddings_to_save)
                save_time = (time.time() - save_start) * 1000
                logger.debug(
                    f" Saved {len(embeddings_to_save)} embeddings to cache in {save_time:.2f}ms"
                )

        # Reconstruct text_embeddings in original order
        if text_ids:
            text_embeddings = [text_embeddings_dict[tx_id] for tx_id in text_ids]
        else:
            text_embeddings = [text_embeddings_dict[i] for i in range(len(texts))]

        # Get reference embeddings from cache or compute them
        if use_cache:
            reference_ids = self._reference_ids_cache
            reference_embeddings = [
                self._reference_embeddings_cache[ref_id] for ref_id in reference_ids
            ]
        else:
            # Fallback: Generate embeddings for all reference texts
            reference_ids = list(reference_texts.keys())
            reference_texts_list = [reference_texts[id] for id in reference_ids]
            reference_embeddings = self.model.encode(reference_texts_list, show_progress_bar=False)

        # Convert to numpy array for vectorized operations
        reference_embeddings_array = np.array(reference_embeddings)
        text_embeddings_array = np.array(text_embeddings)

        # Calculate cosine similarities for all text-reference pairs
        logger.debug(
            f" Computing cosine similarities ({len(texts)} x {len(reference_ids)} matrix)..."
        )
        similarity_start = time.time()

        # Shape: (num_texts, num_references)
        dot_products = np.dot(text_embeddings_array, reference_embeddings_array.T)
        text_norms = np.linalg.norm(text_embeddings_array, axis=1, keepdims=True)
        ref_norms = np.linalg.norm(reference_embeddings_array, axis=1, keepdims=True)

        # Avoid division by zero
        denominator = text_norms * ref_norms.T
        denominator = np.where(denominator == 0, 1e-10, denominator)
        cosine_similarities = dot_products / denominator

        similarity_time = (time.time() - similarity_start) * 1000
        logger.debug(f" Cosine similarity calculation took {similarity_time:.2f}ms")

        # Build result list for each text
        results = []
        for text_idx in range(len(texts)):
            similarities = list(zip(reference_ids, cosine_similarities[text_idx].tolist()))
            similarities.sort(key=lambda x: x[1], reverse=True)
            results.append(similarities)

        return results

"""
Utility functions for the Flask application.

Contains helper functions used across multiple blueprints.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from domain.entities.category_tree import CategoryNode
from domain.entities.transaction import Transaction
from urllib.parse import parse_qs

from flask import g, request
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from config import get_database_path
from infrastructure.persistence.sqlite.factory import SQLiteDataSourceFactory
from infrastructure.persistence.factory import DataSourceFactory
from presentation.web.extensions import (
    get_sentence_model, get_cache_manager, get_session_datasource,
    get_credentials_loader_instance
)
from domain.services.embedding_similarity_calculator import EmbeddingSimilarityCalculator

# Import focused services
from application.services import (
    CategoryService,
    EncryptionService,
    PatternService,
    UserSettingsService,
    TransactionService,
    ClassificationService,
    FetcherService,
    GroupService
)


logger = logging.getLogger(__name__)


class EncryptionKeyRequired(Exception):
    """Raised when an operation requires the encryption key but it's not available."""
    pass


def invalidate_service_cache(user_id: str = None):
    """
    Invalidate service cache in Redis for a specific user or all users.
    Cache invalidation is now shared across all Flask workers/processes.
    Call this when data changes that require reloading (e.g., after Gmail fetch,
    category assignment, comment update, or new transaction).

    Args:
        user_id: Specific user to invalidate, or None to clear all cache entries
    """
    cache_manager = get_cache_manager()
    cache_manager.invalidate(user_id)


def parse_redirect_params(params_string):
    """
    Parse redirect_params string and return a dict suitable for url_for.

    Args:
        params_string: URL-encoded query string (e.g., "category=1&from_date=2025-01-01")

    Returns:
        Dictionary of parameter key-value pairs
    """
    if not params_string:
        return {}

    # parse_qs returns lists for each value, we want single values
    parsed = parse_qs(params_string)
    return {key: values[0] for key, values in parsed.items() if values}


def extract_date_part(date_string):
    """
    Extract date part (YYYY-MM-DD) from a date string.

    Args:
        date_string: Date string which may be None, ISO format (with 'T'), or simple date

    Returns:
        Date part as string (YYYY-MM-DD) or empty string if None
    """
    if not date_string:
        return ''
    if 'T' in date_string:
        return date_string.split('T')[0]
    return date_string


def refresh_google_token_if_needed(session_token, google_token, encryption_key=None):
    """
    Check if Google access token is expired and refresh it if needed.

    Args:
        session_token: User's session token
        google_token: Dictionary containing Google OAuth tokens
        encryption_key: Optional encryption key to encrypt the refreshed token

    Returns:
        Updated google_token dictionary with fresh access token
    """
    # If the token is a fallback (decryption failed or no key), it won't have OAuth fields
    if 'token' not in google_token:
        raise EncryptionKeyRequired('Google token unavailable — encryption key may be missing or incorrect')

    session_datasource = get_session_datasource()
    credentials_loader = get_credentials_loader_instance()

    # Check if access token is expired
    access_token_expiry = google_token.get('access_token_expiry')
    if not access_token_expiry:
        # No expiry info, assume it needs refresh
        needs_refresh = True
    else:
        expiry_dt = datetime.fromisoformat(access_token_expiry)
        # Make timezone-aware if it isn't already (assume UTC)
        if expiry_dt.tzinfo is None:
            expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)
        # Refresh if expired or expiring in next 5 minutes
        needs_refresh = expiry_dt <= datetime.now(timezone.utc) + timedelta(minutes=5)

    if not needs_refresh:
        return google_token  # Token still valid

    # Load client credentials from config
    client_config = credentials_loader.get_client_config()
    client_id = client_config['client_id']
    client_secret = client_config['client_secret']

    # Create credentials object
    creds = Credentials(
        token=google_token['token'],
        refresh_token=google_token['refresh_token'],
        token_uri=google_token['token_uri'],
        client_id=client_id,
        client_secret=client_secret,
        scopes=google_token['scopes']
    )

    # Refresh the token
    try:
        creds.refresh(Request())

        # Update the token dictionary with new access token
        google_token['token'] = creds.token
        google_token['access_token_expiry'] = creds.expiry.isoformat() if creds.expiry else None

        # Update session in database with refreshed token (preserves session_token)
        session_datasource.update_google_token(session_token, google_token, encryption_key=encryption_key)

        logger.info(f"Successfully refreshed access token (expires: {google_token['access_token_expiry']})")
        return google_token

    except Exception as e:
        logger.warning(f"Token refresh failed: {str(e)}")
        # Return original token, let the API call fail and handle it there
        return google_token


# =============================================================================
# Classification Helpers
# =============================================================================

def load_and_classify(tx_service: TransactionService,
                      classification_service: ClassificationService) -> Dict[str, Transaction]:
    """
    Load all transactions and classify them.

    Args:
        tx_service: TransactionService instance
        classification_service: ClassificationService instance

    Returns:
        Dictionary mapping tx_id to classified Transaction
    """
    all_txs = tx_service.get_all_transactions()
    tx_dict = {tx.id: tx for tx in all_txs}
    classification_service.classify_transactions(tx_dict)
    return tx_dict


# =============================================================================
# Focused Service Factory Functions
# =============================================================================

def _get_user_id() -> str:
    """
    Get current user ID from request context.

    Returns:
        User ID string

    Raises:
        RuntimeError: If called without authenticated user
    """
    user_id = getattr(request, 'user_id', None)
    if not user_id:
        raise RuntimeError("Service factory called without authenticated user")
    return user_id


def _get_datasource_factory() -> DataSourceFactory:
    """
    Get datasource factory for the current user.

    Returns:
        DataSourceFactory implementation (currently SQLite)

    Note:
        In future, this can check configuration to return different factory types
        (PostgreSQL, MongoDB, etc.) enabling easy database migration.
    """
    user_id = _get_user_id()
    db_path = get_database_path()
    encryption_key = getattr(g, 'encryption_key', None)
    return SQLiteDataSourceFactory(db_path, user_id, encryption_key=encryption_key)


def get_category_service() -> CategoryService:
    """
    Get CategoryService instance for the current logged-in user.

    Must be called within a request context with authenticated user.
    Lightweight - only loads categories, no ML models.
    """
    factory = _get_datasource_factory()
    return CategoryService(
        user_id=_get_user_id(),
        category_datasource=factory.get_category_datasource(),
        db_path=get_database_path()
    )


def get_pattern_service(category_service: Optional[CategoryService] = None) -> PatternService:
    """
    Get PatternService instance for the current logged-in user.

    Args:
        category_service: Optional CategoryService to reuse (avoids duplicate loading)

    Must be called within a request context with authenticated user.
    """
    factory = _get_datasource_factory()
    if category_service is None:
        category_service = get_category_service()
    return PatternService(
        user_id=_get_user_id(),
        regexp_datasource=factory.get_regexp_datasource(),
        category_service=category_service,
        db_path=get_database_path()
    )


def get_user_settings_service() -> UserSettingsService:
    """
    Get UserSettingsService instance for the current logged-in user.

    Must be called within a request context with authenticated user.
    Lightweight - only loads user settings.
    """
    factory = _get_datasource_factory()
    return UserSettingsService(
        user_id=_get_user_id(),
        user_settings_datasource=factory.get_user_settings_datasource(),
        db_path=get_database_path()
    )


def get_transaction_service(category_service: Optional[CategoryService] = None,
                            user_settings_service: Optional[UserSettingsService] = None) -> TransactionService:
    """
    Get slimmed TransactionService instance for the current logged-in user.

    Args:
        category_service: Optional CategoryService to reuse
        user_settings_service: Optional UserSettingsService to reuse

    Must be called within a request context with authenticated user.
    Does NOT initialize ML models - use get_classification_service() for classification.
    """
    factory = _get_datasource_factory()
    if category_service is None:
        category_service = get_category_service()
    if user_settings_service is None:
        user_settings_service = get_user_settings_service()
    return TransactionService(
        user_id=_get_user_id(),
        transaction_datasource=factory.get_transaction_datasource(),
        manual_assignment_datasource=factory.get_manual_assignment_datasource(),
        category_service=category_service,
        user_settings_service=user_settings_service,
        db_path=get_database_path()
    )


def get_classification_service(skip_similarity: bool = False) -> ClassificationService:
    """
    Get ClassificationService instance for the current logged-in user.

    Args:
        skip_similarity: If True, skip similarity-based classification (faster)

    Must be called within a request context with authenticated user.
    Initializes ML models lazily on first classify() call.
    """
    factory = _get_datasource_factory()

    # Create similarity calculator if not skipping
    similarity_calculator = None
    if not skip_similarity:
        similarity_calculator = EmbeddingSimilarityCalculator(
            model=get_sentence_model(),
            embedding_datasource=factory.get_embedding_datasource()
        )

    return ClassificationService(
        user_id=_get_user_id(),
        manual_assignment_datasource=factory.get_manual_assignment_datasource(),
        regexp_datasource=factory.get_regexp_datasource(),
        embedding_datasource=factory.get_embedding_datasource(),
        db_path=get_database_path(),
        similarity_calculator=similarity_calculator,
        skip_similarity=skip_similarity
    )


def get_fetcher_service(user_settings_service: Optional[UserSettingsService] = None) -> FetcherService:
    """
    Get FetcherService instance for the current logged-in user.

    Args:
        user_settings_service: Optional UserSettingsService to reuse

    Must be called within a request context with authenticated user.
    """
    factory = _get_datasource_factory()
    if user_settings_service is None:
        user_settings_service = get_user_settings_service()
    return FetcherService(
        user_id=_get_user_id(),
        fetcher_datasource=factory.get_fetcher_datasource(),
        user_settings_service=user_settings_service,
        db_path=get_database_path()
    )


def get_group_service(transaction_service: Optional[TransactionService] = None) -> GroupService:
    """
    Get GroupService instance for the current logged-in user.

    Args:
        transaction_service: Optional TransactionService to reuse

    Must be called within a request context with authenticated user.
    """
    factory = _get_datasource_factory()
    if transaction_service is None:
        transaction_service = get_transaction_service()
    return GroupService(
        user_id=_get_user_id(),
        group_datasource=factory.get_group_datasource(),
        transaction_service=transaction_service,
        db_path=get_database_path()
    )


def get_encryption_service() -> EncryptionService:
    """
    Get EncryptionService instance for the current logged-in user.

    Must be called within a request context with authenticated user.
    Includes transaction and session datasources for migration operations.
    """
    factory = _get_datasource_factory()
    encryption_key = getattr(g, 'encryption_key', None)
    return EncryptionService(
        encryption_repo=factory.get_encryption_datasource(),
        transaction_datasource=factory.get_transaction_datasource(),
        session_datasource=get_session_datasource(),
        encryption_key=encryption_key,
        embedding_datasource=factory.get_embedding_datasource(),
    )


# =============================================================================
# Tree / Chart Helpers
# =============================================================================

def tree_to_dict(node: CategoryNode, parent_id: Optional[str] = None) -> dict:
    """
    Convert CategoryNode tree to dictionary format for visualization.

    Pure data transform extracted from legacy service.py.

    Args:
        node: CategoryNode to convert
        parent_id: Optional parent category ID

    Returns:
        Dictionary with id, name, total, children keys
    """
    result = {
        'id': node.category.id,
        'name': node.category.name,
        'total': round(node.total_expense, 2),
        'children': []
    }

    if parent_id:
        result['parent_id'] = parent_id

    # Recursively process children
    for child in sorted(node.children, key=lambda x: x.total_expense, reverse=True):
        if child.total_expense > 0:  # Only include categories with expenses
            result['children'].append(tree_to_dict(child, node.category.id))

    return result


def build_category_tree_data(category_service: CategoryService,
                             user_settings_service: UserSettingsService,
                             transactions: List[Transaction],
                             from_date: Optional[str] = None,
                             to_date: Optional[str] = None) -> dict:
    """
    Build category tree data for visualization.

    Replaces legacy service.get_category_tree_data().

    Args:
        category_service: CategoryService instance
        user_settings_service: UserSettingsService instance
        transactions: List of classified Transaction entities
        from_date: Optional start date filter (YYYY-MM-DD)
        to_date: Optional end date filter (YYYY-MM-DD)

    Returns:
        Dictionary containing tree data for visualization
    """
    from domain.entities.category_tree import CategoryTree

    # Build the category tree
    categories_dict = category_service.get_categories_as_dict_list()
    tree_obj = CategoryTree(categories_dict)

    # Get user currency and converter for currency conversion
    user_settings = user_settings_service.get_user_settings()
    user_currency = user_settings.currency if user_settings else 'JPY'
    converter = user_settings_service.get_currency_converter()

    # Calculate expenses with currency conversion
    tree_obj.calculate_expenses(transactions, from_date, to_date, user_currency, converter)

    # Convert tree to visualization-friendly format
    return tree_to_dict(tree_obj.root)

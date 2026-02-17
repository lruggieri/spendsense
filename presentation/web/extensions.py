"""
Shared state and extensions for the Flask application.

This module contains global state that is shared across all blueprints:
- ML model (SentenceTransformer)
- Currency rate updater
- Redis cache manager
- Session datasource
- OAuth configuration
"""

import atexit
import logging
import time

import torch
from sentence_transformers import SentenceTransformer

from config import (
    get_credentials_loader, get_database_path, get_allowed_emails,
    get_redis_host, get_redis_port, get_redis_db, get_cache_ttl
)
from infrastructure.persistence.sqlite.repositories.session_repository import SQLiteSessionDataSource
from infrastructure.currency_rate_updater import CurrencyRateUpdater
from infrastructure.cache.redis_cache_manager import RedisCacheManager


logger = logging.getLogger(__name__)

# Global ML model - loaded once at startup for performance
# This model is shared across all users (model is stateless)
_global_sentence_model = None

# Currency rate updater - runs in background thread
rate_updater = None

# Redis-based cache manager for TransactionService instances
_cache_manager = None

# Session datasource using configured database path
session_datasource = None

# OAuth credentials loader
credentials_loader = None

# Allowed emails for access control (None = unrestricted)
allowed_emails = None

# Gmail OAuth scopes
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "openid"
]


def init_extensions(app):
    """
    Initialize all extensions and shared state.

    This should be called once during application startup.

    Args:
        app: Flask application instance
    """
    global _global_sentence_model, rate_updater, _cache_manager
    global session_datasource, credentials_loader, allowed_emails

    # Load ML model
    logger.info("Loading SentenceTransformer model (this may take a few seconds)...")
    model_load_start = time.time()

    # Check device availability
    if torch.cuda.is_available():
        device = 'cuda'
        logger.info(f"GPU detected: {torch.cuda.get_device_name(0)} - will use GPU for encoding")
    elif torch.backends.mps.is_available():
        device = 'mps'  # Apple Silicon GPU
        logger.info("Apple Silicon GPU detected - will use MPS for encoding")
    else:
        device = 'cpu'
        logger.info("No GPU detected - will use CPU for encoding (slower)")

    _global_sentence_model = SentenceTransformer('all-MiniLM-L6-v2', device=device)
    model_load_time = (time.time() - model_load_start) * 1000
    logger.info(f"Model loaded in {model_load_time:.2f}ms on device '{device}' and ready for reuse across all users!")

    # Initialize currency rate updater
    logger.info("Initializing currency rate updater...")
    rate_updater = CurrencyRateUpdater()
    rate_updater.start()
    logger.info("Currency rate updater started")

    # Cleanup on shutdown
    atexit.register(rate_updater.stop)

    # Initialize Redis-based cache manager
    _cache_manager = RedisCacheManager(
        redis_host=get_redis_host(),
        redis_port=get_redis_port(),
        redis_db=get_redis_db(),
        default_ttl=get_cache_ttl()
    )

    # Initialize session datasource
    session_datasource = SQLiteSessionDataSource(get_database_path())

    # Initialize credentials loader
    credentials_loader = get_credentials_loader()

    # Load allowed emails for access control
    allowed_emails = get_allowed_emails()


def get_sentence_model():
    """Get the global sentence transformer model."""
    return _global_sentence_model


def get_cache_manager():
    """Get the Redis cache manager."""
    return _cache_manager


def get_session_datasource():
    """Get the session datasource."""
    return session_datasource


def get_credentials_loader_instance():
    """Get the credentials loader instance."""
    return credentials_loader


def get_allowed_emails_list():
    """Get the list of allowed emails (or None if unrestricted)."""
    return allowed_emails

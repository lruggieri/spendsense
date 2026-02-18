"""
Base service class providing common functionality for all services.
"""

import logging

from config import get_database_path
from typing import Optional

logger = logging.getLogger(__name__)


class BaseService:
    """
    Base class for all focused services.

    Provides common initialization pattern with db_path and user_id.
    All services should inherit from this class.
    """

    def __init__(self, user_id: str, db_path: Optional[str] = None):
        """
        Initialize base service.

        Args:
            user_id: User ID for data isolation
            db_path: Optional database path. If None, uses get_database_path()
        """
        self.user_id = user_id
        self.db_path = db_path or get_database_path()

    def _get_db_path(self) -> str:
        """Get the database path (for backward compatibility)."""
        return self.db_path

"""
Session datasource abstraction.

This module provides an abstract interface for session storage, allowing easy migration from one database to another.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Optional

from domain.entities.session import Session


class SessionRepository(ABC):
    """Abstract interface for session storage."""

    @abstractmethod
    def create_session(self, user_id: str, user_profile: Dict, expiration: datetime) -> str:
        """
        Create a new session for a user.

        Args:
            user_id: User identifier (email or Google ID)
            user_profile: User profile dict with user_name and user_picture
            expiration: Session expiration datetime

        Returns:
            Session token string
        """

    @abstractmethod
    def get_session(self, session_token: str) -> Optional[Session]:
        """
        Get session data by token.

        Args:
            session_token: Session token to lookup

        Returns:
            Session object or None if not found/expired
        """

    @abstractmethod
    def delete_session(self, session_token: str) -> bool:
        """
        Delete a session.

        Args:
            session_token: Session token to delete

        Returns:
            True if session was deleted, False otherwise
        """

    @abstractmethod
    def delete_user_sessions(self, user_id: str) -> int:
        """
        Delete all sessions for a user.

        Args:
            user_id: User identifier

        Returns:
            Number of sessions deleted
        """

    @abstractmethod
    def cleanup_expired_sessions(self) -> int:
        """
        Delete all expired sessions.

        Returns:
            Number of sessions deleted
        """

    @abstractmethod
    def update_session_expiration(self, session_token: str, new_expiration: datetime) -> bool:
        """
        Update session expiration time.

        Args:
            session_token: Session token to update
            new_expiration: New expiration datetime

        Returns:
            True if updated, False otherwise
        """

"""
Session datasource abstraction.

This module provides an abstract interface for session storage, allowing easy migration from one database to another.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, Dict
from domain.entities.session import Session


class SessionRepository(ABC):
    """Abstract interface for session storage."""

    @abstractmethod
    def create_session(self, user_id: str, google_token: Dict, expiration: datetime) -> str:
        """
        Create a new session for a user.

        Args:
            user_id: User identifier (email or Google ID)
            google_token: Google OAuth token dictionary
            expiration: Session expiration datetime

        Returns:
            Session token string
        """
        pass

    @abstractmethod
    def get_session(self, session_token: str) -> Optional[Session]:
        """
        Get session data by token.

        Args:
            session_token: Session token to lookup

        Returns:
            Session object or None if not found/expired
        """
        pass

    @abstractmethod
    def delete_session(self, session_token: str) -> bool:
        """
        Delete a session.

        Args:
            session_token: Session token to delete

        Returns:
            True if session was deleted, False otherwise
        """
        pass

    @abstractmethod
    def delete_user_sessions(self, user_id: str) -> int:
        """
        Delete all sessions for a user.

        Args:
            user_id: User identifier

        Returns:
            Number of sessions deleted
        """
        pass

    @abstractmethod
    def cleanup_expired_sessions(self) -> int:
        """
        Delete all expired sessions.

        Returns:
            Number of sessions deleted
        """
        pass

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
        pass

    @abstractmethod
    def update_google_token(self, session_token: str, google_token: Dict) -> bool:
        """
        Update the Google OAuth token for a session (e.g., after token refresh).

        Args:
            session_token: Session token to update
            google_token: New Google token dictionary

        Returns:
            True if updated, False otherwise
        """
        pass

    @abstractmethod
    def encrypt_google_token(self, session_token: str, encryption_key: str) -> bool:
        """
        Encrypt the Google OAuth token for a session.

        Args:
            session_token: Session token whose Google token to encrypt
            encryption_key: Encryption key to use

        Returns:
            True if encrypted, False otherwise
        """
        pass

    @abstractmethod
    def decrypt_google_token(self, session_token: str, encryption_key: str) -> bool:
        """
        Decrypt the Google OAuth token for a session back to plaintext.

        Args:
            session_token: Session token whose Google token to decrypt
            encryption_key: Encryption key to use

        Returns:
            True if decrypted, False otherwise
        """
        pass

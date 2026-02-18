"""
Encryption repository abstraction.

Provides an abstract interface for storing wrapped DEKs and WebAuthn credentials.
"""

from abc import ABC, abstractmethod
from typing import List, Optional


class EncryptionRepository(ABC):
    """Abstract interface for encryption key and WebAuthn credential storage."""

    # =========================================================================
    # Encryption keys (wrapped DEKs)
    # =========================================================================

    @abstractmethod
    def store_wrapped_dek(
        self,
        user_id: str,
        credential_id: str,
        wrapped_dek: bytes,
        prf_salt: str,
        wrapper_type: str = "prf",
    ) -> None:
        """Store a wrapped DEK for a user/credential pair."""

    @abstractmethod
    def get_wrapped_dek(self, user_id: str, credential_id: str) -> Optional[bytes]:
        """Get the wrapped DEK for a specific user/credential pair."""

    @abstractmethod
    def get_wrapped_deks_for_user(self, user_id: str) -> List[dict]:
        """Get all wrapped DEKs for a user."""

    @abstractmethod
    def delete_wrapped_dek(self, user_id: str, credential_id: str) -> None:
        """Delete a wrapped DEK for a user/credential pair."""

    @abstractmethod
    def get_prf_salt(self, user_id: str, credential_id: str) -> Optional[str]:
        """Get the PRF salt for a user/credential pair."""

    # =========================================================================
    # WebAuthn credentials
    # =========================================================================

    @abstractmethod
    def store_credential(
        self,
        user_id: str,
        credential_id: str,
        public_key: bytes,
        sign_count: int,
        device_name: Optional[str] = None,
    ) -> None:
        """Store a WebAuthn credential."""

    @abstractmethod
    def get_credential(self, credential_id: str) -> Optional[dict]:
        """Get a WebAuthn credential by credential_id."""

    @abstractmethod
    def get_credentials_for_user(self, user_id: str) -> List[dict]:
        """Get all WebAuthn credentials for a user."""

    @abstractmethod
    def update_sign_count(self, credential_id: str, sign_count: int) -> None:
        """Update the sign count for a credential after authentication."""

    @abstractmethod
    def delete_credential(self, credential_id: str) -> None:
        """Delete a WebAuthn credential."""

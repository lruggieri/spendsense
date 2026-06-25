"""
Encryption service for managing Data Encryption Keys (DEKs) using envelope encryption.

Handles DEK generation, wrapping/unwrapping with Key Encryption Keys (KEKs),
multi-passkey support, and WebAuthn credential management.
"""

import base64
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from domain.repositories.embedding_repository import EmbeddingRepository
from domain.repositories.encryption_repository import EncryptionRepository
from domain.repositories.mcp_api_key_repository import MCPApiKeyRepository
from domain.repositories.session_repository import SessionRepository
from domain.repositories.transaction_repository import TransactionRepository
from infrastructure.crypto.encryption import generate_dek, unwrap_key, wrap_key

logger = logging.getLogger(__name__)


class EncryptionService:
    """Manages envelope encryption and WebAuthn credential lifecycle."""

    def __init__(
        self,
        encryption_repo: EncryptionRepository,
        transaction_datasource: Optional[TransactionRepository] = None,
        session_datasource: Optional[SessionRepository] = None,
        encryption_key: Optional[str] = None,
        embedding_datasource: Optional[EmbeddingRepository] = None,
        mcp_api_key_datasource: Optional[MCPApiKeyRepository] = None,
    ):
        self._encryption_repo = encryption_repo
        self._transaction_repo = transaction_datasource
        self._session_repo = session_datasource
        self._encryption_key = encryption_key
        self._embedding_datasource = embedding_datasource
        self._mcp_api_key_repo = mcp_api_key_datasource

    # =========================================================================
    # DEK management
    # =========================================================================

    def setup_encryption(
        self, user_id: str, credential_id: str, kek_b64: str, prf_salt: str
    ) -> str:
        """
        Generate a new DEK, wrap it with the provided KEK, and store the wrapped DEK.

        Returns:
            Base64-encoded DEK for the client to store.
        """
        dek = generate_dek()
        kek = base64.b64decode(kek_b64)
        wrapped = wrap_key(dek, kek)

        self._encryption_repo.store_wrapped_dek(user_id, credential_id, wrapped, prf_salt)
        logger.info(f"Encryption set up for user {user_id}, credential {credential_id[:8]}...")

        return base64.b64encode(dek).decode("ascii")

    def unwrap_dek(self, user_id: str, credential_id: str, kek_b64: str) -> str:
        """
        Unwrap the stored DEK using the provided KEK.

        Returns:
            Base64-encoded DEK.

        Raises:
            ValueError: If no wrapped DEK found or unwrap fails.
        """
        wrapped_dek = self._encryption_repo.get_wrapped_dek(user_id, credential_id)
        if not wrapped_dek:
            raise ValueError(
                f"No wrapped DEK found for user {user_id}, credential {credential_id[:8]}..."
            )

        kek = base64.b64decode(kek_b64)
        dek = unwrap_key(wrapped_dek, kek)
        return base64.b64encode(dek).decode("ascii")

    def add_passkey_wrapper(
        self, user_id: str, credential_id: str, dek_b64: str, kek_b64: str, prf_salt: str
    ) -> None:
        """Wrap an existing DEK with a new KEK (for additional passkeys)."""
        dek = base64.b64decode(dek_b64)
        kek = base64.b64decode(kek_b64)
        wrapped = wrap_key(dek, kek)

        self._encryption_repo.store_wrapped_dek(user_id, credential_id, wrapped, prf_salt)
        logger.info(f"Added passkey wrapper for user {user_id}, credential {credential_id[:8]}...")

    def has_encryption(self, user_id: str) -> bool:
        """Check if user has encryption set up (has at least one wrapped DEK)."""
        deks = self._encryption_repo.get_wrapped_deks_for_user(user_id)
        return len(deks) > 0

    # =========================================================================
    # WebAuthn credential management
    # =========================================================================

    def store_credential(
        self,
        user_id: str,
        credential_id: str,
        public_key: bytes,
        sign_count: int,
        device_name: Optional[str] = None,
    ) -> None:
        """Store a WebAuthn credential."""
        self._encryption_repo.store_credential(
            user_id, credential_id, public_key, sign_count, device_name
        )

    def get_credential(self, credential_id: str) -> Optional[dict]:
        """Get a WebAuthn credential by credential_id."""
        return self._encryption_repo.get_credential(credential_id)

    def get_credentials_for_user(self, user_id: str) -> List[dict]:
        """Get all WebAuthn credentials for a user."""
        return self._encryption_repo.get_credentials_for_user(user_id)

    def update_sign_count(self, credential_id: str, sign_count: int) -> None:
        """Update the sign count for a credential after authentication."""
        self._encryption_repo.update_sign_count(credential_id, sign_count)

    def get_prf_salt(self, user_id: str, credential_id: str) -> Optional[str]:
        """Get the PRF salt for a user/credential pair."""
        return self._encryption_repo.get_prf_salt(user_id, credential_id)

    # =========================================================================
    # Data migration (encrypt / decrypt)
    # =========================================================================

    def migrate_to_encrypted(self, session_token: Optional[str] = None) -> int:
        """
        Encrypt all plaintext transactions and the session's Google token.

        Args:
            session_token: Optional session token to encrypt its Google token.

        Returns:
            Number of transactions migrated.

        Raises:
            RuntimeError: If transaction datasource is not configured.
        """
        if not self._transaction_repo:
            raise RuntimeError("Transaction datasource not configured for migration")

        count = self._transaction_repo.migrate_to_encrypted()

        if count > 0 and self._embedding_datasource:
            self._embedding_datasource.invalidate_all()
            logger.info(f"Invalidated embedding cache after encrypting {count} transactions")

        return count

    def migrate_to_plaintext(self, session_token: Optional[str] = None) -> int:
        """
        Decrypt all encrypted transactions and the session's Google token back to plaintext.

        Args:
            session_token: Optional session token to decrypt its Google token.

        Returns:
            Number of transactions migrated.

        Raises:
            RuntimeError: If transaction datasource is not configured.
        """
        if not self._transaction_repo:
            raise RuntimeError("Transaction datasource not configured for migration")

        count = self._transaction_repo.migrate_to_plaintext()

        if count > 0 and self._embedding_datasource:
            self._embedding_datasource.invalidate_all()
            logger.info(f"Invalidated embedding cache after decrypting {count} transactions")

        return count

    # =========================================================================
    # MCP API key lifecycle
    # =========================================================================

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_mcp_api_key(
        self,
        user_id: str,
        scope: str,
        label: str,
        expires_at: Optional[str],
        dek_b64: Optional[str],
    ) -> str:
        """Create an MCP API key.

        If dek_b64 is provided (encrypted account), wrap the DEK with a KEK
        derived from the new key and store it.

        Returns:
            Raw API key string (shown once — caller must relay to the user).
        """
        from infrastructure.crypto.encryption import (
            generate_api_key,
            hash_token,
            hkdf_derive_kek,
            wrap_key,
        )

        assert self._mcp_api_key_repo is not None
        if scope not in ("read", "readwrite"):
            raise ValueError("scope must be 'read' or 'readwrite'")
        raw = generate_api_key()
        key_id = str(uuid.uuid4())
        self._mcp_api_key_repo.create(
            key_id, user_id, hash_token(raw), scope, label, self._now_iso(), expires_at,
        )
        if dek_b64:
            salt = os.urandom(16)
            kek = hkdf_derive_kek(raw, salt)
            wrapped = wrap_key(base64.b64decode(dek_b64), kek)
            self._encryption_repo.store_wrapped_dek(
                user_id, key_id, wrapped,
                base64.b64encode(salt).decode("ascii"), wrapper_type="apikey",
            )
        logger.info(f"Created MCP key {key_id[:8]}... for {user_id} (scope={scope})")
        return raw

    def resolve_mcp_api_key(self, raw_key: str) -> Optional[dict]:
        """Resolve a raw key to identity + scope, or None if invalid/revoked/expired.

        Returns:
            Dict with keys ``user_id``, ``scope``, ``key_id``, ``encrypted``,
            or ``None`` if the key is not found / revoked / expired.
        """
        from infrastructure.crypto.encryption import hash_token

        assert self._mcp_api_key_repo is not None
        row = self._mcp_api_key_repo.get_by_token_hash(hash_token(raw_key))
        if not row or row["revoked"]:
            return None
        if row["expires_at"] and self._now_iso() > row["expires_at"]:
            return None
        key_id = row["id"]
        self._mcp_api_key_repo.touch_last_used(key_id, self._now_iso())
        encrypted = self._encryption_repo.get_wrapped_dek(row["user_id"], key_id) is not None
        return {
            "user_id": row["user_id"],
            "scope": row["scope"],
            "key_id": key_id,
            "encrypted": encrypted,
        }

    def unwrap_dek_for_api_key(self, raw_key: str) -> Optional[str]:
        """Return base64 DEK for the key, or None if the account is not encrypted.

        Raises:
            ValueError: If the key is invalid or revoked.
        """
        from infrastructure.crypto.encryption import hash_token, hkdf_derive_kek, unwrap_key

        assert self._mcp_api_key_repo is not None
        row = self._mcp_api_key_repo.get_by_token_hash(hash_token(raw_key))
        if not row or row["revoked"]:
            raise ValueError("invalid key")
        user_id, key_id = row["user_id"], row["id"]
        wrapped = self._encryption_repo.get_wrapped_dek(user_id, key_id)
        if not wrapped:
            return None
        salt_b64 = self._encryption_repo.get_prf_salt(user_id, key_id)
        if salt_b64 is None:
            raise ValueError("missing salt for wrapped DEK")
        kek = hkdf_derive_kek(raw_key, base64.b64decode(salt_b64))
        dek = unwrap_key(wrapped, kek)
        return base64.b64encode(dek).decode("ascii")

    def list_mcp_api_keys(self, user_id: str) -> List[dict]:
        """Return all MCP API keys for a user."""
        assert self._mcp_api_key_repo is not None
        return self._mcp_api_key_repo.list_for_user(user_id)

    def revoke_mcp_api_key(self, user_id: str, key_id: str) -> bool:
        """Revoke a key and delete its wrapped-DEK row (avoids orphan rows)."""
        assert self._mcp_api_key_repo is not None
        self._encryption_repo.delete_wrapped_dek(user_id, key_id)
        return self._mcp_api_key_repo.revoke(user_id, key_id)

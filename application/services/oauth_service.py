"""OAuthService: owns the OAuth 2.1 persistence repos + EncryptionService.

Covers client registration and the authorization-transaction bootstrap
(`begin_authorization`) used by `SpendSenseOAuthProvider.authorize()`. Later
tasks add code exchange, refresh-token rotation, and access-token
verification to this same class.
"""
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from application.services.encryption_service import EncryptionService
from infrastructure.persistence.sqlite.repositories.encryption_repository import (
    SQLiteEncryptionRepository,
)
from infrastructure.persistence.sqlite.repositories.oauth_authorization_repository import (
    SQLiteOAuthAuthorizationRepository,
)
from infrastructure.persistence.sqlite.repositories.oauth_client_repository import (
    SQLiteOAuthClientRepository,
)
from infrastructure.persistence.sqlite.repositories.oauth_grant_repository import (
    SQLiteOAuthGrantRepository,
)

logger = logging.getLogger(__name__)

# Token TTLs (seconds), per the OAuth 2.1 plan. Not all are consumed yet —
# code exchange / refresh / access-token verification are later tasks — but
# they're defined here as the single source of truth for those tasks.
AT_TTL_SECONDS = 3600
RT_TTL_SECONDS = 30 * 24 * 3600
CODE_TTL_SECONDS = 60
RT_GRACE_SECONDS = 30

# TTL for a pending (not-yet-consented) authorization transaction. Not
# specified by name in the plan's TTL list (which only names AT/RT/code/
# rt_grace); chosen to comfortably cover a user completing the consent
# screen without leaving stale rows around indefinitely.
PENDING_AUTH_TTL_SECONDS = 600


class OAuthService:
    """Owns OAuth client/authorization/grant persistence and DEK envelope operations."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._client_repo = SQLiteOAuthClientRepository(db_path)
        self._authorization_repo = SQLiteOAuthAuthorizationRepository(db_path)
        self._grant_repo = SQLiteOAuthGrantRepository(db_path)
        self._encryption = EncryptionService(
            encryption_repo=SQLiteEncryptionRepository(db_path)
        )

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    # =========================================================================
    # Client registration
    # =========================================================================

    def register_client(
        self, client_id: str, redirect_uris: List[str], metadata_json: str
    ) -> None:
        """Register (or re-register) an OAuth client."""
        self._client_repo.upsert(
            client_id, redirect_uris, metadata_json, self._now().isoformat()
        )
        logger.info(f"Registered OAuth client {client_id}")

    def get_client(self, client_id: str) -> Optional[dict]:
        """Return the stored client row (client_id, redirect_uris, metadata, created_at)."""
        return self._client_repo.get(client_id)

    # =========================================================================
    # Authorization bootstrap
    # =========================================================================

    def begin_authorization(self, client_id: str, params_dict: dict) -> str:
        """Start a pending authorization transaction and return its txn_id.

        Persists `params_dict` (the incoming AuthorizationParams, JSON-encoded)
        keyed by a fresh 256-bit txn_id so the consent flow (a later task) can
        look it up and, on approval, complete the authorization-code issuance.
        """
        import json

        txn_id = secrets.token_urlsafe(32)
        now = self._now()
        expires_at = now + timedelta(seconds=PENDING_AUTH_TTL_SECONDS)
        self._authorization_repo.create_pending(
            txn_id, client_id, json.dumps(params_dict), now.isoformat(), expires_at.isoformat()
        )
        return txn_id

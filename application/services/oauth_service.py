"""OAuthService: owns the OAuth 2.1 persistence repos + EncryptionService.

Covers client registration and the authorization-transaction bootstrap
(`begin_authorization`) used by `SpendSenseOAuthProvider.authorize()`. Later
tasks add code exchange, refresh-token rotation, and access-token
verification to this same class.
"""
import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from application.services.encryption_service import EncryptionService
from infrastructure.crypto.encryption import hash_token
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
        txn_id = secrets.token_urlsafe(32)
        now = self._now()
        expires_at = now + timedelta(seconds=PENDING_AUTH_TTL_SECONDS)
        self._authorization_repo.create_pending(
            txn_id, client_id, json.dumps(params_dict), now.isoformat(), expires_at.isoformat()
        )
        return txn_id

    # =========================================================================
    # Authorization code issuance + exchange (the DEK bridge)
    # =========================================================================

    def issue_code(
        self, user_id: str, pending: dict, dek_b64: Optional[str]
    ) -> str:
        """Mint a fresh authorization code for a consented authorization request.

        `pending` carries the assembled authorization request (client_id plus
        the AuthorizationParams fields: scopes, code_challenge, redirect_uri,
        redirect_uri_provided_explicitly, resource). If `dek_b64` is given
        (the account is encrypted), the DEK is wrapped under a KEK derived
        from the raw code itself, so it can be recovered on exchange even
        though the OAuth back-channel carries no user credentials.

        Returns:
            The raw authorization code (shown once - callers must not log it).
        """
        code = secrets.token_urlsafe(32)
        code_id = hash_token(code)
        now = self._now()
        expires_at = now + timedelta(seconds=CODE_TTL_SECONDS)
        self._authorization_repo.create_code(
            code_id,
            pending["client_id"],
            user_id,
            json.dumps(pending.get("scopes") or []),
            pending["code_challenge"],
            pending["redirect_uri"],
            1 if pending.get("redirect_uri_provided_explicitly") else 0,
            pending.get("resource"),
            expires_at.isoformat(),
        )
        if dek_b64:
            self._encryption.oauth_wrap_dek_for_code(user_id, code, code_id, dek_b64)
        return code

    def get_code(self, client_id: str, raw_code: str) -> Optional[dict]:
        """Return the stored code row if it exists, is unexpired, and belongs to `client_id`.

        Returns None otherwise (unknown code, wrong client, or expired) so
        callers can treat all three the same way - never revealing which one.
        """
        row = self._authorization_repo.get_code(hash_token(raw_code))
        if row is None or row["client_id"] != client_id:
            return None
        if self._now() >= datetime.fromisoformat(row["expires_at"]):
            return None
        return row

    def exchange_code(self, client_id: str, raw_code: str) -> Optional[dict]:
        """Exchange a valid authorization code for a fresh access/refresh token pair.

        Bridges the DEK (if the account is encrypted) from the code's
        envelope to new envelopes keyed on the minted access/refresh tokens,
        then deletes the code and its envelope so it cannot be replayed.

        Returns:
            Dict with `access_token`, `refresh_token`, `scope`, `expires_in`,
            or None if the code is invalid/expired/mismatched-client.
        """
        row = self.get_code(client_id, raw_code)
        if row is None:
            return None

        code_id = hash_token(raw_code)
        user_id = row["user_id"]
        dek_b64 = self._encryption.oauth_unwrap_dek_for_code(user_id, raw_code, code_id)

        grant_id = secrets.token_urlsafe(32)
        access_token = secrets.token_urlsafe(32)
        refresh_token = secrets.token_urlsafe(32)

        at_salt_b64, rt_salt_b64 = "", ""
        if dek_b64:
            at_salt_b64, rt_salt_b64 = self._encryption.oauth_create_token_envelopes(
                user_id, grant_id, access_token, refresh_token, dek_b64
            )

        now = self._now()
        at_expires_at = now + timedelta(seconds=AT_TTL_SECONDS)
        rt_expires_at = now + timedelta(seconds=RT_TTL_SECONDS)
        scope = " ".join(json.loads(row["scopes"]))

        self._grant_repo.create(
            grant_id,
            user_id,
            client_id,
            scope,
            hash_token(access_token),
            at_salt_b64,
            at_expires_at.isoformat(),
            hash_token(refresh_token),
            rt_salt_b64,
            rt_expires_at.isoformat(),
            now.isoformat(),
        )

        self._authorization_repo.delete_code(code_id)
        self._encryption.oauth_delete_code_envelope(user_id, code_id)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "scope": scope,
            "expires_in": AT_TTL_SECONDS,
        }

    # =========================================================================
    # Access-token resolution (minimal helpers used by the DEK bridge; the
    # full provider-facing `load_access_token` is completed in a later task)
    # =========================================================================

    def resolve_access(self, access_token: str) -> Optional[dict]:
        """Resolve a raw access token to its grant row, or None if invalid/expired/revoked."""
        row = self._grant_repo.get_by_at_hash(hash_token(access_token))
        if row is None:
            return None
        if self._now() >= datetime.fromisoformat(row["at_expires_at"]):
            return None
        return row

    def unwrap_dek(self, access_token: str, resolved: dict) -> Optional[str]:
        """Return the base64 DEK bridged via this access token, or None if unencrypted."""
        return self._encryption.oauth_unwrap_dek_for_access_token(
            resolved["user_id"], resolved["grant_id"], access_token, resolved["at_salt"]
        )

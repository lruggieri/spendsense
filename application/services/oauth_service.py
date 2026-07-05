"""OAuthService: owns the OAuth 2.1 persistence repos + EncryptionService.

Covers client registration and the authorization-transaction bootstrap
(`begin_authorization`) used by `SpendSenseOAuthProvider.authorize()`. Later
tasks add code exchange, refresh-token rotation, and access-token
verification to this same class.
"""
import json
import logging
import secrets
import threading
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
from infrastructure.persistence.sqlite.repositories.mcp_api_key_repository import (
    SQLiteMCPApiKeyRepository,
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
            encryption_repo=SQLiteEncryptionRepository(db_path),
            # Needed so resolve_access()/unwrap_dek() can fall back to the
            # legacy manually-created API key path (resolve_mcp_api_key /
            # unwrap_dek_for_api_key) alongside OAuth grants.
            mcp_api_key_datasource=SQLiteMCPApiKeyRepository(db_path),
        )
        # Serializes refresh() end-to-end (read -> DEK unwrap -> re-wrap ->
        # rotate). See refresh()'s docstring for why rotate()'s SQL-level
        # compare-and-swap alone is not enough.
        self._refresh_lock = threading.Lock()

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

    def get_pending(self, txn_id: str) -> Optional[dict]:
        """Return the pending authorization request for `txn_id`, or None if unknown/expired.

        The returned dict is the original AuthorizationParams fields (scopes,
        code_challenge, redirect_uri, redirect_uri_provided_explicitly,
        resource, state) merged with `client_id`, matching the `pending` shape
        `issue_code` expects - so callers (the consent blueprint) can pass
        this straight through without a second lookup.
        """
        row = self._authorization_repo.get_pending(txn_id)
        if row is None:
            return None
        if self._now() >= datetime.fromisoformat(row["expires_at"]):
            return None
        pending = json.loads(row["params"])
        pending["client_id"] = row["client_id"]
        return pending

    def consume_pending(self, txn_id: str) -> None:
        """Delete a pending authorization transaction.

        Called once the user has acted on the consent screen (approve or
        deny) so the txn_id cannot be replayed to re-trigger issuance.
        """
        self._authorization_repo.delete_pending(txn_id)

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
        then deletes the code's envelope so it cannot be replayed.

        The code row itself is claimed atomically via `consume_code` (a single
        `DELETE ... RETURNING` statement) *before* any DEK unwrap or token
        minting happens. This closes a TOCTOU race where two concurrent
        exchanges of the same code could both pass a read-then-delete check
        and mint two independent, valid token pairs from one single-use code.

        Returns:
            Dict with `access_token`, `refresh_token`, `scope`, `expires_in`,
            or None if the code is invalid/expired/mismatched-client/already
            consumed.
        """
        code_id = hash_token(raw_code)
        row = self._authorization_repo.consume_code(code_id)
        if row is None:
            return None
        if row["client_id"] != client_id:
            return None
        if self._now() >= datetime.fromisoformat(row["expires_at"]):
            return None

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

        self._encryption.oauth_delete_code_envelope(user_id, code_id)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "scope": scope,
            "expires_in": AT_TTL_SECONDS,
        }

    # =========================================================================
    # Access-token resolution (unifies OAuth grants with legacy,
    # manually-created API keys, so both auth paths keep working side by
    # side) + revoke
    # =========================================================================

    def resolve_access(self, access_token: str) -> Optional[dict]:
        """Resolve a raw access token to identity + scope.

        Tries the OAuth grant first (by `at_hash`, unexpired, unrevoked); if
        that doesn't resolve, falls back to a legacy manually-created API
        key. Returns None if neither resolves.

        Returns:
            The full grant row plus `"kind": "oauth"` for an OAuth access
            token (so `grant_id`/`at_salt` remain available to `unwrap_dek`
            and callers), or `{"user_id", "scope", "key_id", "encrypted",
            "kind": "apikey"}` for a legacy API key, or None.
        """
        row = self._grant_repo.get_by_at_hash(hash_token(access_token))
        if row is not None:
            if self._now() >= datetime.fromisoformat(row["at_expires_at"]):
                return None
            return {**row, "kind": "oauth"}
        legacy = self._encryption.resolve_mcp_api_key(access_token)
        if legacy is not None:
            return {**legacy, "kind": "apikey"}
        return None

    def unwrap_dek(self, access_token: str, resolved: dict) -> Optional[str]:
        """Return the base64 DEK bridged via this access token, or None if unencrypted."""
        if resolved.get("kind") == "apikey":
            return self._encryption.unwrap_dek_for_api_key(access_token)
        return self._encryption.oauth_unwrap_dek_for_access_token(
            resolved["user_id"], resolved["grant_id"], access_token, resolved["at_salt"]
        )

    def revoke(self, raw_token: str) -> None:
        """Revoke the OAuth grant behind a raw access or refresh token.

        Looks the token up by `at_hash` first, then `rt_hash` (a caller may
        hand back either an access or a refresh token per the SDK's
        `revoke_token` contract), revokes the grant, and deletes its DEK
        envelopes. A legacy API key (or any other unrecognized token) has no
        grant/envelopes to revoke via this path, so this is a no-op rather
        than an error - matching the SDK's "invalid or already revoked
        tokens are silently ignored" contract.
        """
        token_hash = hash_token(raw_token)
        grant = self._grant_repo.get_by_at_hash(token_hash)
        if grant is None:
            grant = self._grant_repo.get_by_rt_hash(token_hash)
        if grant is None:
            return
        self._grant_repo.revoke_by_grant_id(grant["grant_id"])
        self._encryption.oauth_delete_grant_envelopes(grant["user_id"], grant["grant_id"])

    # =========================================================================
    # Refresh-token rotation
    # =========================================================================

    def resolve_refresh(self, client_id: str, raw_rt: str) -> Optional[dict]:
        """Read-only resolve of a raw refresh token to its grant row.

        Used by the provider's `load_refresh_token` to validate the token
        (existence, client ownership, expiry) *before* the SDK decides
        whether to call `refresh()` to perform the actual rotation. Does not
        mutate anything, so it is safe to call speculatively and is not
        covered by `_refresh_lock`.

        If the presented token is the just-rotated-away RT still inside its
        grace window, the returned dict's `rt_expires_at` is overridden with
        the grace expiry (`prev_rt_expires_at`) rather than the current RT's
        expiry, so callers report the presented token's own expiry.

        Returns:
            The grant row (dict), or None if unknown/expired/wrong client.
        """
        rt_hash = hash_token(raw_rt)
        grant = self._grant_repo.get_by_rt_hash(rt_hash)
        if grant is None:
            return None
        if grant["client_id"] != client_id:
            return None

        now = self._now()
        if rt_hash == grant["rt_hash"]:
            if now >= datetime.fromisoformat(grant["rt_expires_at"]):
                return None
            return grant
        if grant["prev_rt_hash"] is not None and rt_hash == grant["prev_rt_hash"]:
            if grant["prev_rt_expires_at"] is None:
                return None
            if now >= datetime.fromisoformat(grant["prev_rt_expires_at"]):
                return None
            return {**grant, "rt_expires_at": grant["prev_rt_expires_at"]}
        return None

    def refresh(
        self, client_id: str, raw_rt: str, scopes: Optional[List[str]]
    ) -> Optional[dict]:
        """Exchange a valid refresh token for a new access/refresh token pair.

        Rotates the grant's tokens and re-wraps the DEK (if the account is
        encrypted) under the new secrets, preserving the outgoing refresh
        token's envelope under a `:prev` slot so a request that presents the
        just-rotated-away RT within `RT_GRACE_SECONDS` still resolves instead
        of hard-failing (e.g. a client retrying after a lost response).

        Concurrency (two layers, see the class-level threading.Lock and
        `rotate()`'s docstring):

        1. `_refresh_lock` serializes this method's entire read -> DEK-unwrap
           -> re-wrap -> rotate sequence per-process. This matters because
           the DEK re-wrap (`oauth_rewrap_for_rotation`) writes envelope rows
           in the encryption-key store keyed only by `grant_id` - it has no
           compare-and-swap of its own. Without the lock, two truly
           concurrent calls could interleave their envelope writes (e.g.
           caller A's "preserve current envelope as :prev" step reading
           caller B's already-rewritten envelope instead of the original),
           leaving a grant row whose `at_salt`/`rt_salt` no longer match what
           is actually stored in the envelope the winner needs to unwrap -
           breaking DEK recovery even for the winning, "successful" caller.
           Serializing avoids this entirely: at most one refresh is ever
           minting/re-wrapping tokens for a given grant at a time, in this
           process.
        2. `_grant_repo.rotate()` is additionally a SQL-level compare-and-swap
           (`WHERE rt_hash = <the rt_hash this call observed>`) on the grants
           table itself. This is what actually determines whether a token
           pair is "live" - it protects correctness even across multiple
           processes sharing one SQLite file (where the in-process lock in
           (1) provides no guarantee), and it is what a second, *sequential*
           call in the retry-with-the-just-rotated-away-RT scenario relies on
           to be treated as a legitimate next rotation rather than a race.

        With (1) in place, a truly concurrent pair of calls on the same RT
        degrades into the same well-defined sequential case the plan
        describes: one completes first and wins; the second acquires the
        lock next, re-reads the row, finds its RT hash now matches
        `prev_rt_hash` (with grace still open), and is honored as a
        legitimate refresh of the just-rotated-away RT - it mints its own
        new, chained pair rather than failing or corrupting anything.
        `rotate()`'s CAS is kept regardless (defense in depth for
        multi-process deployments and to make illegal states like "row
        changed underneath us" fail closed rather than silently succeed).

        Returns:
            Dict with `access_token`, `refresh_token`, `scope`, `expires_in`,
            or None if the refresh token is invalid/expired/revoked, belongs
            to a different client, or lost a concurrent rotation race.
        """
        with self._refresh_lock:
            rt_hash = hash_token(raw_rt)
            grant = self._grant_repo.get_by_rt_hash(rt_hash)
            if grant is None:
                return None
            if grant["client_id"] != client_id:
                return None

            now = self._now()
            using_prev = False
            if rt_hash == grant["rt_hash"]:
                if now >= datetime.fromisoformat(grant["rt_expires_at"]):
                    return None
            elif grant["prev_rt_hash"] is not None and rt_hash == grant["prev_rt_hash"]:
                if grant["prev_rt_expires_at"] is None:
                    return None
                if now >= datetime.fromisoformat(grant["prev_rt_expires_at"]):
                    return None
                using_prev = True
            else:
                # get_by_rt_hash only matches rt_hash/prev_rt_hash, so this is
                # unreachable in practice - kept as a defensive fallback.
                return None

            user_id = grant["user_id"]
            grant_id = grant["grant_id"]
            if using_prev:
                dek_b64 = self._encryption.oauth_unwrap_dek_for_prev_refresh_token(
                    user_id, grant_id, raw_rt
                )
            else:
                dek_b64 = self._encryption.oauth_unwrap_dek_for_refresh_token(
                    user_id, grant_id, raw_rt, grant["rt_salt"]
                )

            access_token = secrets.token_urlsafe(32)
            refresh_token = secrets.token_urlsafe(32)
            at_expires_at = now + timedelta(seconds=AT_TTL_SECONDS)
            rt_expires_at = now + timedelta(seconds=RT_TTL_SECONDS)
            grace_expires_at = now + timedelta(seconds=RT_GRACE_SECONDS)

            at_salt_b64, rt_salt_b64 = "", ""
            if dek_b64:
                at_salt_b64, rt_salt_b64 = self._encryption.oauth_rewrap_for_rotation(
                    user_id, grant_id, access_token, refresh_token, dek_b64,
                    keep_prev_rt=raw_rt,
                )

            rotated = self._grant_repo.rotate(
                grant_id,
                hash_token(access_token),
                at_salt_b64,
                at_expires_at.isoformat(),
                hash_token(refresh_token),
                rt_salt_b64,
                rt_expires_at.isoformat(),
                grant["rt_hash"],
                grace_expires_at.isoformat(),
            )
            if not rotated:
                # Lost a concurrent rotation race (e.g. a different process
                # also holding the grants-table row): our new envelopes (if
                # any) were written but are now unreachable via any rt/at
                # hash stored on the grant row, so they're inert - discard
                # our pair rather than returning tokens that can never
                # resolve.
                return None

            scope = " ".join(scopes) if scopes else grant["scope"]
            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "scope": scope,
                "expires_in": AT_TTL_SECONDS,
            }

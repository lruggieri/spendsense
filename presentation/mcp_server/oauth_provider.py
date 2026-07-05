"""SpendSenseOAuthProvider: MCP SDK OAuthAuthorizationServerProvider implementation.

This task covers client registration (`register_client`/`get_client`), the
`authorize()` entry point (which starts a pending-authorization transaction
and redirects to SpendSense's own consent page), and code exchange
(`load_authorization_code`/`exchange_authorization_code`), which recovers the
DEK across the OAuth back-channel gap and mints the first access/refresh
token pair. The remaining abstract methods (`load_refresh_token`,
`exchange_refresh_token`, `load_access_token`, `revoke_token`) are stubbed
here — later tasks implement them one at a time.
"""
import json
import os
from datetime import datetime
from typing import Any, Optional

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    TokenError,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from application.services.oauth_service import OAuthService

# The full set of scopes SpendSense supports. Every client is registered
# with this as its ceiling (see `register_client()` below) regardless of
# what its registration request specified - some OAuth clients (e.g. Claude
# Code's `oauth.scopes` config) only pin the scope requested at the
# `/authorize` step, never at Dynamic Client Registration, so gating
# `/authorize` requests against a narrower per-client registered scope would
# reject a legitimate "readwrite" request with "Client was not registered
# with scope readwrite". The actual per-authorization grant is still fully
# gated by what's requested at `/authorize` (or DEFAULT_SCOPES below when
# omitted) plus the user's consent approval - this ceiling only controls
# what a client is allowed to *ask* for.
VALID_SCOPES = ["read", "readwrite"]

# Fallback used when a client's `/authorize` request omits `scope` entirely
# (RFC 6749 §3.3: the server MUST substitute a pre-defined default rather
# than silently granting none). Deliberately NOT derived from the client's
# registered scope (see VALID_SCOPES above) - that's just a ceiling on what
# can be requested, not a safe default to fall back to when nothing was
# requested at all.
DEFAULT_SCOPES = ["read"]


def _base_url() -> str:
    return os.getenv("MCP_BASE_URL", "http://localhost:5000")


def _iso_to_epoch(iso_str: str) -> float:
    return datetime.fromisoformat(iso_str).timestamp()


class SpendSenseOAuthProvider(OAuthAuthorizationServerProvider):
    """Delegates OAuth 2.1 authorization-server behavior to `OAuthService`."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._service = OAuthService(db_path)

    @property
    def service(self) -> OAuthService:
        return self._service

    # =========================================================================
    # Client registration (implemented this task)
    # =========================================================================

    async def get_client(self, client_id: str) -> Optional[OAuthClientInformationFull]:
        row = self._service.get_client(client_id)
        if row is None:
            return None
        return OAuthClientInformationFull(**json.loads(row["metadata"]))

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        assert client_info.client_id is not None
        redirect_uris = client_info.redirect_uris or []
        # Widen the registered scope to the server's full valid set (see
        # VALID_SCOPES) regardless of what the registration request asked
        # for - it's only a ceiling for what a client may request later at
        # `/authorize`, not what actually gets granted.
        client_info.scope = " ".join(VALID_SCOPES)
        self._service.register_client(
            client_info.client_id,
            [str(uri) for uri in redirect_uris],
            client_info.model_dump_json(),
        )

    # =========================================================================
    # authorize() entry point (implemented this task)
    # =========================================================================

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        assert client.client_id is not None
        base = _base_url()
        params_dict = params.model_dump(mode="json")
        if not params_dict.get("scopes"):
            # RFC 6749 §3.3: if the client's authorization request omits
            # `scope` entirely (the SDK's `validate_scope(None)` returns
            # `None`, so `params.scopes` is empty here), the server MUST
            # substitute a pre-defined default rather than silently granting
            # none. Always DEFAULT_SCOPES here, never the client's
            # registered scope (VALID_SCOPES, "read readwrite" for every
            # client) - that's a ceiling on what CAN be requested, not a
            # safe assumption for what SHOULD be granted when nothing was
            # explicitly asked for.
            params_dict["scopes"] = DEFAULT_SCOPES
        txn_id = self._service.begin_authorization(client.client_id, params_dict)
        return f"{base}/mcp-consent?txn={txn_id}"

    # =========================================================================
    # Code exchange (implemented this task) — the DEK bridge
    # =========================================================================

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> Optional[AuthorizationCode]:
        assert client.client_id is not None
        row = self._service.get_code(client.client_id, authorization_code)
        if row is None:
            return None
        return AuthorizationCode(
            code=authorization_code,
            scopes=json.loads(row["scopes"]),
            expires_at=_iso_to_epoch(row["expires_at"]),
            client_id=row["client_id"],
            code_challenge=row["code_challenge"],
            redirect_uri=row["redirect_uri"],
            redirect_uri_provided_explicitly=bool(row["redirect_uri_explicit"]),
            resource=row["resource"],
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: Any
    ) -> OAuthToken:
        assert client.client_id is not None
        result = self._service.exchange_code(client.client_id, authorization_code.code)
        if result is None:
            raise TokenError(
                "invalid_grant", "Authorization code is invalid, expired, or already used"
            )
        return OAuthToken(
            access_token=result["access_token"],
            token_type="Bearer",
            expires_in=result["expires_in"],
            scope=result["scope"],
            refresh_token=result["refresh_token"],
        )

    # =========================================================================
    # Refresh-token rotation (implemented this task)
    # =========================================================================

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> Optional[RefreshToken]:
        assert client.client_id is not None
        row = self._service.resolve_refresh(client.client_id, refresh_token)
        if row is None:
            return None
        return RefreshToken(
            token=refresh_token,
            client_id=row["client_id"],
            scopes=row["scope"].split() if row["scope"] else [],
            expires_at=int(_iso_to_epoch(row["rt_expires_at"])),
        )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: Any,
        scopes: list,
    ) -> OAuthToken:
        assert client.client_id is not None
        result = self._service.refresh(client.client_id, refresh_token.token, scopes)
        if result is None:
            raise TokenError(
                "invalid_grant", "Refresh token is invalid, expired, or already used"
            )
        return OAuthToken(
            access_token=result["access_token"],
            token_type="Bearer",
            expires_in=result["expires_in"],
            scope=result["scope"],
            refresh_token=result["refresh_token"],
        )

    # =========================================================================
    # Access-token verification + revoke (implemented this task) — unifies
    # OAuth grants with legacy, manually-created API keys via
    # `OAuthService.resolve_access`/`revoke`.
    # =========================================================================

    async def load_access_token(self, token: str) -> Optional[AccessToken]:
        resolved = self._service.resolve_access(token)
        if resolved is None:
            return None
        return AccessToken(
            token=token,
            # client_id is the *registered OAuth client's* id (the same value
            # used everywhere else as client_id, e.g. the SDK's /revoke
            # handler authorizes a revocation by checking this against the
            # client authenticated on the request) - not the SpendSense user
            # and not the grant_id (a fresh, per-authorization identifier
            # minted on every code exchange, so it can never match a stable
            # client id). A legacy API key has no OAuth client, so it falls
            # back to the user id (matching the pre-existing legacy verifier
            # in presentation/mcp_server/auth.py).
            client_id=resolved.get("client_id") or resolved["user_id"],
            scopes=resolved["scope"].split() if resolved["scope"] else [],
            expires_at=None,
            resource=None,
        )

    async def revoke_token(self, token: Any) -> None:
        self._service.revoke(token.token)

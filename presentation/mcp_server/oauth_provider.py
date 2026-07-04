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
        txn_id = self._service.begin_authorization(
            client.client_id, params.model_dump(mode="json")
        )
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
    # Stubs — implemented by a later task (6: access-token verification).
    # Kept here only so this class is concrete/importable; do not implement
    # real logic in this task.
    # =========================================================================

    async def load_access_token(self, token: str) -> Optional[AccessToken]:
        raise NotImplementedError

    async def revoke_token(self, token: Any) -> None:
        raise NotImplementedError

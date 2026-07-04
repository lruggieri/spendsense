"""SpendSenseOAuthProvider: MCP SDK OAuthAuthorizationServerProvider implementation.

This task covers client registration (`register_client`/`get_client`) and the
`authorize()` entry point, which starts a pending-authorization transaction
and redirects to SpendSense's own consent page. The remaining abstract
methods (`load_authorization_code`, `exchange_authorization_code`,
`load_refresh_token`, `exchange_refresh_token`, `load_access_token`,
`revoke_token`) are stubbed here — later tasks implement them one at a time.
"""
import json
import os
from typing import Any, Optional

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from application.services.oauth_service import OAuthService


def _base_url() -> str:
    return os.getenv("MCP_BASE_URL", "http://localhost:5000")


class SpendSenseOAuthProvider(OAuthAuthorizationServerProvider):
    """Delegates OAuth 2.1 authorization-server behavior to `OAuthService`."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._service = OAuthService(db_path)

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
    # Stubs — implemented by later tasks (4: code exchange, 5: refresh
    # rotation, 6: access-token verification). Kept here only so this class
    # is concrete/importable; do not implement real logic in this task.
    # =========================================================================

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> Optional[AuthorizationCode]:
        raise NotImplementedError

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: Any
    ) -> OAuthToken:
        raise NotImplementedError

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> Optional[RefreshToken]:
        raise NotImplementedError

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: Any,
        scopes: list,
    ) -> OAuthToken:
        raise NotImplementedError

    async def load_access_token(self, token: str) -> Optional[AccessToken]:
        raise NotImplementedError

    async def revoke_token(self, token: Any) -> None:
        raise NotImplementedError

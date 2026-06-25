"""MCP authentication: resolve per-user scoped API keys to identity, scope, and DEK."""
import os
import time
from typing import Optional

from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp.exceptions import ToolError

from application.services.encryption_service import EncryptionService
from infrastructure.crypto.encryption import hash_token
from infrastructure.persistence.sqlite.repositories.encryption_repository import (
    SQLiteEncryptionRepository,
)
from infrastructure.persistence.sqlite.repositories.mcp_api_key_repository import (
    SQLiteMCPApiKeyRepository,
)
from presentation.mcp.context import MCPServices, build_services
from presentation.mcp.ratelimit import RateLimiter


def _db_path() -> str:
    from config import get_database_path
    return get_database_path()


_rate_limiter = RateLimiter(int(os.getenv("MCP_RATE_LIMIT_PER_MIN", "60")))


def _encryption_service() -> EncryptionService:
    path = _db_path()
    return EncryptionService(
        encryption_repo=SQLiteEncryptionRepository(path),
        mcp_api_key_datasource=SQLiteMCPApiKeyRepository(path),
    )


class SpendSenseTokenVerifier(TokenVerifier):
    async def verify_token(self, token: str) -> Optional[AccessToken]:
        resolved = _encryption_service().resolve_mcp_api_key(token)
        if not resolved:
            return None
        return AccessToken(
            token=token,
            client_id=resolved["user_id"],
            scopes=[resolved["scope"]],
            expires_at=None,
        )


def require_write(scope: str) -> None:
    if scope != "readwrite":
        raise ToolError("permission denied: this API key is read-only")


def get_tool_context() -> "tuple[MCPServices, str]":
    """Resolve the current request to (services, scope). Call at the top of every tool."""
    token_obj = get_access_token()
    if token_obj is None:
        raise ToolError("unauthorized: no access token")
    raw = token_obj.token
    user_id = token_obj.client_id
    scope = token_obj.scopes[0] if token_obj.scopes else "read"
    if not _rate_limiter.check(hash_token(raw), time.monotonic()):
        raise ToolError("rate limit exceeded, retry shortly")
    dek = _encryption_service().unwrap_dek_for_api_key(raw)
    services = build_services(_db_path(), user_id, dek)
    return services, scope

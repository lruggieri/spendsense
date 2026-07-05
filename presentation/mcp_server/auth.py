"""MCP authentication: resolve per-user scoped API keys to identity, scope, and DEK."""
import os
import time

from cryptography.hazmat.primitives.keywrap import InvalidUnwrap
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp.exceptions import ToolError

from application.services.encryption_service import EncryptionService
from application.services.oauth_service import OAuthService
from infrastructure.crypto.encryption import hash_token
from infrastructure.persistence.sqlite.repositories.encryption_repository import (
    SQLiteEncryptionRepository,
)
from infrastructure.persistence.sqlite.repositories.mcp_api_key_repository import (
    SQLiteMCPApiKeyRepository,
)
from presentation.mcp_server.context import MCPServices, build_services
from presentation.mcp_server.ratelimit import RateLimiter


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


def _oauth_service() -> OAuthService:
    return OAuthService(_db_path())


def require_write(scope: str) -> None:
    if "readwrite" not in scope.split():
        raise ToolError("permission denied: this API key is read-only")


def get_tool_context() -> "tuple[MCPServices, str]":
    """Resolve the current request to (services, scope). Call at the top of every tool.

    Resolves both OAuth access tokens and legacy API keys via
    `OAuthService.resolve_access`/`unwrap_dek`, so the SpendSense user_id is
    always derived from the resolved identity - never from
    `AccessToken.client_id` (which, for OAuth tokens, is the registered
    OAuth client application's id, not the user).
    """
    token_obj = get_access_token()
    if token_obj is None:
        raise ToolError("unauthorized: no access token")
    raw = token_obj.token
    if not _rate_limiter.check(hash_token(raw), time.monotonic()):
        raise ToolError("rate limit exceeded, retry shortly")
    svc = _oauth_service()
    resolved = svc.resolve_access(raw)
    if resolved is None:
        raise ToolError("unauthorized: invalid token")
    try:
        dek = svc.unwrap_dek(raw, resolved)
    except ValueError as e:
        raise ToolError(f"unauthorized: {e}") from e
    except InvalidUnwrap as e:
        # oauth_unwrap_dek_for_access_token's AES key-unwrap raises this (not
        # ValueError) when the envelope no longer matches this access token -
        # e.g. a concurrent refresh() rewrapped the DEK under a new token
        # between this request resolving the grant row and unwrapping its
        # envelope. Same "lost the race"/stale-token class of failure as an
        # invalid token; map it to the same clean unauthorized ToolError
        # instead of letting it propagate as an uncaught 500.
        raise ToolError("unauthorized: invalid token") from e
    services = build_services(_db_path(), resolved["user_id"], dek)
    return services, resolved["scope"]

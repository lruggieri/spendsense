"""Abstract repository for MCP API keys."""
from abc import ABC, abstractmethod
from typing import List, Optional


class MCPApiKeyRepository(ABC):
    @abstractmethod
    def create(self, key_id: str, user_id: str, token_hash: str, scope: str,
               label: str, created_at: str, expires_at: Optional[str]) -> None: ...

    @abstractmethod
    def get_by_token_hash(self, token_hash: str) -> Optional[dict]: ...

    @abstractmethod
    def list_for_user(self, user_id: str) -> List[dict]: ...

    @abstractmethod
    def touch_last_used(self, key_id: str, when_iso: str) -> None: ...

    @abstractmethod
    def revoke(self, user_id: str, key_id: str) -> bool: ...

"""Abstract repositories for OAuth 2.1 clients, authorizations, and grants."""
from abc import ABC, abstractmethod
from typing import List, Optional


class OAuthClientRepository(ABC):
    @abstractmethod
    def upsert(self, client_id: str, redirect_uris: List[str], metadata_json: str,
               created_at: str) -> None: ...

    @abstractmethod
    def get(self, client_id: str) -> Optional[dict]: ...


class OAuthAuthorizationRepository(ABC):
    @abstractmethod
    def create_pending(self, txn_id: str, client_id: str, params_json: str,
                        created_at: str, expires_at: str) -> None: ...

    @abstractmethod
    def get_pending(self, txn_id: str) -> Optional[dict]: ...

    @abstractmethod
    def delete_pending(self, txn_id: str) -> None: ...

    @abstractmethod
    def create_code(self, code_hash: str, client_id: str, user_id: str, scopes_json: str,
                     code_challenge: str, redirect_uri: str, redirect_uri_explicit: int,
                     resource: Optional[str], expires_at: str) -> None: ...

    @abstractmethod
    def get_code(self, code_hash: str) -> Optional[dict]: ...

    @abstractmethod
    def delete_code(self, code_hash: str) -> None: ...


class OAuthGrantRepository(ABC):
    @abstractmethod
    def create(self, grant_id: str, user_id: str, client_id: str, scope: str,
               at_hash: str, at_salt: str, at_expires_at: str,
               rt_hash: str, rt_salt: str, rt_expires_at: str,
               created_at: str) -> None: ...

    @abstractmethod
    def get_by_at_hash(self, at_hash: str) -> Optional[dict]: ...

    @abstractmethod
    def get_by_rt_hash(self, rt_hash: str) -> Optional[dict]: ...

    @abstractmethod
    def rotate(self, grant_id: str, at_hash: str, at_salt: str, at_expires_at: str,
               rt_hash: str, rt_salt: str, rt_expires_at: str,
               prev_rt_hash: str, prev_rt_expires_at: str) -> None: ...

    @abstractmethod
    def revoke_by_grant_id(self, grant_id: str) -> None: ...

    @abstractmethod
    def revoke_by_at_hash(self, at_hash: str) -> None: ...

    @abstractmethod
    def revoke_by_rt_hash(self, rt_hash: str) -> None: ...

"""Abstract repositories for OAuth 2.1 clients, authorizations, and grants."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class OAuthEnvelopeRewrite:
    """Already-computed DEK envelope bytes for an encrypted-account rotation.

    Carries only inert bytes/strings, never raw token secrets or the DEK
    itself. The crypto (deriving a KEK from the new access/refresh token
    and wrapping the DEK under it) is pure computation with no DB
    dependency, so it happens BEFORE `rotate_with_envelopes`'s transaction
    opens - the transaction only persists these precomputed values, plus
    preserves whatever the CURRENT `oauthrt:{grant_id}` envelope is (read
    fresh inside that same transaction) under a `:prev` slot.
    """

    user_id: str
    new_at_wrapped: bytes
    new_at_salt_b64: str
    new_rt_wrapped: bytes
    new_rt_salt_b64: str


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

    @abstractmethod
    def consume_code(self, code_hash: str) -> Optional[dict]: ...


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
               prev_rt_hash: str, prev_rt_expires_at: str) -> bool:
        """Atomically rotate a grant's access/refresh token pair.

        `prev_rt_hash` must be the `rt_hash` value the caller observed when it
        read the grant row (i.e. the refresh token hash being rotated away
        from). This doubles as an optimistic-concurrency guard: the UPDATE
        only applies if the row's *current* `rt_hash` still equals
        `prev_rt_hash` at write time. If a concurrent `rotate()` already won
        the race and changed `rt_hash`, this call matches zero rows and
        returns False so the caller can discard its freshly minted (but now
        orphaned) token pair instead of returning it as valid.

        Returns:
            True if the row was updated, False if a concurrent rotation had
            already moved the row out from under this call.
        """
        ...

    @abstractmethod
    def rotate_with_envelopes(
        self, grant_id: str, at_hash: str, at_salt: str, at_expires_at: str,
        rt_hash: str, rt_salt: str, rt_expires_at: str,
        prev_rt_hash: str, prev_rt_expires_at: str,
        envelopes: Optional[OAuthEnvelopeRewrite] = None,
    ) -> bool:
        """Atomically rotate the grant row AND (for encrypted accounts) its
        DEK envelopes, as ONE single database transaction.

        Same CAS semantics as `rotate()` for the grants-table update
        (`prev_rt_hash` is both the WHERE-clause guard and the new
        `prev_rt_hash` column value). Additionally, when `envelopes` is
        given, the DEK envelope rewrite (backing up the current
        `oauthrt:{grant_id}` envelope to `oauthrt:{grant_id}:prev`, then
        writing the new `oauthat:{grant_id}` / `oauthrt:{grant_id}`
        envelopes) happens inside the SAME transaction as the grants-table
        CAS, so a competing process's rotate attempt on the same grant is
        genuinely serialized (blocked until this transaction commits or
        rolls back) rather than merely racing to a wrong-but-plausible
        final state. Either the whole rotation (grant row + all envelope
        writes) commits, or none of it does - there is no window where a
        partial rotation is visible to another connection.

        Returns:
            True if the row was updated (and envelopes, if given, written).
            False if a concurrent rotation had already moved the row out
            from under this call - the entire transaction (including any
            envelope writes) is rolled back, so nothing partial persists.
        """
        ...

    @abstractmethod
    def revoke_by_grant_id(self, grant_id: str) -> None: ...

    @abstractmethod
    def revoke_by_at_hash(self, at_hash: str) -> None: ...

    @abstractmethod
    def revoke_by_rt_hash(self, rt_hash: str) -> None: ...

import asyncio, tempfile, os, pytest
from mcp.shared.auth import OAuthClientInformationFull
from mcp.server.auth.provider import AuthorizationParams
from presentation.mcp_server.oauth_provider import SpendSenseOAuthProvider

@pytest.fixture
def provider(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd)
    monkeypatch.setenv("MCP_BASE_URL", "https://spendsense.dev")
    yield SpendSenseOAuthProvider(db_path=path); os.remove(path)

def test_register_and_get_client(provider):
    ci = OAuthClientInformationFull(client_id="cid", redirect_uris=["http://localhost:9/callback"])
    asyncio.run(provider.register_client(ci))
    got = asyncio.run(provider.get_client("cid"))
    assert got is not None and str(got.redirect_uris[0]) == "http://localhost:9/callback"

def test_authorize_returns_consent_redirect(provider):
    ci = OAuthClientInformationFull(client_id="cid", redirect_uris=["http://localhost:9/callback"])
    asyncio.run(provider.register_client(ci))
    params = AuthorizationParams(state="st", scopes=["read"], code_challenge="chal",
        redirect_uri="http://localhost:9/callback", redirect_uri_provided_explicitly=True, resource=None)
    url = asyncio.run(provider.authorize(ci, params))
    assert url.startswith("https://spendsense.dev/mcp-consent?txn=")

def test_full_code_exchange_bridges_dek(provider):
    import base64, os, asyncio
    from mcp.shared.auth import OAuthClientInformationFull
    svc = provider.service
    dek = base64.b64encode(os.urandom(32)).decode()
    pending = {"client_id":"cid","scopes":["read"],"code_challenge":"chal",
               "redirect_uri":"http://localhost:9/callback","redirect_uri_provided_explicitly":True,"resource":None}
    raw_code = svc.issue_code("u@x", pending, dek)
    ci = OAuthClientInformationFull(client_id="cid", redirect_uris=["http://localhost:9/callback"])
    ac = asyncio.run(provider.load_authorization_code(ci, raw_code))
    assert ac is not None and ac.client_id == "cid"
    tok = asyncio.run(provider.exchange_authorization_code(ci, ac))
    assert tok.access_token and tok.refresh_token
    # the minted AT unwraps the SAME dek via the grant
    resolved = svc.resolve_access(tok.access_token)
    assert resolved["user_id"] == "u@x"
    assert svc.unwrap_dek(tok.access_token, resolved) == dek
    # code + its envelope are consumed
    assert asyncio.run(provider.load_authorization_code(ci, raw_code)) is None

def test_load_authorization_code_rejects_wrong_client(provider):
    svc = provider.service
    pending = {"client_id":"cid","scopes":["read"],"code_challenge":"chal",
               "redirect_uri":"http://localhost:9/callback","redirect_uri_provided_explicitly":True,"resource":None}
    raw_code = svc.issue_code("u@x", pending, None)
    other_ci = OAuthClientInformationFull(client_id="other", redirect_uris=["http://localhost:9/callback"])
    assert asyncio.run(provider.load_authorization_code(other_ci, raw_code)) is None

def test_exchange_code_without_dek_yields_no_envelope(provider):
    svc = provider.service
    pending = {"client_id":"cid","scopes":["read"],"code_challenge":"chal",
               "redirect_uri":"http://localhost:9/callback","redirect_uri_provided_explicitly":True,"resource":None}
    raw_code = svc.issue_code("u@x", pending, None)
    ci = OAuthClientInformationFull(client_id="cid", redirect_uris=["http://localhost:9/callback"])
    ac = asyncio.run(provider.load_authorization_code(ci, raw_code))
    tok = asyncio.run(provider.exchange_authorization_code(ci, ac))
    resolved = svc.resolve_access(tok.access_token)
    assert svc.unwrap_dek(tok.access_token, resolved) is None

def test_exchange_unknown_code_raises_invalid_grant(provider):
    from mcp.server.auth.provider import AuthorizationCode, TokenError
    ci = OAuthClientInformationFull(client_id="cid", redirect_uris=["http://localhost:9/callback"])
    fake_ac = AuthorizationCode(
        code="bogus", scopes=["read"], expires_at=9999999999.0, client_id="cid",
        code_challenge="chal", redirect_uri="http://localhost:9/callback",
        redirect_uri_provided_explicitly=True, resource=None,
    )
    with pytest.raises(TokenError):
        asyncio.run(provider.exchange_authorization_code(ci, fake_ac))

def test_replaying_a_consumed_code_raises_invalid_grant_not_assertion_error(provider):
    """Regression test for the TOCTOU race: a code must be single-use.

    Exchanging the same authorization code twice must never crash with an
    uncaught AssertionError from the DEK-unwrap path (which happened when a
    second read-then-delete exchange found the code row but its envelope had
    already been deleted by the first exchange). The second attempt must
    cleanly raise TokenError(invalid_grant), exactly like an unknown code.
    """
    from mcp.server.auth.provider import TokenError
    import base64, os as _os

    svc = provider.service
    dek = base64.b64encode(_os.urandom(32)).decode()
    pending = {"client_id": "cid", "scopes": ["read"], "code_challenge": "chal",
               "redirect_uri": "http://localhost:9/callback",
               "redirect_uri_provided_explicitly": True, "resource": None}
    raw_code = svc.issue_code("u@x", pending, dek)
    ci = OAuthClientInformationFull(client_id="cid", redirect_uris=["http://localhost:9/callback"])
    ac = asyncio.run(provider.load_authorization_code(ci, raw_code))
    assert ac is not None

    # First exchange succeeds and consumes the code.
    tok = asyncio.run(provider.exchange_authorization_code(ci, ac))
    assert tok.access_token and tok.refresh_token

    # Replaying the same code must fail cleanly (invalid_grant), not crash.
    with pytest.raises(TokenError):
        asyncio.run(provider.exchange_authorization_code(ci, ac))

def test_concurrent_exchange_of_same_code_only_one_winner():
    """Two threads racing exchange_code() on the SAME code: exactly one wins.

    This exercises the atomic consume_code() DELETE...RETURNING claim
    directly against OAuthService (bypassing the async provider layer, since
    threads need a synchronous call). Before the fix, both threads could
    pass a read-then-delete check and mint two independent token pairs.
    """
    import threading
    from application.services.oauth_service import OAuthService

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        svc = OAuthService(db_path=path)
        pending = {"client_id": "cid", "scopes": ["read"], "code_challenge": "chal",
                   "redirect_uri": "http://localhost:9/callback",
                   "redirect_uri_provided_explicitly": True, "resource": None}
        raw_code = svc.issue_code("u@x", pending, None)

        results = [None, None]

        def worker(i):
            results[i] = svc.exchange_code("cid", raw_code)

        t1 = threading.Thread(target=worker, args=(0,))
        t2 = threading.Thread(target=worker, args=(1,))
        t1.start(); t2.start()
        t1.join(); t2.join()

        non_none = [r for r in results if r is not None]
        assert len(non_none) == 1
        assert results.count(None) == 1
    finally:
        os.remove(path)

def test_refresh_rotates_and_preserves_dek(provider):
    import base64, os, asyncio
    from mcp.shared.auth import OAuthClientInformationFull
    svc = provider.service
    dek = base64.b64encode(os.urandom(32)).decode()
    pending = {"client_id":"cid","scopes":["read"],"code_challenge":"c","redirect_uri":"http://localhost:9/callback","redirect_uri_provided_explicitly":True,"resource":None}
    ci = OAuthClientInformationFull(client_id="cid", redirect_uris=["http://localhost:9/callback"])
    raw_code = svc.issue_code("u@x", pending, dek)
    ac = asyncio.run(provider.load_authorization_code(ci, raw_code))
    tok1 = asyncio.run(provider.exchange_authorization_code(ci, ac))
    rt1 = tok1.refresh_token
    rtobj = asyncio.run(provider.load_refresh_token(ci, rt1))
    tok2 = asyncio.run(provider.exchange_refresh_token(ci, rtobj, ["read"]))
    assert tok2.access_token != tok1.access_token and tok2.refresh_token != rt1
    r2 = svc.resolve_access(tok2.access_token)
    assert svc.unwrap_dek(tok2.access_token, r2) == dek        # DEK preserved across rotation
    # grace: old RT still resolves briefly
    assert asyncio.run(provider.load_refresh_token(ci, rt1)) is not None
    # old AT no longer valid
    assert svc.resolve_access(tok1.access_token) is None

def test_refresh_unknown_token_raises_invalid_grant(provider):
    import asyncio
    from mcp.server.auth.provider import RefreshToken, TokenError
    ci = OAuthClientInformationFull(client_id="cid", redirect_uris=["http://localhost:9/callback"])
    assert asyncio.run(provider.load_refresh_token(ci, "bogus-rt")) is None
    fake = RefreshToken(token="bogus-rt", client_id="cid", scopes=["read"])
    with pytest.raises(TokenError):
        asyncio.run(provider.exchange_refresh_token(ci, fake, ["read"]))

def test_refresh_rejects_wrong_client(provider):
    import base64, os, asyncio
    svc = provider.service
    pending = {"client_id":"cid","scopes":["read"],"code_challenge":"c","redirect_uri":"http://localhost:9/callback","redirect_uri_provided_explicitly":True,"resource":None}
    ci = OAuthClientInformationFull(client_id="cid", redirect_uris=["http://localhost:9/callback"])
    raw_code = svc.issue_code("u@x", pending, None)
    ac = asyncio.run(provider.load_authorization_code(ci, raw_code))
    tok1 = asyncio.run(provider.exchange_authorization_code(ci, ac))

    other_ci = OAuthClientInformationFull(client_id="other", redirect_uris=["http://localhost:9/callback"])
    assert asyncio.run(provider.load_refresh_token(other_ci, tok1.refresh_token)) is None
    assert svc.refresh("other", tok1.refresh_token, ["read"]) is None

def test_refresh_revoked_grant_refuses(provider):
    import asyncio
    svc = provider.service
    pending = {"client_id":"cid","scopes":["read"],"code_challenge":"c","redirect_uri":"http://localhost:9/callback","redirect_uri_provided_explicitly":True,"resource":None}
    ci = OAuthClientInformationFull(client_id="cid", redirect_uris=["http://localhost:9/callback"])
    raw_code = svc.issue_code("u@x", pending, None)
    ac = asyncio.run(provider.load_authorization_code(ci, raw_code))
    tok1 = asyncio.run(provider.exchange_authorization_code(ci, ac))

    resolved = svc.resolve_access(tok1.access_token)
    svc._grant_repo.revoke_by_grant_id(resolved["grant_id"])

    assert svc.refresh("cid", tok1.refresh_token, ["read"]) is None
    assert asyncio.run(provider.load_refresh_token(ci, tok1.refresh_token)) is None

def test_refresh_expired_rt_refuses(provider, monkeypatch):
    import asyncio
    from datetime import datetime, timedelta, timezone
    svc = provider.service
    pending = {"client_id":"cid","scopes":["read"],"code_challenge":"c","redirect_uri":"http://localhost:9/callback","redirect_uri_provided_explicitly":True,"resource":None}
    ci = OAuthClientInformationFull(client_id="cid", redirect_uris=["http://localhost:9/callback"])
    raw_code = svc.issue_code("u@x", pending, None)
    ac = asyncio.run(provider.load_authorization_code(ci, raw_code))
    tok1 = asyncio.run(provider.exchange_authorization_code(ci, ac))

    monkeypatch.setattr(svc, "_now", lambda: datetime.now(timezone.utc) + timedelta(days=31))
    assert svc.refresh("cid", tok1.refresh_token, ["read"]) is None

def test_sequential_refresh_with_same_rt_yields_exactly_one_success_then_grace_success(provider):
    """Two refresh() calls presenting the SAME refresh token, one after another.

    The first call rotates the grant. The second call reuses the very same
    (now just-rotated-away) refresh token - this is the grace-window retry
    scenario the plan calls out explicitly, and must succeed cleanly rather
    than hard-failing. Critically, once the second (grace) rotation lands,
    the first call's access token must no longer be valid - there must never
    be two independently-valid token pairs alive for the same grant.
    """
    import base64, os, asyncio
    svc = provider.service
    dek = base64.b64encode(os.urandom(32)).decode()
    pending = {"client_id":"cid","scopes":["read"],"code_challenge":"c","redirect_uri":"http://localhost:9/callback","redirect_uri_provided_explicitly":True,"resource":None}
    ci = OAuthClientInformationFull(client_id="cid", redirect_uris=["http://localhost:9/callback"])
    raw_code = svc.issue_code("u@x", pending, dek)
    ac = asyncio.run(provider.load_authorization_code(ci, raw_code))
    tok0 = asyncio.run(provider.exchange_authorization_code(ci, ac))
    rt0 = tok0.refresh_token

    result1 = svc.refresh("cid", rt0, ["read"])
    assert result1 is not None

    # Retry with the SAME original RT (grace window, RT_GRACE_SECONDS=30s).
    result2 = svc.refresh("cid", rt0, ["read"])
    assert result2 is not None
    assert result2["access_token"] != result1["access_token"]
    assert result2["refresh_token"] != result1["refresh_token"]

    # Exactly one access token is live at a time: the second rotation must
    # have invalidated the first's.
    assert svc.resolve_access(result1["access_token"]) is None
    r2 = svc.resolve_access(result2["access_token"])
    assert r2 is not None
    assert svc.unwrap_dek(result2["access_token"], r2) == dek

    # A third attempt with the now-doubly-stale original RT must fail: it
    # is neither the current rt_hash nor the current prev_rt_hash anymore.
    assert svc.refresh("cid", rt0, ["read"]) is None

def test_concurrent_refresh_of_same_rt_never_yields_two_live_pairs():
    """Two threads racing refresh() on the SAME refresh token.

    Exercises OAuthService's internal serialization (the `_refresh_lock`
    plus `rotate()`'s SQL-level compare-and-swap) directly, the same way
    `test_concurrent_exchange_of_same_code_only_one_winner` exercises code
    exchange. Both calls may legitimately succeed (the loser is honored as a
    grace-window retry of the just-rotated-away RT, per the plan), but the
    outcome must never be a crash, and at no point may two independently
    resolvable access tokens both unwrap the DEK from the same original RT -
    only the most-recently-rotated pair may ever be live.
    """
    import base64, os as _os, threading
    from application.services.oauth_service import OAuthService

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        svc = OAuthService(db_path=path)
        dek = base64.b64encode(_os.urandom(32)).decode()
        pending = {"client_id": "cid", "scopes": ["read"], "code_challenge": "chal",
                   "redirect_uri": "http://localhost:9/callback",
                   "redirect_uri_provided_explicitly": True, "resource": None}
        raw_code = svc.issue_code("u@x", pending, dek)
        tok0 = svc.exchange_code("cid", raw_code)
        assert tok0 is not None
        rt0 = tok0["refresh_token"]

        results = [None, None]

        def worker(i):
            results[i] = svc.refresh("cid", rt0, ["read"])

        t1 = threading.Thread(target=worker, args=(0,))
        t2 = threading.Thread(target=worker, args=(1,))
        t1.start(); t2.start()
        t1.join(); t2.join()

        # No crash, and never a totally-silent double failure.
        assert results.count(None) < 2

        resolvable = []
        for r in results:
            if r is None:
                continue
            resolved = svc.resolve_access(r["access_token"])
            if resolved is not None:
                resolvable.append((r, resolved))

        # At most one of the two returned pairs may still be resolvable -
        # whichever rotation landed last. The other, if it "succeeded" at
        # the service layer, must already be dead.
        assert len(resolvable) == 1
        live_result, live_resolved = resolvable[0]
        assert svc.unwrap_dek(live_result["access_token"], live_resolved) == dek
    finally:
        os.remove(path)


# =============================================================================
# load_access_token / revoke_token (Task 6): unifies OAuth grants + legacy
# manually-created API keys.
# =============================================================================


def test_load_access_token_resolves_oauth_grant(provider):
    import asyncio
    svc = provider.service
    pending = {"client_id": "cid", "scopes": ["read"], "code_challenge": "c",
               "redirect_uri": "http://localhost:9/callback",
               "redirect_uri_provided_explicitly": True, "resource": None}
    raw_code = svc.issue_code("u@x", pending, None)
    result = svc.exchange_code("cid", raw_code)

    at = asyncio.run(provider.load_access_token(result["access_token"]))
    assert at is not None
    assert at.token == result["access_token"]
    assert at.scopes == ["read"]
    grant = svc.resolve_access(result["access_token"])
    assert at.client_id == grant["grant_id"]


def test_load_access_token_resolves_legacy_api_key(provider):
    import asyncio, base64
    from infrastructure.crypto.encryption import generate_dek

    svc = provider.service
    dek_b64 = base64.b64encode(generate_dek()).decode("ascii")
    raw = svc._encryption.create_mcp_api_key("u@x", "readwrite", "laptop", None, dek_b64)

    at = asyncio.run(provider.load_access_token(raw))
    assert at is not None
    assert at.token == raw
    assert at.scopes == ["readwrite"]
    # Legacy keys have no OAuth client - falls back to the SpendSense user id.
    assert at.client_id == "u@x"


def test_load_access_token_garbage_returns_none(provider):
    import asyncio
    assert asyncio.run(provider.load_access_token("totally-bogus-token")) is None


def test_revoke_token_kills_the_oauth_grant(provider):
    import asyncio
    from mcp.server.auth.provider import AccessToken

    svc = provider.service
    pending = {"client_id": "cid", "scopes": ["read"], "code_challenge": "c",
               "redirect_uri": "http://localhost:9/callback",
               "redirect_uri_provided_explicitly": True, "resource": None}
    raw_code = svc.issue_code("u@x", pending, None)
    result = svc.exchange_code("cid", raw_code)

    token_obj = AccessToken(token=result["access_token"], client_id="cid", scopes=["read"])
    asyncio.run(provider.revoke_token(token_obj))

    assert svc.resolve_access(result["access_token"]) is None


def test_revoke_token_is_a_noop_for_legacy_api_key(provider):
    import asyncio, base64
    from infrastructure.crypto.encryption import generate_dek
    from mcp.server.auth.provider import AccessToken

    svc = provider.service
    dek_b64 = base64.b64encode(generate_dek()).decode("ascii")
    raw = svc._encryption.create_mcp_api_key("u@x", "read", "laptop", None, dek_b64)

    token_obj = AccessToken(token=raw, client_id="u@x", scopes=["read"])
    asyncio.run(provider.revoke_token(token_obj))  # must not raise

    assert svc.resolve_access(raw) is not None

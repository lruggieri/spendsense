# MCP OAuth Authentication — Design

**Status:** Design agreed + double-checked against the installed `mcp` SDK and
codebase (crypto primitives, wrapped-DEK repo, OAuth provider surface all
verified). Not yet implemented.
**Owner decisions:** locked (see [Decisions](#decisions)).
**Goal:** Let interactive MCP clients (Claude Code, claude.ai) connect to SpendSense's
MCP server via standard OAuth 2.1 (discovery → dynamic client registration →
auth-code + PKCE) instead of a hand-copied API key — **without** weakening the
existing end-to-end encryption guarantee.

This document is written so a fresh session/agent can pick the work up cold. It
records *why* as well as *what*, because the encryption interaction is subtle.

---

## 1. Context: how MCP auth works today

The MCP server lives under `presentation/mcp_server/`. Today it is a bearer-token
**resource server** only:

- User creates an MCP API key in the web UI: `POST /api/mcp-keys/create`
  (`presentation/web/blueprints/api_keys.py`) → `EncryptionService.create_mcp_api_key()`
  (`application/services/encryption_service.py`). Raw key shown once.
- User pastes it into their MCP client config as `Authorization: Bearer <key>`.
- Per request: `SpendSenseTokenVerifier.verify_token()`
  (`presentation/mcp_server/auth.py`) hashes the token, looks it up, returns an
  `AccessToken(client_id=user_id, scopes=[scope])`.
- `get_tool_context()` (same file) then unwraps the DEK and builds services.

The FastMCP instance is created in `presentation/mcp_server/server.py`
(`create_mcp_app()`), configured with `token_verifier=SpendSenseTokenVerifier()`
and `AuthSettings(issuer_url=..., resource_server_url=...)`. It does **not**
currently implement an OAuth authorization server.

### 1.1 The critical constraint — the API key is ALSO a decryption key

SpendSense uses envelope encryption. Transactions are encrypted with a per-user
**DEK** (Data Encryption Key). The DEK is never stored in plaintext; the DB stores
**wrapped DEK** rows ("envelopes"), one per wrapper, via
`EncryptionRepository.store_wrapped_dek(user_id, wrapper_id, wrapped, salt, wrapper_type)`.
A single user has several envelopes wrapping the *same* DEK:

- one per **passkey** (WebAuthn credential) — default `wrapper_type`
- one per **API key** — `wrapper_type="apikey"`

When an API key is created for an encrypted account, `create_mcp_api_key()` does:

```python
salt = os.urandom(16)
kek = hkdf_derive_kek(raw_key, salt)          # KEK derived FROM the raw key
wrapped = wrap_key(base64.b64decode(dek_b64), kek)
store_wrapped_dek(user_id, key_id, wrapped, salt_b64, wrapper_type="apikey")
```

So the raw API key does **double duty**: (1) identity/authz, and (2) it *is* the
secret that derives the KEK that unwraps the DEK. Per request,
`unwrap_dek_for_api_key(raw)` re-derives that KEK. **Consequence: the server DB
alone cannot decrypt an encrypted account — it needs a client-presented secret.**
This is the property we must preserve.

Note: `dek_b64` comes from `g.encryption_key` — set by the web `before_request`
hook `extract_encryption_key()` (`presentation/web/app.py`) from the
`X-Encryption-Key` header or `encryption_key` cookie. The browser holds the
plaintext DEK (unlocked via passkey PRF) and ships it per request; the server
never persists it. See `presentation/web/static/js/passkey-manager.js`
(`authenticateWithPRF`, `syncCookie`, the `fetch` interceptor).

### 1.2 Why OAuth collides with this

OAuth 2.1 access tokens are **server-minted, short-lived, and rotate**. You can't
derive a durable KEK from an ephemeral token the way you can from a static API
key. So OAuth forces a decision about where the DEK-unwrapping capability lives.
For **unencrypted** accounts there's no DEK to unwrap — trivial. All the
complexity below is only for **encrypted** accounts.

---

## 2. Decisions

All three were explicitly chosen by the owner:

1. **Encryption model = zero-knowledge (token-derived KEK).** Preserve today's
   "server DB alone can't decrypt" property. Derive the KEK from the client-held
   token and re-wrap the DEK on token rotation. (Chosen over the simpler
   "server master key" model, and over "OAuth for unencrypted accounts only".)
2. **AS topology = reuse existing Google login + passkey unlock.** SpendSense
   hosts the OAuth endpoints, but `/authorize` reuses the existing Google OAuth
   login and passkey PRF unlock, then shows a consent screen. The DEK lands in
   `g.encryption_key` exactly as it does for the web app today.
3. **Back-compat = keep both.** OAuth becomes the default for interactive
   clients; the manual API-key path stays (scripts/CI, and as the encrypted-
   account fallback when inline passkey unlock isn't possible — see §6).

---

## 3. The token + envelope model (the heart of the design)

### 3.1 Key realization

On every MCP tool call the only secret the client sends is the **access token
(AT)**. The **refresh token (RT)** is sent *only* to `/token`. Therefore:

- To decrypt on each tool call, the DEK must be unwrappable **from the AT**.
- The AT rotates, so something must survive rotation and re-create the AT-keyed
  envelope *without* a passkey re-prompt. That something is the **RT**.

So we maintain **two envelopes around the same DEK** (reusing existing crypto:
`hkdf_derive_kek`, `wrap_key`, `unwrap_key`, `store_wrapped_dek`, `get_wrapped_dek`):

| `wrapper_type` | KEK derived from        | keyed by (`wrapper_id`) | purpose                                   |
|----------------|-------------------------|-------------------------|-------------------------------------------|
| `oauth_at`     | `hkdf_derive_kek(AT, s)`| access-token id         | per-request unwrap (hot path)             |
| `oauth_rt`     | `hkdf_derive_kek(RT, s)`| grant id                | survive AT rotation without passkey       |

Both wrap the identical DEK — same secret, two locks. Same "one DEK, many
envelopes" pattern already used for passkeys + API keys.

**AT and RT** = Access Token / Refresh Token (standard OAuth). AT = day pass shown
at every request; RT = membership card shown only at `/token` to get a new day pass.

### 3.2 Lifecycle

**A. Consent (Flask consent page — the only step that needs the passkey).**
The SDK's `/authorize` handler calls `provider.authorize()`, which returns a
redirect to a **Flask consent/unlock page** (§4). There the user does Google
login + passkey unlock, so the plaintext DEK is in `g.encryption_key` (same spot
`create_mcp_api_key()` reads today), and approves the scope.

> **CRITICAL — DEK bridge via the authorization code.** The token envelopes are
> keyed to AT/RT, but AT/RT are minted later at `/token`
> (`exchange_authorization_code`) — a **back-channel call with no browser, so the
> DEK is NOT available there.** The DEK only exists here, at consent. So we must
> carry it across the gap using the authorization `code` as the transport secret:
>
> On consent approval (encrypted accounts):
> 1. Generate `code` (≥160 bits entropy, per RFC 6749 / SDK docstring).
> 2. Store the code record: `hash(code)`, client_id, user_id, scope, PKCE
>    `code_challenge`, `redirect_uri`, expiry (short, e.g. 60s), single-use.
> 3. `KEK_code = hkdf_derive_kek(code, salt_code)`; store an **`oauth_code`
>    envelope** = `wrap(DEK, KEK_code)` keyed by the code record.
> 4. Redirect the browser to the client's `redirect_uri` with `?code&state`.
> 5. Discard the plaintext DEK.
>
> Then at `/token` → `exchange_authorization_code(client, code_obj)`:
> 1. (SDK validates PKCE `S256(verifier)==challenge` and code before calling us.)
> 2. Recover the DEK: `KEK_code = hkdf_derive_kek(code, salt_code)` → unwrap the
>    `oauth_code` envelope. **Note the provider only receives the validated code
>    object, not the raw PKCE `code_verifier`** — so the KEK is bound to the code
>    secret, mitigated by single-use + short TTL + storing only `hash(code)`.
> 3. Mint AT + RT; create the `oauth_at` + `oauth_rt` envelopes from the DEK.
> 4. Delete the `oauth_code` envelope and the code record; discard plaintext DEK.
> 5. Return `OAuthToken(access_token=AT, refresh_token=RT, expires_in, scope)`.
>
> For **unencrypted** accounts, skip all envelope steps entirely.

**B. Steady-state tool call (hot path — barely changes).**
```
request: Authorization: Bearer <AT>
  → verify AT: hash-lookup → user_id + scope           (like today's verify_token)
  → KEK_AT = hkdf_derive_kek(AT, salt_at); unwrap oauth_at → DEK
  → build_services(db, user_id, DEK); run tool
```
This is a near-copy of today's `unwrap_dek_for_api_key(raw)` in
`get_tool_context()` — swap "raw API key" for "access token".

**C. Refresh (AT expired).**
```
POST /token  grant_type=refresh_token  refresh_token=<RT>
  1. hash(RT) → look up grant; check not revoked/expired
  2. KEK_RT = hkdf_derive_kek(RT, salt_rt); unwrap oauth_rt → DEK   (NO passkey)
  3. mint AT_new; wrap DEK under hkdf_derive_kek(AT_new,·) → new oauth_at row;
     delete old oauth_at row
  4. rotate RT: mint RT_new; re-wrap DEK → new oauth_rt row; delete old; invalidate old RT
  5. return {access_token: AT_new, refresh_token: RT_new, expires_in}
  6. discard plaintext DEK
```
The RT is a **portable re-unlock**: after initial consent the client regenerates
AT-envelopes forever via refresh; the passkey/Google login is never needed again
until the grant is revoked or the RT is lost.

**D. Revocation / lost RT.** Revoke = delete the grant row + both envelopes. The
DEK itself is untouched (passkey and API-key envelopes still work). Lost RT →
user re-runs `/authorize`. No data loss ever — we only add/remove outer
envelopes, never re-encrypt transaction ciphertext.

### 3.3 Zero-knowledge-at-rest — preserved

At rest the DB holds only `hash(AT)`, `hash(RT)`, and the two envelopes (each
needs a plaintext token to open). No plaintext DEK, no plaintext tokens. A DB dump
alone can't decrypt — identical guarantee to today's API keys. The server sees
AT/RT transiently (it must, to verify), just as it sees the API key per request
today.

### 3.4 The genuinely tricky bits (do not skip)

- **Refresh races / RT rotation — RESOLVED.** Two concurrent refreshes with the same
  RT are serialized via a single SQLite transaction (`BEGIN IMMEDIATE`) spanning
  *both* the grants-row compare-and-swap *and* the DEK-envelope rewrites
  (`OAuthGrantRepository.rotate_with_envelopes`) — this matters because the codebase
  is deployed as 4 separate `gunicorn` worker processes sharing one SQLite file, so
  an in-process lock alone (the first cut of this fix) is not sufficient — only the
  database's own file-level lock actually protects across separate OS processes.
  Verified with a real `multiprocessing`-based test plus deliberate fault
  injection (reproducing the original corrupt-DEK bug, then confirming the fix
  prevents it). A short **reuse grace window** (`prev_rt_hash`) means a lost
  `/token` response doesn't brick the client.
- **AT TTL is a dial.** Short TTL (15–60 min) = frequent refreshes, each doing one
  cheap AES unwrap+rewrap. Long TTL ≈ "OAuth-issued API key" (refresh rarely runs).
  Start conservative.
- **Per-grant isolation.** Each authorized client gets its own envelope pair;
  revoking one doesn't touch others.

---

## 4. HTTP surface & deployment topology

SpendSense becomes an OAuth 2.1 **Authorization Server + Resource Server**. It
already is an OAuth *client* to Google (for login) — that's unrelated and stays.

**VERIFIED against the installed SDK** (`lib/python3.13/site-packages/mcp`,
inspected during design double-check):

- `FastMCP.__init__` accepts `auth_server_provider=` (alongside `token_verifier=`,
  `auth=`, `transport_security=`).
- `mcp.server.auth.provider.OAuthAuthorizationServerProvider` methods (exact):
  `authorize`, `exchange_authorization_code`, `exchange_refresh_token`,
  `get_client`, `load_access_token`, `load_authorization_code`,
  `load_refresh_token`, `register_client`, `revoke_token`.
- `authorize(self, client, params) -> str` **returns a redirect URL.** Its
  docstring describes the exact "MCP server redirects to a login page, then a
  return-flow handler generates + stores the auth code" pattern we use.
- `AuthorizationParams` fields: `state, scopes, code_challenge, redirect_uri,
  redirect_uri_provided_explicitly, resource`.
- **The SDK mounts the AS routes itself** at fixed root paths (from
  `mcp.server.auth.routes`): `AUTHORIZATION_PATH=/authorize`, `TOKEN_PATH=/token`,
  `REGISTRATION_PATH=/register`, `REVOCATION_PATH=/revoke`, plus metadata via
  `create_auth_routes` / `create_protected_resource_routes` / `MetadataHandler`.
  DCR is gated by `AuthSettings.client_registration_options`
  (`ClientRegistrationOptions(enabled=True, valid_scopes=[...], default_scopes=[...])`).

**Corrected topology — the SDK owns the OAuth endpoints, NOT Flask:**

- **FastMCP (Starlette/ASGI) serves:** `/mcp`, `/authorize`, `/token`, `/register`,
  `/revoke`, `/.well-known/oauth-authorization-server`,
  `/.well-known/oauth-protected-resource`. We do **not** hand-write these in Flask.
- **Flask serves the consent/unlock page** that `provider.authorize()` redirects
  to (e.g. `GET/POST /mcp-consent`). This is where Google login + passkey PRF +
  consent happen. **It must be a top-level page on `spendsense.dev`** (WebAuthn
  PRF requires it — §6). This page is the "return-flow handler": on approval it
  generates the auth `code`, stores the `oauth_code` envelope (§3.2A), and
  redirects to `params.redirect_uri` with `?code&state`.
- `provider.authorize()` itself must **not** need the DEK/browser — it just
  persists a pending-authorization record (client + params, keyed by a signed
  state/txn id) and returns the `/mcp-consent?txn=...` URL.

**Deployment consequence — RESOLVED.** A `presentation/asgi.py` entrypoint was added
(pre-dating the OAuth implementation) that already implements the single-ASGI-server
option: it builds `mcp.streamable_http_app()`, wraps the Flask app via
`asgiref.wsgi.WsgiToAsgi`, and dispatches every request by path — anything matching a
FastMCP-registered route (`/mcp`, `/authorize`, `/token`, `/register`, `/revoke`,
`/.well-known/oauth-*` once `auth_server_provider` is wired in) goes to the FastMCP app;
everything else (`/mcp-consent`, Google login, passkeys) falls through to Flask. Both are
same-origin on `spendsense.dev`, one process type, no nginx path-routing needed. Deployed
as `gunicorn -k uvicorn.workers.UvicornWorker -w 4 presentation.asgi:app` — **4 separate
OS processes** sharing one SQLite file, which is why refresh-token rotation had to be made
atomic at the database-transaction level (`OAuthGrantRepository.rotate_with_envelopes`,
§3.4) rather than relying on an in-process lock. No deploy/topology change is needed to
ship this feature — the existing `asgi.py`/gunicorn command already serves it correctly.

Redirect URI: Claude Code uses `http://localhost:<port>/callback` (random port,
`--callback-port` to pin). Allow loopback redirect URIs in DCR.

---

## 5. Where it plugs into existing code

- `presentation/mcp_server/auth.py`
  - **Per-request AT verification moves to the provider.** With
    `auth_server_provider` set, the SDK verifies bearer tokens via
    `provider.load_access_token(token)` — the current `SpendSenseTokenVerifier`
    (`token_verifier`) is the RS-only path. To **keep both auth methods working
    (decision 3)**, implement `load_access_token()` to resolve *either* an OAuth AT
    *or* a legacy API key, returning the same `AccessToken(client_id=user_id,
    scopes=[scope])`. (Confirm whether the installed SDK lets `token_verifier` and
    `auth_server_provider` coexist; if not, unify both lookups inside
    `load_access_token`.)
  - `get_tool_context()` — the DEK unwrap must branch on token kind: legacy API
    key → `unwrap_dek_for_api_key(raw)` (existing); OAuth AT → new
    `unwrap_dek_for_access_token(AT)` that derives `hkdf_derive_kek(AT, salt_at)` and
    unwraps the `oauth_at` envelope. Everything downstream (`build_services`,
    rate limiting keyed on `hash_token(raw)`) is unchanged.
- `application/services/encryption_service.py`
  - Add methods mirroring `create_mcp_api_key` / `unwrap_dek_for_api_key` for the
    OAuth envelopes: create both envelopes at consent, unwrap `oauth_at` per
    request, the refresh re-wrap dance, and revoke (delete grant + both envelopes).
  - Reuse `hkdf_derive_kek`, `wrap_key`, `unwrap_key`, `hash_token` from
    `infrastructure/crypto/encryption.py`.
- **New persistence** (SQLite repositories, follow existing patterns in
  `infrastructure/persistence/sqlite/repositories/`):
  - registered OAuth clients (client_id, redirect_uris, metadata, created)
  - authorization codes (code_hash, client_id, user_id, scope, PKCE challenge,
    redirect_uri, expiry, single-use) — short TTL
  - tokens/grants (grant_id, user_id, client_id, scope, `hash(AT)`, `hash(RT)`,
    AT expiry, RT expiry, revoked, rotation bookkeeping for the grace window)
  - The `oauth_code` (transient, consent→exchange), `oauth_at`, and `oauth_rt`
    envelopes all reuse the **existing** wrapped-DEK table
    (`encryption_keys`, column `wrapper_type TEXT DEFAULT 'prf'`, keyed by
    `(user_id, credential_id)`) via new `wrapper_type` values — no new table for
    these. Existing values: `'prf'` (passkey), `'apikey'`. Add `'oauth_code'`,
    `'oauth_at'`, `'oauth_rt'`. (Repo methods `store_wrapped_dek`,
    `get_wrapped_dek`, `get_prf_salt`, `delete_wrapped_dek` already take a generic
    `credential_id` — reuse the token/code id there.)
- `presentation/web/blueprints/` — new blueprint for `/authorize`, `/token`,
  `/register`, `/.well-known/*`, consent template. Reuse `login_required` /
  session / `g.encryption_key`. Add a consent HTML template extending `base.html`.
- `presentation/mcp_server/server.py` — wire the `auth_server_provider` (or keep
  RS-only there and host the AS entirely in Flask, depending on SDK check in §4).
- `MCP_BASE_URL` already feeds `AuthSettings` + transport security; the well-known
  docs must advertise the same base URL.

---

## 6. Passkey-during-OAuth feasibility (researched)

The load-bearing assumption is that passkey **PRF** unlock can run on the
`/authorize` page. WebAuthn credentials are bound to rpId (`spendsense.dev`) and
PRF output is produced in the page, so this only works if `/authorize` is a
**genuine top-level browser context on `spendsense.dev`** (never an iframe/webview).

Findings (source: `code.claude.com/docs/en/mcp.md`):

- **Claude Code — CONFIRMED top-level.** Opens the auth URL in the system default
  browser as a top-level navigation. Tell: on redirect failure the docs say to
  *"paste the full callback URL from your browser's address bar"* — address bars
  only exist in top-level windows. Also supports DCR (RFC 7591) + discovery
  (RFC 9728 → 8414). So the existing `authenticateWithPRF()` JS is reusable there.
- **claude.ai — NOT documented, strong inference it's top-level.** Third-party
  OAuth pages are effectively never iframable (IdPs send `X-Frame-Options`/
  `frame-ancestors DENY`; browsers block cross-origin WebAuthn in iframes anyway),
  so claude.ai almost certainly opens a top-level popup/tab. **Verify empirically**
  once the flow exists.

Caveats (real-world friction, not blockers):

1. **Device locality.** The passkey must be reachable in whatever browser the OAuth
   flow opens. Local Claude Code → local platform passkey → smooth. claude.ai on a
   desktop whose passkey is only on the user's phone → cross-device **hybrid
   (caBLE)** + **PRF-over-hybrid**, which newer authenticators support but not
   universally. This is the case most likely to fail.
2. **Fresh browser session** needs Google login *then* passkey unlock inside the
   authorize flow — more steps, still just redirects.

**Fallback (why decision 3 matters):** if inline passkey unlock isn't available,
that grant can't be zero-knowledge-minted — the user falls back to creating a
manual API key in the already-unlocked web session. Graceful degradation.

---

## 7. Testing requirements (per repo CLAUDE.md)

- `make test` must pass; write tests for every new piece; target ≥80% coverage
  (`make test-coverage`). `make mypy` for types. `make check` before commit.
- Service/repository tests: real temp SQLite DBs. Blueprint tests:
  `authenticated_client` fixture + mocked service factories.
- Specific cases to cover:
  - consent creates the `oauth_code` envelope; `exchange_authorization_code`
    recovers the DEK from it, creates `oauth_at`+`oauth_rt`, deletes `oauth_code`
  - all three envelopes unwrap to the *same* DEK; DEK bridge survives consent→token
  - per-request unwrap from `oauth_at` (mirror existing api-key unwrap tests)
  - refresh: RT unwraps `oauth_rt` → new AT → new `oauth_at`; old AT envelope gone
  - RT rotation + reuse-grace-window (concurrent refresh doesn't brick)
  - revoke deletes grant + both envelopes; passkey/API-key envelopes still work
  - unencrypted account path (no DEK, no envelopes) still authorizes
  - PKCE validation; auth-code single-use + expiry; scope enforcement
    (`read` vs `readwrite`, reuse existing `require_write`)
  - discovery docs return correct base URL / metadata

---

## 8. Suggested build order

0. **Decide the serving topology** (nginx path-routing vs single ASGI + WSGI
   mount — §4). Everything below assumes AS routes reach the FastMCP app at root
   paths on `spendsense.dev`, same-origin as Flask.
1. Persistence: registered clients, pending-authorizations, auth codes,
   tokens/grants repositories (+ tests).
2. Implement `OAuthAuthorizationServerProvider` skeleton + wire
   `auth_server_provider` into `create_mcp_app()`; DCR + discovery/metadata live
   (verify `/.well-known/*` served; wire `MCP_BASE_URL`).
3. `provider.authorize()` → store pending auth, redirect to Flask `/mcp-consent`.
4. Flask `/mcp-consent`: reuse Google login + passkey unlock + consent; generate
   code; create `oauth_code` envelope (§3.2A); redirect back with `code`.
5. `exchange_authorization_code`: unwrap `oauth_code` → DEK → mint AT/RT → create
   `oauth_at`/`oauth_rt` → delete `oauth_code`. (This is where the DEK bridge lands.)
6. `load_access_token` (+ `get_tool_context`) accept OAuth ATs (unwrap `oauth_at`)
   **and** legacy API keys — keep both working (decision 3).
7. `exchange_refresh_token`: RT rotation + re-wrap + reuse-grace-window (§3.4).
8. `revoke_token`. Consent-screen UI polish.
9. Verify claude.ai renders the consent page top-level (empirical). Deploy to
   `spendsense.dev` (SSH `luca@173.249.11.4`) — **owner deploys / confirms server
   changes; do not touch the server without explicit confirmation**.

---

## 9. References

- Current MCP auth: `presentation/mcp_server/auth.py`, `server.py`, `context.py`
- Encryption service: `application/services/encryption_service.py`
  (`create_mcp_api_key`, `unwrap_dek_for_api_key`, `store_wrapped_dek`)
- Crypto primitives: `infrastructure/crypto/encryption.py`
  (`hkdf_derive_kek`, `wrap_key`, `unwrap_key`, `hash_token`, `generate_api_key`)
- Web DEK handling: `presentation/web/app.py` (`extract_encryption_key`),
  `presentation/web/static/js/passkey-manager.js`,
  `presentation/web/blueprints/webauthn.py`, `blueprints/api_keys.py`
- Prior fix context: PR #46 (MCP server), PR #47 (transport_security 421 fix)
- Claude Code MCP OAuth docs: https://code.claude.com/docs/en/mcp.md
- A visual of the web-vs-OAuth DEK flow was produced as a Claude artifact during
  design (see the `oauth_at`/`oauth_rt` model above for the authoritative version).

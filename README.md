# SpendSense

[![codecov](https://codecov.io/gh/lruggieri/spendsense/branch/main/graph/badge.svg)](https://codecov.io/gh/lruggieri/spendsense)

Automatic expense tracking with AI-powered categorization.

SpendSense is a self-hostable expense tracker that auto-categorizes transactions from bank notification emails. It uses a three-tier classification system — manual rules, regex patterns, and ML similarity — so categories improve over time with minimal effort. Try it at [spendsense.dev](https://spendsense.dev) or run it locally with Docker.

## Features

**Auto-categorization (three tiers)**
- **Manual assignments** — highest priority, explicit user mappings that always win
- **Regex patterns** — visual pattern builder, no regex knowledge needed
- **ML similarity** — sentence-transformers (`all-MiniLM-L6-v2`) matches against previously categorized transactions

**Gmail import**
- Configurable **Fetchers** extract transaction data (amount, merchant, currency) from notification emails
- Fetchers are versioned; LLM (Gemini) can auto-generate extraction patterns from email samples
- All Gmail access happens client-side in the browser (see [Privacy](#privacy-architecture))

**Categories**
- Hierarchical parent-child category tree
- Filtering by category includes all descendants

**Encryption at rest**
- AES-256-GCM field-level encryption with envelope encryption
- DEK wrapped with KEK derived from WebAuthn passkey (PRF extension)
- Passkey-based auth (no passwords)

**Analytics**
- Charts by category, trend lines, date range filtering
- Multi-currency with automatic ECB exchange-rate conversion

**Groups**
- Tag transactions into custom groups (e.g. "Vacation 2025")
- Per-group spending breakdown

**Progressive Web App**
- Installable with service worker, offline caching, mobile-first responsive design
- Guided onboarding wizard

## Privacy Architecture

SpendSense keeps your email data out of the server:

- **Client-side Gmail OAuth** — `gmail.readonly` scope via Google Identity Services
- **Token stays local** — stored in `localStorage`, never sent to the server
- **Browser-side extraction** — transaction parsing runs in JavaScript in the browser
- **Why?** Avoids Google's CASA (Cloud Application Security Assessment) audit requirement for server-side sensitive scopes
- **Encryption opt-in** — transaction fields encrypted at rest using a passkey-derived key

## Current Limitations

- **Gmail only** — other email providers not yet supported
- **Email-dependent** — some banks don't send notification emails; you can use [IFTTT](https://ifttt.com/) to forward mobile push notifications to email

## Tech Stack

- **Backend:** Python / Flask, SQLite, Gunicorn
- **ML:** sentence-transformers (`all-MiniLM-L6-v2`), PyTorch
- **Frontend:** Vanilla JavaScript, Chart.js, CSS (no framework)
- **Auth:** WebAuthn / passkeys, Google OAuth
- **Encryption:** AES-256-GCM, AES Key Wrap (RFC 3394), WebAuthn PRF
- **Infra:** Docker, service worker (PWA)

## Getting Started

**Prerequisites:** Docker (recommended) or Python 3.12+

### Docker

```bash
cp .env.example .env   # fill in credentials
docker compose up --build
# → http://localhost:5678
```

### Local

```bash
cp .env.example .env   # fill in credentials
make install
make run
# → http://localhost:5000
```

### Key Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GOOGLE_CLIENT_ID` | Yes | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Yes | Google OAuth client secret |
| `FLASK_SECRET_KEY` | Yes | Session encryption key |
| `GEMINI_API_KEY` | No | Enables LLM-powered fetcher generation |
| `ALLOWED_EMAILS` | No | Comma-separated allowlist (open access if unset) |

See [`.env.example`](.env.example) for the full list. For OAuth setup instructions, see [`config/README.md`](config/README.md).

## Development

```bash
make test    # all tests (Python + JS)
make mypy    # type checking
make check   # tests + mypy + lint
make run     # dev server
```

## License

[PolyForm Noncommercial 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0) — see [`LICENSE`](LICENSE).

## MCP Server (Remote LLM Access)

SpendSense exposes a [Model Context Protocol](https://modelcontextprotocol.io) server at `/mcp` for LLM clients such as Claude Code.

### Quick setup (Claude Code)

1. **Generate an API key** — log in to SpendSense and go to **Settings → MCP API Keys**. Choose scope:
   - `read` — list/query transactions, categories, patterns, groups
   - `readwrite` — above + add/update transactions, categories, patterns, groups

2. **Add to `.mcp.json`** in your project root:

```json
{
  "mcpServers": {
    "spendsense": {
      "type": "http",
      "url": "https://your-spendsense-host/mcp",
      "headers": {
        "Authorization": "Bearer ssk_<your-key>"
      }
    }
  }
}
```

3. **Verify** by asking your LLM: *"list my recent transactions from SpendSense"*.

### Encryption (DEK) lifecycle

If your account uses passkey-based encryption, you must generate MCP keys **while logged in** (the server wraps your DEK at key-creation time using the session key). If you later rotate or re-encrypt your account, all existing MCP keys become invalid — you must regenerate them from the UI.

### Available tools

| Tool | Scope | Description |
|---|---|---|
| `list_transactions` | read | Paginated transaction list with optional filters |
| `get_transaction` | read | Fetch one transaction by ID |
| `add_transaction` | readwrite | Add a new transaction |
| `update_transaction` | readwrite | Update date/amount/description/comment |
| `assign_transaction_category` | readwrite | Manually assign category (highest priority) |
| `list_categories` | read | All categories with hierarchy |
| `create_category` / `update_category` | readwrite | Manage categories |
| `list_regexp_patterns` | read | All classification regexp patterns |
| `create_regexp_pattern` / `update_regexp_pattern` | readwrite | Manage patterns |
| `list_groups` | read | All groups |
| `create_group` / `update_group` | readwrite | Manage groups |
| `get_user_settings` | read | Currency and language settings |

### Nginx (reverse-proxy) configuration

Add `proxy_buffering off` to the `/mcp` location block to avoid buffering the Streamable HTTP response stream:

```nginx
location /mcp {
    proxy_pass http://app:5678;
    proxy_buffering off;
}
```

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `MCP_RATE_LIMIT_PER_MIN` | `60` | Max tool calls per API key per minute (per worker) |
| `MCP_BASE_URL` | `http://localhost:5000` | Issuer/resource-server URL for MCP OAuth metadata |

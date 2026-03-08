# SpendSense

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

# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Project Overview

SpendSense: an expense tracker that automatically categorizes financial transactions using a three-tier classification system:

1. **Manual assignments** (highest priority) - Database-stored explicit mappings
2. **Regex patterns** - Pattern matching on descriptions
3. **Similarity-based** (fallback) - ML embeddings using sentence-transformers

**Stack:** SQLite database, Flask web interface, mobile-first responsive design with template inheritance and separated CSS/JS.

## Development Workflow

### Testing Requirements

**CRITICAL: Run `make test` after every code change.** All tests must pass before committing, creating PRs, or considering work complete.

**CRITICAL: Write tests for every new feature and bug fix.** Cover the core logic with unit tests before considering the work done. Use real temp SQLite databases for service/repository tests; use `authenticated_client` fixture with mocked service factories for blueprint tests. Target: maintain ≥70% coverage.

**CRITICAL: Run `make mypy` to check type correctness.** Type errors should be reviewed (full fixing is ongoing work).

```bash
make test                              # Run all tests
make mypy                              # Run type checker (errors are tracked, not blocking)
make test-verbose                      # Detailed output
make test-fast                         # Stop on first failure
make test-specific FILE=test_file.py   # Run specific test
make check                             # Run tests + mypy + lint (recommended before commit)
make quick-check                       # Fast tests + mypy + lint
```

## Architecture: Domain-Driven Design (DDD)

**DDD Layers**: `domain/` (entities, business logic) → `application/` (use cases) → `infrastructure/` (persistence, external services) → `presentation/` (web UI). Dependencies point inward only - domain has no dependencies, application depends on domain, infrastructure implements domain interfaces, presentation orchestrates application services.

## Key Design Patterns

**Service Layer**: Blueprints use focused services from `application/services/` via factory functions in `presentation/web/utils.py`. Services own repositories - blueprints should not access `SQLite*Repository` classes directly (exceptions: tests, auth middleware, SSE generators).

**Classification Priority**: Manual > Regex > Similarity. Manual corrections always win.

**Repository Abstraction**: Uses abstract base classes (`TransactionRepository`, `ManualAssignmentRepository`). Current implementation is SQLite.

**Batch Processing**: `classify_batch()` encodes all descriptions at once for performance.

**Category Hierarchy**: Categories have parent-child relationships. Filtering by category includes all descendants via `_get_descendant_category_ids()`.

**Embedding Cache**: `EmbeddingSimilarityCalculator` pre-computes embeddings at startup (`precompute_reference_embeddings()`).

**Category Source Tracking**: Transaction `category_source` field tracks how it was categorized. `/review` only allows editing SIMILARITY categorizations.

**Database Performance**: SQLite uses indexes on frequently-queried columns. Batch operations use `executemany()`.

**Mobile-First Frontend**: Base styles target mobile (< 640px), tablet (640px-1024px), desktop (> 1024px). All pages extend `base.html` for shared layout. CSS variables in `main.css`. Separated HTML/CSS/JS files.

## Frontend Development

**Mobile-First:** Design for mobile first, then progressively enhance for larger screens. Test on mobile, tablet, and desktop sizes.

**Templates:**
- Extend `base.html` for consistency (except special cases)
- Available blocks: `title`, `page_title`, `extra_head`, `header_actions`, `content`, `modals`, `extra_scripts`
- Reference static files: `{{ url_for('static', filename='...') }}`
- Use CSS classes from `main.css`, minimize inline styles

**CSS:**
- Use existing utility classes (`.btn`, `.card`, `.form-group`)
- BEM-like naming for new components: `.component-name__element--modifier`
- CSS variables: `var(--primary)`, `var(--spacing-md)`, etc.
- Media queries: Mobile (base), Tablet (`640px`), Desktop (`1024px`)

**JavaScript:**
- Separate JS files in `presentation/web/static/js/`
- ES6+ features, no jQuery
- Large touch targets for mobile

### Service Worker & Cache Management

**CRITICAL: When modifying any file in `/presentation/web/static/` that's listed in `PRECACHE_ASSETS` (service-worker.js), increment both cache versions:**

```javascript
const CACHE_NAME = 'spendsense-vXX';        // Increment XX
const RUNTIME_CACHE = 'spendsense-runtime-vXX';  // Increment XX
```

**Mobile debug:** Triple-tap the header logo to open debug panel with cache info.

## Logging & Privacy

**CRITICAL: Never log email content, user data, or PII.** Suppress third-party library loggers (e.g., `openai`, `httpx`) that dump request/response bodies. Log only operation results, errors, and metadata — never the data itself.

## Code Comments Guidelines

**Avoid migration references:** Never use terms like "migration period", "post-migration", or "during migration" in code comments. Future readers won't know what migration you're referring to. Instead, use "backward-compatibility" or "for backward-compatibility" when explaining fallback logic or default values.

## PR Creation

**Format:** `{type}/{shortname}: {description}` where type is `feat`, `chore`, or `fix`

**IMPORTANT:** This format applies to branch names, commit messages, AND PR titles.

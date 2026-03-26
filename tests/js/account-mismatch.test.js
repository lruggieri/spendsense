/**
 * Tests for Gmail account mismatch protection.
 *
 * Covers:
 *   - init() passes login_hint to GIS
 *   - _getStoredToken() rejects tokens verified for a different account
 *   - _handleTokenResponse verifies email via Gmail profile and rejects mismatches
 *   - clearToken() removes the stored email key
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { readFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const STATIC_JS = resolve(__dirname, '../../presentation/web/static/js');

// Track GIS initTokenClient options for assertion
let gisInitOpts = null;
let gisCallback = null;

globalThis.google = {
  accounts: {
    oauth2: {
      initTokenClient: (opts) => {
        gisInitOpts = opts;
        gisCallback = opts.callback;
        return {
          requestAccessToken: () => {
            // Simulate async GIS response
            setTimeout(() => gisCallback({
              access_token: 'new-token',
              expires_in: 3600,
            }), 0);
          },
        };
      },
    },
  },
};

// Load email-token.js IIFE
// eslint-disable-next-line no-eval
eval(readFileSync(resolve(STATIC_JS, 'email-token.js'), 'utf-8'));

const tokenManager = window.emailTokenManager;

// =========================================================================
// init() — login_hint behaviour
// =========================================================================

describe('init() login_hint', () => {
  beforeEach(() => {
    localStorage.clear();
    gisInitOpts = null;
    // Reset the token client by reloading the IIFE
    window.emailTokenManager = undefined;
    // eslint-disable-next-line no-eval
    eval(readFileSync(resolve(STATIC_JS, 'email-token.js'), 'utf-8'));
  });

  it('passes hint when userEmail is provided', () => {
    window.emailTokenManager.init('client-id', 'alice@example.com');
    expect(gisInitOpts.hint).toBe('alice@example.com');
  });

  it('omits hint when userEmail is not provided', () => {
    window.emailTokenManager.init('client-id');
    expect(gisInitOpts.hint).toBeUndefined();
  });
});

// =========================================================================
// Stored token email validation
// =========================================================================

describe('stored token email validation', () => {
  beforeEach(() => {
    localStorage.clear();
    window.emailTokenManager = undefined;
    // eslint-disable-next-line no-eval
    eval(readFileSync(resolve(STATIC_JS, 'email-token.js'), 'utf-8'));
  });

  it('rejects stored token verified for a different account', () => {
    // Token was stored for alice, but we're now logged in as bob
    localStorage.setItem('gmail_gis_token', 'some-token');
    localStorage.setItem('gmail_gis_token_expiry', String(Date.now() + 999_999));
    localStorage.setItem('gmail_gis_token_email', 'alice@example.com');

    window.emailTokenManager.init('client-id', 'bob@example.com');
    expect(window.emailTokenManager.hasToken()).toBe(false);
  });

  it('accepts stored token verified for the same account', () => {
    localStorage.setItem('gmail_gis_token', 'some-token');
    localStorage.setItem('gmail_gis_token_expiry', String(Date.now() + 999_999));
    localStorage.setItem('gmail_gis_token_email', 'alice@example.com');

    window.emailTokenManager.init('client-id', 'alice@example.com');
    expect(window.emailTokenManager.hasToken()).toBe(true);
  });

  it('rejects stored token with no email when expectedEmail is set', () => {
    // Legacy token stored before account verification was added
    localStorage.setItem('gmail_gis_token', 'legacy-token');
    localStorage.setItem('gmail_gis_token_expiry', String(Date.now() + 999_999));
    // No EMAIL_KEY stored

    window.emailTokenManager.init('client-id', 'alice@example.com');
    expect(window.emailTokenManager.hasToken()).toBe(false);
  });

  it('accepts stored token when no expectedEmail is set', () => {
    localStorage.setItem('gmail_gis_token', 'some-token');
    localStorage.setItem('gmail_gis_token_expiry', String(Date.now() + 999_999));
    // No email verification in this mode

    window.emailTokenManager.init('client-id');
    expect(window.emailTokenManager.hasToken()).toBe(true);
  });
});

// =========================================================================
// Account verification on token acquisition
// =========================================================================

describe('account verification on token acquisition', () => {
  let fetchMock;

  beforeEach(() => {
    localStorage.clear();
    window.emailTokenManager = undefined;
    // eslint-disable-next-line no-eval
    eval(readFileSync(resolve(STATIC_JS, 'email-token.js'), 'utf-8'));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('rejects token when Gmail profile email does not match', async () => {
    // Mock fetch: Gmail profile returns a different email
    fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ emailAddress: 'mallory@example.com' }),
    });
    vi.stubGlobal('fetch', fetchMock);

    window.emailTokenManager.init('client-id', 'alice@example.com');

    await expect(window.emailTokenManager.getOrRequestToken())
      .rejects.toThrow('Gmail account mismatch');

    // Token should NOT be stored
    expect(localStorage.getItem('gmail_gis_token')).toBeNull();
  });

  it('accepts token when Gmail profile email matches', async () => {
    fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ emailAddress: 'alice@example.com' }),
    });
    vi.stubGlobal('fetch', fetchMock);

    window.emailTokenManager.init('client-id', 'alice@example.com');

    const token = await window.emailTokenManager.getOrRequestToken();
    expect(token).toBe('new-token');
    expect(localStorage.getItem('gmail_gis_token')).toBe('new-token');
    expect(localStorage.getItem('gmail_gis_token_email')).toBe('alice@example.com');
  });

  it('accepts token when profile check fails (network error)', async () => {
    fetchMock = vi.fn().mockRejectedValue(new Error('Network error'));
    vi.stubGlobal('fetch', fetchMock);

    window.emailTokenManager.init('client-id', 'alice@example.com');

    const token = await window.emailTokenManager.getOrRequestToken();
    expect(token).toBe('new-token');
  });

  it('accepts token when profile returns non-OK status', async () => {
    fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
    });
    vi.stubGlobal('fetch', fetchMock);

    window.emailTokenManager.init('client-id', 'alice@example.com');

    const token = await window.emailTokenManager.getOrRequestToken();
    expect(token).toBe('new-token');
  });

  it('skips verification when no expectedEmail is set', async () => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    window.emailTokenManager.init('client-id');

    const token = await window.emailTokenManager.getOrRequestToken();
    expect(token).toBe('new-token');
    // Should NOT have called the Gmail profile endpoint
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

// =========================================================================
// clearToken removes email key
// =========================================================================

describe('clearToken', () => {
  beforeEach(() => {
    localStorage.clear();
    window.emailTokenManager = undefined;
    // eslint-disable-next-line no-eval
    eval(readFileSync(resolve(STATIC_JS, 'email-token.js'), 'utf-8'));
  });

  it('removes token, expiry, and email from localStorage', () => {
    localStorage.setItem('gmail_gis_token', 'tok');
    localStorage.setItem('gmail_gis_token_expiry', '999');
    localStorage.setItem('gmail_gis_token_email', 'alice@example.com');

    window.emailTokenManager.init('client-id');
    window.emailTokenManager.clearToken();

    expect(localStorage.getItem('gmail_gis_token')).toBeNull();
    expect(localStorage.getItem('gmail_gis_token_expiry')).toBeNull();
    expect(localStorage.getItem('gmail_gis_token_email')).toBeNull();
  });
});

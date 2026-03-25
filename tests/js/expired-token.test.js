/**
 * Tests for expired/revoked token handling.
 *
 * Covers:
 *   - emailTokenManager.forceRefreshToken() clears + re-requests
 *   - _gmailApiFetch() retries on 401 with a refreshed token
 *   - GmailApiClient.listMessages / getMessage surface the retry transparently
 *   - concurrent 401 retries share a single forceRefreshToken() call
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Load the IIFE scripts into jsdom (same approach as setup.js)
import { readFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const STATIC_JS = resolve(__dirname, '../../presentation/web/static/js');

// Stub GIS before loading email-token.js
let gisCallback = null;
let gisErrorCallback = null;
globalThis.google = {
  accounts: {
    oauth2: {
      initTokenClient: (opts) => {
        gisCallback = opts.callback;
        gisErrorCallback = opts.error_callback;
        return { requestAccessToken: () => {
          // Simulate async GIS response: resolve with a fresh token
          setTimeout(() => gisCallback({
            access_token: 'refreshed-token',
            expires_in: 3600,
          }), 0);
        }};
      },
    },
  },
};

// Load scripts
// eslint-disable-next-line no-eval
eval(readFileSync(resolve(STATIC_JS, 'email-token.js'), 'utf-8'));
// eslint-disable-next-line no-eval
eval(readFileSync(resolve(STATIC_JS, 'gmail-fetch.js'), 'utf-8'));

const { GmailApiClient } = window.gmailFetch;
const tokenManager = window.emailTokenManager;

// =========================================================================
// forceRefreshToken
// =========================================================================

describe('emailTokenManager.forceRefreshToken', () => {
  beforeEach(() => {
    localStorage.clear();
    tokenManager.init('test-client-id');
  });

  it('clears the stored token and requests a new one', async () => {
    // Seed a valid-looking token
    localStorage.setItem('gmail_gis_token', 'old-stale-token');
    localStorage.setItem('gmail_gis_token_expiry', String(Date.now() + 999_999));

    expect(tokenManager.hasToken()).toBe(true);

    const token = await tokenManager.forceRefreshToken();

    expect(token).toBe('refreshed-token');
    expect(localStorage.getItem('gmail_gis_token')).toBe('refreshed-token');
  });

  it('deduplicates concurrent calls', async () => {
    localStorage.setItem('gmail_gis_token', 'old');
    localStorage.setItem('gmail_gis_token_expiry', String(Date.now() + 999_999));

    const p1 = tokenManager.forceRefreshToken();
    const p2 = tokenManager.forceRefreshToken();

    const [t1, t2] = await Promise.all([p1, p2]);
    expect(t1).toBe('refreshed-token');
    expect(t2).toBe('refreshed-token');
  });
});

// =========================================================================
// _gmailApiFetch (tested via GmailApiClient)
// =========================================================================

describe('GmailApiClient 401 auto-retry', () => {
  let fetchMock;

  beforeEach(() => {
    localStorage.clear();
    tokenManager.init('test-client-id');
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('listMessages retries on 401 and succeeds with refreshed token', async () => {
    let callCount = 0;
    fetchMock = vi.fn().mockImplementation((url, opts) => {
      callCount++;
      if (callCount === 1) {
        // First call: 401
        return Promise.resolve({
          status: 401,
          ok: false,
          json: async () => ({ error: { message: 'Token expired' } }),
        });
      }
      // Second call (after refresh): success
      return Promise.resolve({
        status: 200,
        ok: true,
        json: async () => ({ messages: [{ id: 'msg1' }] }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    const ids = await GmailApiClient.listMessages('stale-token', 'from:test@example.com');

    expect(ids).toEqual(['msg1']);
    expect(fetchMock).toHaveBeenCalledTimes(2);

    // First call used the stale token
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe('Bearer stale-token');
    // Second call used the refreshed token
    expect(fetchMock.mock.calls[1][1].headers.Authorization).toBe('Bearer refreshed-token');
  });

  it('getMessage retries on 401 and succeeds with refreshed token', async () => {
    let callCount = 0;
    fetchMock = vi.fn().mockImplementation(() => {
      callCount++;
      if (callCount === 1) {
        return Promise.resolve({
          status: 401,
          ok: false,
          json: async () => ({ error: { message: 'Invalid credentials' } }),
        });
      }
      return Promise.resolve({
        status: 200,
        ok: true,
        json: async () => ({ id: 'abc123', payload: { mimeType: 'text/plain', body: {} } }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    const msg = await GmailApiClient.getMessage('stale-token', 'abc123');

    expect(msg.id).toBe('abc123');
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('throws if retry also returns 401', async () => {
    // Both calls return 401 — retry does not help
    fetchMock = vi.fn().mockResolvedValue({
      status: 401,
      ok: false,
      statusText: 'Unauthorized',
      json: async () => ({ error: { message: 'Consent revoked' } }),
    });
    vi.stubGlobal('fetch', fetchMock);

    await expect(GmailApiClient.listMessages('bad-token', 'from:test@example.com'))
      .rejects.toThrow('401');
  });

  it('reuses already-refreshed token instead of refreshing again', async () => {
    // Simulate: another call already refreshed the token into localStorage
    localStorage.setItem('gmail_gis_token', 'already-fresh-token');
    localStorage.setItem('gmail_gis_token_expiry', String(Date.now() + 999_999));

    let callCount = 0;
    fetchMock = vi.fn().mockImplementation(() => {
      callCount++;
      if (callCount === 1) {
        return Promise.resolve({
          status: 401,
          ok: false,
          json: async () => ({ error: { message: 'Token expired' } }),
        });
      }
      return Promise.resolve({
        status: 200,
        ok: true,
        json: async () => ({ messages: [{ id: 'msg1' }] }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    // Pass a stale token that differs from what's in localStorage
    const ids = await GmailApiClient.listMessages('stale-token', 'from:test@example.com');

    expect(ids).toEqual(['msg1']);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    // Retry used the already-stored fresh token, not a newly requested one
    expect(fetchMock.mock.calls[1][1].headers.Authorization).toBe('Bearer already-fresh-token');
  });

  it('does not retry on non-401 errors', async () => {
    fetchMock = vi.fn().mockResolvedValue({
      status: 403,
      ok: false,
      statusText: 'Forbidden',
      json: async () => ({ error: { message: 'Rate limited' } }),
    });
    vi.stubGlobal('fetch', fetchMock);

    await expect(GmailApiClient.listMessages('valid-token', 'from:test@example.com'))
      .rejects.toThrow('403');

    // Only one call — no retry for non-401 status codes
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

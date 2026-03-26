/**
 * email-token.js — GIS token lifecycle manager.
 *
 * Manages a Gmail readonly access token obtained via Google Identity Services
 * (GIS) Token Client.  The token is stored in localStorage so it persists
 * across page navigations and is silently refreshed when it approaches
 * expiry — no popup unless Google requires fresh consent.
 *
 * Account mismatch protection: when initialised with a userEmail, the manager
 * verifies (via the Gmail profile endpoint) that the authorised Google account
 * matches the logged-in SpendSense user.  Mismatched tokens are rejected.
 *
 * Exported API (attached to window.emailTokenManager):
 *   init(clientId, userEmail) — call once with the OAuth client_id and logged-in email
 *   getOrRequestToken()       — returns a Promise<string> with a valid token
 *   clearToken()              — removes token from localStorage (on logout/error)
 */

(function () {
  'use strict';

  const TOKEN_KEY  = 'gmail_gis_token';
  const EXPIRY_KEY = 'gmail_gis_token_expiry';
  const EMAIL_KEY  = 'gmail_gis_token_email';
  const SCOPE      = 'https://www.googleapis.com/auth/gmail.readonly';
  const GMAIL_PROFILE_URL = 'https://gmail.googleapis.com/gmail/v1/users/me/profile';

  // Refresh proactively if the token expires within 60 seconds
  const REFRESH_THRESHOLD_MS = 60_000;

  let _tokenClient = null;
  let _pendingResolve = null;
  let _pendingReject  = null;
  let _inflightPromise = null;  // deduplicates concurrent getOrRequestToken() calls
  let _expectedEmail   = null;  // logged-in user's email (lowercase)

  /**
   * Initialise the GIS token client.  Must be called before getOrRequestToken().
   *
   * The userEmail parameter enables account mismatch protection: after a token
   * is obtained, the manager verifies the Gmail account matches this email.
   *
   * @param {string} clientId  - OAuth 2.0 client ID
   * @param {string} [userEmail] - logged-in user's email address
   */
  function init(clientId, userEmail) {
    // Always update the expected email, even if the token client is already
    // initialised (handles page reuse across different user sessions).
    _expectedEmail = userEmail ? userEmail.toLowerCase() : null;

    if (_tokenClient) return;  // GIS client already initialised

    const opts = {
      client_id: clientId,
      scope: SCOPE,
      callback: _handleTokenResponse,
      error_callback: _handleTokenError,
    };
    if (_expectedEmail) {
      opts.hint = _expectedEmail;
    }
    _tokenClient = google.accounts.oauth2.initTokenClient(opts);
  }

  /**
   * Return a valid access token, refreshing silently if needed.
   * If no token exists or a silent refresh fails, shows the GIS popup.
   * @returns {Promise<string>} Resolves with the access token.
   */
  function getOrRequestToken() {
    const stored = _getStoredToken();
    if (stored) return Promise.resolve(stored);

    // If a token request is already in flight, piggy-back on it
    if (_inflightPromise) return _inflightPromise;

    _inflightPromise = new Promise((resolve, reject) => {
      _pendingResolve = resolve;
      _pendingReject  = reject;
      _requestToken(/* silent */ true);
    }).finally(() => {
      _inflightPromise = null;
    });

    return _inflightPromise;
  }

  /**
   * Force-refresh the token: clear the stored (possibly revoked/expired) token
   * and request a new one.  Concurrent callers share the same in-flight request.
   * @returns {Promise<string>} Resolves with the new access token.
   */
  function forceRefreshToken() {
    clearToken();
    return getOrRequestToken();
  }

  /**
   * Remove the stored token (e.g., on logout or after a permission error).
   */
  function clearToken() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(EXPIRY_KEY);
    localStorage.removeItem(EMAIL_KEY);
  }

  // -------------------------------------------------------------------------
  // Internal helpers
  // -------------------------------------------------------------------------

  function _getStoredToken() {
    const token  = localStorage.getItem(TOKEN_KEY);
    const expiry = parseInt(localStorage.getItem(EXPIRY_KEY) || '0', 10);
    if (!token) return null;
    if (Date.now() + REFRESH_THRESHOLD_MS >= expiry) return null;  // about to expire

    // Reject stored token if it was verified for a different account
    if (_expectedEmail) {
      const storedEmail = localStorage.getItem(EMAIL_KEY);
      if (!storedEmail || storedEmail.toLowerCase() !== _expectedEmail) return null;
    }

    return token;
  }

  function _requestToken(silent) {
    if (!_tokenClient) {
      if (_pendingReject) _pendingReject(new Error('emailTokenManager not initialised'));
      return;
    }
    // prompt='' -> silent refresh (no popup if user previously consented)
    // prompt='consent' -> force popup
    _tokenClient.requestAccessToken({ prompt: silent ? '' : 'consent' });
  }

  /**
   * Verify that the Gmail account behind the access token matches the
   * logged-in SpendSense user.
   *
   * Throws on mismatch.  Silently returns if verification succeeds or
   * cannot be performed (no expected email, network error).
   */
  async function _verifyAccountEmail(accessToken) {
    if (!_expectedEmail) return;

    let profile;
    try {
      const resp = await fetch(GMAIL_PROFILE_URL, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (!resp.ok) return;  // can't verify — proceed (login_hint + stored email provide backup)
      profile = await resp.json();
    } catch (_e) {
      return;  // network error — proceed
    }

    const tokenEmail = (profile.emailAddress || '').toLowerCase();
    if (tokenEmail && tokenEmail !== _expectedEmail) {
      throw new Error(
        'Gmail account mismatch: you are signed in to SpendSense as ' +
        _expectedEmail + ' but authorized Gmail access for ' + tokenEmail +
        '. Please try again and select the correct Google account.'
      );
    }
    localStorage.setItem(EMAIL_KEY, tokenEmail);
  }

  async function _handleTokenResponse(response) {
    if (response.error) {
      _handleTokenError(response);
      return;
    }

    try {
      await _verifyAccountEmail(response.access_token);
    } catch (err) {
      clearToken();
      if (_pendingReject) {
        const rej = _pendingReject;
        _pendingResolve = null;
        _pendingReject  = null;
        rej(err);
      }
      return;
    }

    // Store with expiry
    const expiresAt = Date.now() + (response.expires_in || 3600) * 1000;
    localStorage.setItem(TOKEN_KEY,  response.access_token);
    localStorage.setItem(EXPIRY_KEY, String(expiresAt));

    if (_pendingResolve) {
      const r = _pendingResolve;
      _pendingResolve = null;
      _pendingReject  = null;
      r(response.access_token);
    }
  }

  function _handleTokenError(error) {
    // If silent refresh failed (e.g. user not signed in), retry with popup
    if (error.type === 'popup_failed_to_open' || error.type === 'popup_closed' ||
        error.error === 'access_denied') {
      if (_pendingReject) {
        const rej = _pendingReject;
        _pendingResolve = null;
        _pendingReject  = null;
        rej(new Error(`Gmail authorisation failed: ${error.error || error.type}`));
      }
      return;
    }

    // For other errors on silent attempt, try again with popup
    if (_pendingResolve) {
      _requestToken(/* silent */ false);
    }
  }

  /**
   * Return true if a valid (non-expired) token is already in localStorage.
   * Use this to detect whether the user skipped the auth page.
   */
  function hasToken() {
    return _getStoredToken() !== null;
  }

  // Expose on window so other scripts can import it
  window.emailTokenManager = { init, getOrRequestToken, forceRefreshToken, clearToken, hasToken };
})();

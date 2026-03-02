/**
 * email-token.js — GIS token lifecycle manager.
 *
 * Manages a Gmail readonly access token obtained via Google Identity Services
 * (GIS) Token Client.  The token is stored in localStorage so it persists
 * across page navigations and is silently refreshed when it approaches
 * expiry — no popup unless Google requires fresh consent.
 *
 * Exported API (attached to window.emailTokenManager):
 *   init(clientId)         — call once with the OAuth client_id
 *   getOrRequestToken()    — returns a Promise<string> with a valid token
 *   clearToken()           — removes token from localStorage (on logout/error)
 */

(function () {
  'use strict';

  const TOKEN_KEY  = 'gmail_gis_token';
  const EXPIRY_KEY = 'gmail_gis_token_expiry';
  const SCOPE      = 'https://www.googleapis.com/auth/gmail.readonly';

  // Refresh proactively if the token expires within 60 seconds
  const REFRESH_THRESHOLD_MS = 60_000;

  let _tokenClient = null;
  let _pendingResolve = null;
  let _pendingReject  = null;

  /**
   * Initialise the GIS token client.  Must be called before getOrRequestToken().
   * @param {string} clientId - OAuth 2.0 client ID
   */
  function init(clientId) {
    if (_tokenClient) return;  // already initialised

    _tokenClient = google.accounts.oauth2.initTokenClient({
      client_id: clientId,
      scope: SCOPE,
      callback: _handleTokenResponse,
      error_callback: _handleTokenError,
    });
  }

  /**
   * Return a valid access token, refreshing silently if needed.
   * If no token exists or a silent refresh fails, shows the GIS popup.
   * @returns {Promise<string>} Resolves with the access token.
   */
  function getOrRequestToken() {
    return new Promise((resolve, reject) => {
      const stored = _getStoredToken();
      if (stored) {
        resolve(stored);
        return;
      }

      // No valid token — request one (silent first, popup only if needed)
      _pendingResolve = resolve;
      _pendingReject  = reject;
      _requestToken(/* silent */ true);
    });
  }

  /**
   * Remove the stored token (e.g., on logout or after a permission error).
   */
  function clearToken() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(EXPIRY_KEY);
  }

  // -------------------------------------------------------------------------
  // Internal helpers
  // -------------------------------------------------------------------------

  function _getStoredToken() {
    const token  = localStorage.getItem(TOKEN_KEY);
    const expiry = parseInt(localStorage.getItem(EXPIRY_KEY) || '0', 10);
    if (!token) return null;
    if (Date.now() + REFRESH_THRESHOLD_MS >= expiry) return null;  // about to expire
    return token;
  }

  function _requestToken(silent) {
    if (!_tokenClient) {
      if (_pendingReject) _pendingReject(new Error('emailTokenManager not initialised'));
      return;
    }
    // prompt='' → silent refresh (no popup if user previously consented)
    // prompt='consent' → force popup
    _tokenClient.requestAccessToken({ prompt: silent ? '' : 'consent' });
  }

  function _handleTokenResponse(response) {
    if (response.error) {
      _handleTokenError(response);
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
  window.emailTokenManager = { init, getOrRequestToken, clearToken, hasToken };
})();

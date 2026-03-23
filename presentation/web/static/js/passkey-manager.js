/**
 * Passkey Manager — WebAuthn + PRF for end-to-end encryption.
 *
 * Handles passkey registration with PRF key derivation,
 * passkey authentication with PRF to recover KEK,
 * fetch interception for injecting encryption key headers,
 * and cookie-based key transmission for server-rendered pages.
 */

(function () {
  'use strict';

  const STORAGE_KEY = 'encryption_dek';
  const COOKIE_NAME = 'encryption_key';

  // =========================================================================
  // Helpers
  // =========================================================================

  function bufferToBase64url(buffer) {
    const bytes = new Uint8Array(buffer);
    let str = '';
    for (const b of bytes) str += String.fromCharCode(b);
    return btoa(str).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }

  function base64urlToBuffer(base64url) {
    const base64 = base64url.replace(/-/g, '+').replace(/_/g, '/');
    const padded = base64 + '=='.slice(0, (4 - (base64.length % 4)) % 4);
    const binary = atob(padded);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return bytes.buffer;
  }

  function getDeviceName() {
    // Prefer User-Agent Client Hints (Chromium browsers)
    if (navigator.userAgentData) {
      const p = navigator.userAgentData.platform;
      if (p) return navigator.userAgentData.mobile ? p + ' (Mobile)' : p;
    }
    // Fallback: parse userAgent for Safari / Firefox
    const ua = navigator.userAgent;
    if (/iPhone/.test(ua)) return 'iPhone';
    if (/iPad/.test(ua)) return 'iPad';
    if (/Android/.test(ua)) return 'Android';
    if (/Mac/.test(ua)) return 'macOS';
    if (/Windows/.test(ua)) return 'Windows';
    if (/CrOS/.test(ua)) return 'Chrome OS';
    if (/Linux/.test(ua)) return 'Linux';
    return 'Unknown Device';
  }

  function showStatus(elementId, message, type) {
    const el = document.getElementById(elementId);
    if (!el) return;
    el.textContent = message;
    el.className = type; // 'success' or 'error'
  }

  /**
   * Fire-and-forget: encrypt any plaintext transactions and the session's google token.
   */
  function triggerAutoMigration() {
    fetch('/api/encryption/migrate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    }).then(r => r.json()).then(d => {
      if (d.success) console.log('[Encryption] Migrated', d.transactions_migrated, 'transactions');
    }).catch(e => console.error('[Encryption] Migration error:', e));
  }
  window.triggerAutoMigration = triggerAutoMigration;

  /**
   * Derive a KEK from PRF output using HKDF-SHA256.
   */
  async function deriveKEK(prfOutput) {
    const keyMaterial = await crypto.subtle.importKey(
      'raw', prfOutput, 'HKDF', false, ['deriveKey']
    );
    const kek = await crypto.subtle.deriveKey(
      {
        name: 'HKDF',
        hash: 'SHA-256',
        salt: new TextEncoder().encode('spendsense-kek'),
        info: new TextEncoder().encode('encryption-key'),
      },
      keyMaterial,
      { name: 'AES-KW', length: 256 },
      true, // extractable so we can export for server
      ['wrapKey', 'unwrapKey']
    );
    const exported = await crypto.subtle.exportKey('raw', kek);
    return btoa(String.fromCharCode(...new Uint8Array(exported)));
  }

  // =========================================================================
  // Registration
  // =========================================================================

  window.registerPasskeyWithPRF = async function () {
    const statusId = 'setup-status';
    const btn = document.getElementById('register-passkey-btn');
    if (btn) btn.disabled = true;

    try {
      // 1. Get registration options from server
      const optionsRes = await fetch('/api/webauthn/register/options');
      const options = await optionsRes.json();
      if (!optionsRes.ok) throw new Error(options.error || 'Failed to get registration options');

      // Generate PRF salt
      const prfSalt = crypto.getRandomValues(new Uint8Array(32));
      const prfSaltB64 = bufferToBase64url(prfSalt);

      // 2. Create credential with PRF extension
      const publicKey = {
        challenge: base64urlToBuffer(options.challenge),
        rp: options.rp,
        user: {
          ...options.user,
          id: base64urlToBuffer(options.user.id),
        },
        pubKeyCredParams: options.pubKeyCredParams,
        authenticatorSelection: options.authenticatorSelection,
        timeout: options.timeout,
        excludeCredentials: (options.excludeCredentials || []).map(c => ({
          ...c,
          id: base64urlToBuffer(c.id),
        })),
        extensions: {
          prf: {
            eval: {
              first: prfSalt.buffer,
            },
          },
        },
      };

      const credential = await navigator.credentials.create({ publicKey });

      // 3. Check PRF support
      const extResults = credential.getClientExtensionResults();
      let kekB64 = null;

      if (extResults.prf && extResults.prf.results && extResults.prf.results.first) {
        kekB64 = await deriveKEK(extResults.prf.results.first);
      } else {
        showStatus(statusId, 'Your authenticator does not support PRF. Passkey registered without encryption.', 'error');
      }

      // 4. Send credential to server
      // If the user already has a DEK (adding another passkey), include it
      // so the server wraps the existing DEK instead of generating a new one.
      const existingDek = localStorage.getItem(STORAGE_KEY);

      const attestationResponse = credential.response;
      const verifyRes = await fetch('/api/webauthn/register/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          credential: {
            id: credential.id,
            rawId: bufferToBase64url(credential.rawId),
            response: {
              attestationObject: bufferToBase64url(attestationResponse.attestationObject),
              clientDataJSON: bufferToBase64url(attestationResponse.clientDataJSON),
            },
            type: credential.type,
          },
          kek: kekB64,
          prfSalt: prfSaltB64,
          deviceName: getDeviceName(),
          existingDek: existingDek,
        }),
      });

      const result = await verifyRes.json();
      if (!result.success) throw new Error(result.error || 'Registration failed');

      // 5. Store DEK if encryption was set up
      if (result.dek) {
        localStorage.setItem(STORAGE_KEY, result.dek);
        syncCookie();
        showStatus(statusId, 'Passkey registered and encryption enabled!', 'success');

        triggerAutoMigration();
      } else {
        showStatus(statusId, 'Passkey registered.', 'success');
      }
    } catch (err) {
      console.error('Passkey registration error:', err);
      showStatus(statusId, 'Registration failed: ' + err.message, 'error');
    } finally {
      if (btn) btn.disabled = false;
    }
  };

  // =========================================================================
  // Authentication
  // =========================================================================

  window.authenticateWithPRF = async function () {
    const statusId = 'unlock-status';
    const btn = document.getElementById('unlock-btn');
    if (btn) btn.disabled = true;

    try {
      // 1. Get authentication options
      const optionsRes = await fetch('/api/webauthn/authenticate/options');
      const options = await optionsRes.json();
      if (!optionsRes.ok) throw new Error(options.error || 'Failed to get authentication options');
      const prfSalts = options.prfSalts || {};

      // 2. Build per-credential PRF salt map so the authenticator uses
      //    the correct salt regardless of which passkey is selected.
      const evalByCredential = {};
      for (const [credId, salt] of Object.entries(prfSalts)) {
        evalByCredential[credId] = { first: base64urlToBuffer(salt) };
      }

      if (Object.keys(evalByCredential).length === 0) {
        throw new Error('No PRF salt available');
      }

      const publicKey = {
        challenge: base64urlToBuffer(options.challenge),
        rpId: options.rpId,
        allowCredentials: (options.allowCredentials || []).map(c => ({
          ...c,
          id: base64urlToBuffer(c.id),
        })),
        userVerification: options.userVerification,
        timeout: options.timeout,
        extensions: {
          prf: {
            evalByCredential: evalByCredential,
          },
        },
      };

      const assertion = await navigator.credentials.get({ publicKey });

      // 3. Check PRF output
      const extResults = assertion.getClientExtensionResults();
      if (!extResults.prf || !extResults.prf.results || !extResults.prf.results.first) {
        throw new Error('PRF extension not supported by this authenticator');
      }

      const kekB64 = await deriveKEK(extResults.prf.results.first);
      const credentialIdB64 = bufferToBase64url(assertion.rawId);

      // 4. Verify authentication with server
      const assertionResponse = assertion.response;
      const verifyRes = await fetch('/api/webauthn/authenticate/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          credentialId: credentialIdB64,
          credential: {
            id: assertion.id,
            rawId: credentialIdB64,
            response: {
              authenticatorData: bufferToBase64url(assertionResponse.authenticatorData),
              clientDataJSON: bufferToBase64url(assertionResponse.clientDataJSON),
              signature: bufferToBase64url(assertionResponse.signature),
              userHandle: assertionResponse.userHandle
                ? bufferToBase64url(assertionResponse.userHandle)
                : null,
            },
            type: assertion.type,
          },
        }),
      });

      const verifyResult = await verifyRes.json();
      if (!verifyResult.success) throw new Error(verifyResult.error || 'Auth verification failed');

      // 5. Unwrap DEK using KEK
      const unwrapRes = await fetch('/api/encryption/unwrap-dek', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          kek: kekB64,
          credentialId: credentialIdB64,
        }),
      });

      const unwrapResult = await unwrapRes.json();
      if (!unwrapResult.success) throw new Error(unwrapResult.error || 'Failed to unwrap key');

      // 6. Store DEK in localStorage and sync cookie
      localStorage.setItem(STORAGE_KEY, unwrapResult.dek);
      syncCookie();

      triggerAutoMigration();

      showStatus(statusId, 'Data unlocked! Redirecting...', 'success');
      setTimeout(() => { window.location.href = '/'; }, 1000);
    } catch (err) {
      console.error('Passkey authentication error:', err);
      showStatus(statusId, 'Authentication failed: ' + err.message, 'error');
    } finally {
      if (btn) btn.disabled = false;
    }
  };

  // =========================================================================
  // Key Management — Cookie and Fetch Interceptor
  // =========================================================================

  /**
   * Sync the DEK from localStorage into a short-lived cookie
   * so server-rendered page navigations can access it.
   */
  function syncCookie() {
    const dek = localStorage.getItem(STORAGE_KEY);
    if (dek) {
      // SameSite=Lax (not Strict) because OAuth redirects from accounts.google.com
      // to /auth/callback are cross-site navigations. With Strict, the browser
      // withholds this cookie, so the server can't encrypt the Google token at
      // session creation. Lax sends the cookie on top-level navigations (redirects,
      // link clicks) but still blocks cross-site subrequests (iframes, fetch).
      const secure = location.protocol === 'https:' ? '; Secure' : '';
      // max-age=604800 (7 days) matches the session_token cookie lifetime
      // so the encryption cookie survives PWA cold starts on Android/iOS.
      // The DEK is already persisted in localStorage; this just prevents a
      // stale-session-cookie race where the server renders the unlock banner
      // even though the key is available client-side.
      // Cleared on logout by both server (set_cookie expires=0) and client
      // (login.html removes encryption_dek from localStorage before syncCookie).
      document.cookie = COOKIE_NAME + '=' + encodeURIComponent(dek)
        + '; path=/; SameSite=Lax; max-age=604800' + secure;
    } else {
      // Clear the cookie
      document.cookie = COOKIE_NAME + '=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT';
    }
  }

  /**
   * Override global fetch to inject X-Encryption-Key header on same-origin requests.
   */
  const originalFetch = window.fetch;
  window.fetch = function (input, init) {
    const dek = localStorage.getItem(STORAGE_KEY);
    if (dek) {
      // Only inject header for same-origin requests
      let url;
      try {
        url = new URL(input instanceof Request ? input.url : input, location.origin);
      } catch (e) {
        return originalFetch.call(this, input, init);
      }

      if (url.origin === location.origin) {
        init = init || {};
        const headers = new Headers(init.headers || {});
        headers.set('X-Encryption-Key', dek);
        init.headers = headers;
      }
    }
    return originalFetch.call(this, input, init);
  };

  // Sync cookie on page load
  syncCookie();
})();

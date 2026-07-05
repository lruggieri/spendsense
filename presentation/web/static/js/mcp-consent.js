/**
 * MCP OAuth consent page glue.
 *
 * Two small pieces of page-specific behavior that don't belong in the
 * shared passkey-manager.js:
 *
 * 1. Tell the shared `authenticateWithPRF()` unlock flow to redirect back to
 *    this consent page (with its txn) after a successful unlock, instead of
 *    its default '/' - so the same GET handler re-runs and, with the DEK now
 *    available via the cookie the unlock flow just set, renders the actual
 *    consent screen instead of the unlock prompt again.
 * 2. Disable the Approve/Deny buttons on submit so a slow network or an
 *    impatient double-tap can't fire two authorization attempts.
 */
(function () {
  'use strict';

  document.addEventListener('DOMContentLoaded', function () {
    var page = document.getElementById('mcp-consent-page');
    if (page && page.dataset.redirectTarget) {
      window.PRF_REDIRECT_TARGET = page.dataset.redirectTarget;
    }

    document.querySelectorAll('.mcp-consent__actions form').forEach(function (form) {
      form.addEventListener('submit', function () {
        var btn = form.querySelector('button[type="submit"]');
        if (btn) btn.disabled = true;
      });
    });
  });
})();

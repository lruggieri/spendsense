// Shared Playwright fixtures for the SpendSense end-to-end suite.
//
// Every test logs in as a brand-new user (via the test-only /__e2e__ API of
// tests/e2e/server.py), so tests never share data and can run in parallel.
// Third-party network traffic is stubbed out:
//   - Chart.js CDN       -> served from node_modules
//   - Google Identity    -> fake token client that grants immediately
//   - Gmail REST API     -> in-memory FakeGmail mailbox (see `gmail` fixture)
//   - anything else off-host is aborted, so tests never depend on the internet.

const path = require('path');
const fs = require('fs');
const base = require('@playwright/test');

const { expect } = base;

const CHART_JS = fs.readFileSync(
  path.join(__dirname, '..', '..', 'node_modules', 'chart.js', 'dist', 'chart.umd.js'),
  'utf8'
);

// Minimal stand-in for https://accounts.google.com/gsi/client: the token
// client answers every request with a fake access token.
const FAKE_GIS = `
window.google = window.google || {};
window.google.accounts = {
  oauth2: {
    initTokenClient(opts) {
      return {
        requestAccessToken() {
          setTimeout(() => opts.callback({ access_token: 'fake-gmail-token', expires_in: 3600 }), 0);
        },
      };
    },
  },
};
`;

function b64url(text) {
  return Buffer.from(text, 'utf8').toString('base64').replace(/\+/g, '-').replace(/\//g, '_');
}

/** In-memory Gmail mailbox served at https://gmail.googleapis.com. */
class FakeGmail {
  constructor() {
    this.emailAddress = null;
    this.messages = [];
    this.requests = [];
  }

  /** Add a plain-text message; returns its Gmail message id. */
  addMessage({ id, body, date = new Date() }) {
    const msgId = id || (Date.now().toString(16) + Math.floor(Math.random() * 1e6).toString(16));
    this.messages.push({
      id: msgId,
      threadId: msgId,
      internalDate: String(date.getTime()),
      payload: { mimeType: 'text/plain', body: { data: b64url(body) } },
    });
    return msgId;
  }

  async install(context) {
    await context.route('https://gmail.googleapis.com/**', async (route) => {
      const url = new URL(route.request().url());
      this.requests.push(url.pathname + url.search);
      const json = (body, status = 200) =>
        route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

      if (url.pathname.endsWith('/profile')) {
        return json({ emailAddress: this.emailAddress });
      }
      if (url.pathname.endsWith('/messages')) {
        return json({
          messages: this.messages.map((m) => ({ id: m.id, threadId: m.threadId })),
          resultSizeEstimate: this.messages.length,
        });
      }
      const match = url.pathname.match(/\/messages\/([^/]+)$/);
      if (match) {
        const msg = this.messages.find((m) => m.id === decodeURIComponent(match[1]));
        return msg ? json(msg) : json({ error: { message: 'Not Found' } }, 404);
      }
      return json({ error: { message: 'Unhandled fake Gmail route' } }, 404);
    });
  }
}

async function stubExternalNetwork(context, baseURL) {
  const origin = new URL(baseURL).origin;
  await context.route(
    (url) => url.origin !== origin && url.hostname !== 'gmail.googleapis.com',
    async (route) => {
      const url = route.request().url();
      if (url.includes('cdn.jsdelivr.net/npm/chart.js')) {
        return route.fulfill({ contentType: 'application/javascript', body: CHART_JS });
      }
      if (url.startsWith('https://accounts.google.com/gsi/client')) {
        return route.fulfill({ contentType: 'application/javascript', body: FAKE_GIS });
      }
      return route.abort();
    }
  );
}

let userCounter = 0;

const test = base.test.extend({
  context: async ({ context, baseURL }, use) => {
    await stubExternalNetwork(context, baseURL);
    await use(context);
  },

  gmail: async ({ context }, use) => {
    const gmail = new FakeGmail();
    await gmail.install(context);
    await use(gmail);
  },

  /**
   * login({ seed, onboarded, onboardingStep, showEncryptionBanner, userName })
   * creates a fresh user, sets the session cookie and returns { userId, ids }.
   * `ids` maps the seeded entity names (see _seed_basic in server.py) to their
   * database IDs.
   */
  login: async ({ context, baseURL }, use, testInfo) => {
    await use(async (opts = {}) => {
      userCounter += 1;
      const userId =
        `e2e-w${testInfo.workerIndex}-${userCounter}-${Date.now().toString(36)}@example.com`;
      const resp = await context.request.post(`${baseURL}/__e2e__/session`, {
        data: {
          user_id: userId,
          seed: opts.seed || 'none',
          onboarded: opts.onboarded !== false,
          onboarding_step: opts.onboardingStep,
          show_encryption_banner: !!opts.showEncryptionBanner,
          user_name: opts.userName || 'E2E User',
        },
      });
      expect(resp.ok(), await resp.text()).toBeTruthy();
      const data = await resp.json();
      await context.addCookies([
        { name: 'session_token', value: data.session_token, url: baseURL },
      ]);
      return { userId, ids: data.ids };
    });
  },

  /** Logged-in user with the "basic" seed data set; yields { userId, ids }. */
  seeded: async ({ login }, use) => {
    await use(await login({ seed: 'basic' }));
  },
});

/** Assert that a toast containing `text` is shown. */
async function expectToast(page, text) {
  await expect(page.locator('#toast-container .toast-message', { hasText: text }).first()).toBeVisible();
}

/** Accept the in-page showConfirm() dialog. */
async function confirmDialog(page, { accept = true } = {}) {
  const modal = page.locator('#confirm-modal');
  await expect(modal).toBeVisible();
  await modal.locator(accept ? '#confirm-ok' : '#confirm-cancel').click();
  await expect(modal).toBeHidden();
}

/** Open the floating action button menu and click the action with `label`. */
async function clickFabAction(page, label) {
  await page.locator('#fab-main').click();
  await page.getByRole('button', { name: label, exact: true }).click();
}

/**
 * Attach a Chromium virtual authenticator (with the PRF extension the app
 * relies on for encryption keys) so passkey ceremonies succeed headlessly.
 */
async function addVirtualAuthenticator(context, page) {
  const cdp = await context.newCDPSession(page);
  await cdp.send('WebAuthn.enable');
  await cdp.send('WebAuthn.addVirtualAuthenticator', {
    options: {
      protocol: 'ctap2',
      transport: 'internal',
      hasResidentKey: true,
      hasUserVerification: true,
      isUserVerified: true,
      hasPrf: true,
      automaticPresenceSimulation: true,
    },
  });
  return cdp;
}

/**
 * Click something that makes the page reload itself (many forms call
 * location.reload() shortly after saving) and wait for the new document.
 */
async function clickAndWaitForReload(page, locator) {
  const reloaded = page.waitForEvent('load');
  await locator.click();
  await reloaded;
}

/** The transaction card on /review or /groups for a seeded transaction id. */
function txCard(page, txId) {
  return page.locator(`.transaction-card[data-tx-id="${txId}"]`);
}

module.exports = {
  test,
  expect,
  expectToast,
  confirmDialog,
  clickFabAction,
  clickAndWaitForReload,
  txCard,
  addVirtualAuthenticator,
  FakeGmail,
};

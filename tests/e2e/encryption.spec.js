// End-to-end encryption with passkeys (WebAuthn PRF), and the MCP OAuth
// consent screen, which has to unlock the encryption key before approving.

const { test, expect, txCard, addVirtualAuthenticator } = require('./fixtures');

/** Register a passkey on /passkey/setup and wait for data migration. */
async function enableEncryption(page) {
  await page.goto('/passkey/setup');
  const migrated = page.waitForResponse('**/api/encryption/migrate');
  await page.locator('#register-passkey-btn').click();
  await expect(page.locator('#setup-status')).toContainText('Passkey registered and encryption enabled!');
  expect((await (await migrated).json()).success).toBe(true);
}

/** Forget the data-encryption key in this browser, as on a new device/session. */
async function lockBrowser(page, context) {
  await page.evaluate(() => localStorage.removeItem('encryption_dek'));
  const cookies = (await context.cookies()).filter((c) => c.name !== 'encryption_key');
  await context.clearCookies();
  await context.addCookies(cookies);
}

async function startMcpAuthorization(page, scopes = ['read']) {
  const resp = await page.request.post('/__e2e__/mcp-pending', {
    data: { client_name: 'Claude Code', scopes },
  });
  return resp.json();
}

test.describe('Passkey encryption', () => {
  test('setting up a passkey encrypts data that stays readable while unlocked', async ({ page, context, seeded }) => {
    await addVirtualAuthenticator(context, page);
    const tx = seeded.ids.transactions;

    await page.goto('/passkey/setup');
    await expect(page.getByRole('link', { name: 'Skip for Now' })).toBeVisible();
    await enableEncryption(page);

    await page.reload();
    await expect(page.getByRole('heading', { name: 'Registered Passkeys' })).toBeVisible();
    await expect(page.locator('.credential-item')).toHaveCount(1);
    await expect(page.locator('#register-passkey-btn')).toHaveText(/Add Another Passkey/);

    await page.goto('/review');
    await expect(page.locator('#unlock-banner')).toHaveCount(0);
    await expect(txCard(page, tx.supermarket)).toContainText('CITY SUPERMARKET');
    await expect(txCard(page, tx.supermarket).locator('.encryption-badge')).toBeVisible();
    await expect(page.locator('.encryption-badge')).toHaveCount(7);
  });

  test('a locked browser hides encrypted data until the passkey unlocks it', async ({ page, context, seeded }) => {
    await addVirtualAuthenticator(context, page);
    const tx = seeded.ids.transactions;
    await enableEncryption(page);

    await lockBrowser(page, context);
    await page.goto('/review');
    const banner = page.locator('#unlock-banner');
    await expect(banner).toContainText('Your data is encrypted.');
    await expect(txCard(page, tx.supermarket)).toContainText('[Encrypted]');
    await expect(txCard(page, tx.supermarket)).not.toContainText('CITY SUPERMARKET');
    // Encrypted rows cannot be edited.
    await expect(txCard(page, tx.supermarket).locator('.edit-transaction-btn')).toHaveCount(0);

    await banner.getByRole('link', { name: 'Unlock with your passkey' }).click();
    await expect(page).toHaveURL(/\/passkey\/login$/);
    await page.getByRole('button', { name: 'Authenticate with Passkey' }).click();
    await expect(page.locator('#unlock-status')).toContainText('Data unlocked!');

    await expect(page).toHaveURL(/\/review$/, { timeout: 10_000 });
    await expect(page.locator('#unlock-banner')).toHaveCount(0);
    await expect(txCard(page, tx.supermarket)).toContainText('CITY SUPERMARKET');
  });

  test('new transactions are encrypted too', async ({ page, context, seeded }) => {
    await addVirtualAuthenticator(context, page);
    await enableEncryption(page);

    await page.goto('/review');
    await page.locator('#fab-main').click();
    await page.getByRole('button', { name: 'Add Transaction', exact: true }).click();
    await page.locator('#add-tx-amount').fill('3');
    await page.locator('#add-tx-currency').selectOption('USD');
    await page.locator('#add-tx-description').fill('Secret espresso');
    await page.locator('#add-transaction-modal').getByRole('button', { name: 'Add Transaction' }).click();
    const card = page.locator('.transaction-card', { hasText: 'Secret espresso' });
    await expect(card.locator('.encryption-badge')).toBeVisible();

    await lockBrowser(page, context);
    await page.reload();
    await expect(page.locator('.transaction-card', { hasText: 'Secret espresso' })).toHaveCount(0);
  });

  test('logging out forgets the encryption key cookie', async ({ page, context, seeded }) => {
    await addVirtualAuthenticator(context, page);
    await enableEncryption(page);
    expect((await context.cookies()).some((c) => c.name === 'encryption_key')).toBe(true);

    await page.goto('/logout');
    expect((await context.cookies()).some((c) => c.name === 'encryption_key' && c.value)).toBe(false);
  });
});

test.describe('MCP OAuth consent', () => {
  test('approving redirects back to the client with an authorization code', async ({ page, seeded }) => {
    const { consent_url } = await startMcpAuthorization(page, ['read', 'readwrite']);
    await page.goto(consent_url);

    await expect(page.getByRole('heading', { name: 'Claude Code would like to access your SpendSense data' })).toBeVisible();
    const scopes = page.locator('.mcp-consent__scopes li');
    await expect(scopes).toHaveCount(2);
    await expect(scopes.nth(0)).toContainText('View your transactions');
    await expect(scopes.nth(1)).toContainText('Add and edit your transactions');

    await page.getByRole('button', { name: 'Approve' }).click();
    await expect(page).toHaveURL(/\/__e2e__\/oauth-callback\?/);
    const params = new URL(page.url()).searchParams;
    expect(params.get('code')).toBeTruthy();
    expect(params.get('state')).toBe('e2e-state');

    // The pending request is single-use.
    const replay = await page.goto(consent_url);
    expect(replay.status()).toBe(404);
  });

  test('denying redirects back with access_denied', async ({ page, seeded }) => {
    const { consent_url } = await startMcpAuthorization(page);
    await page.goto(consent_url);
    await page.getByRole('button', { name: 'Deny' }).click();
    const params = new URL(page.url()).searchParams;
    expect(params.get('error')).toBe('access_denied');
    expect(params.get('code')).toBeNull();
  });

  test('an unknown authorization request is a 404', async ({ page, seeded }) => {
    const resp = await page.goto('/mcp-consent?txn=not-a-real-transaction');
    expect(resp.status()).toBe(404);
  });

  test('signing in first returns to the consent screen', async ({ page, context, login, baseURL }) => {
    const { consent_url } = await startMcpAuthorization(page);
    await page.goto(consent_url);
    await expect(page).toHaveURL(/\/login\?next=/);
    expect(new URL(page.url()).searchParams.get('next')).toBe(consent_url);

    // Once a session exists, the login page forwards to the consent screen.
    await login({ seed: 'basic' });
    await page.goto(`/login?next=${encodeURIComponent(consent_url)}`);
    await expect(page).toHaveURL(`${baseURL}${consent_url}`);
    await expect(page.getByRole('button', { name: 'Approve' })).toBeVisible();
  });

  test('a new user finishes onboarding and lands back on the consent screen', async ({ page, login }) => {
    await login({ seed: 'basic', onboardingStep: 4 });
    const { consent_url } = await startMcpAuthorization(page);
    await page.goto(consent_url);
    await expect(page).toHaveURL(/\/onboarding\/step\/4$/);

    await page.locator('#continue-btn').click();
    await expect(page).toHaveURL(/\/onboarding\/complete$/);
    await page.getByRole('link', { name: 'Continue' }).click();
    await expect(page).toHaveURL(new RegExp(consent_url.replace('?', '\\?')));
    await expect(page.getByRole('button', { name: 'Approve' })).toBeVisible();
  });

  test('an encrypted account must unlock with its passkey before approving', async ({ page, context, seeded }) => {
    await addVirtualAuthenticator(context, page);
    await enableEncryption(page);
    await lockBrowser(page, context);

    const { consent_url } = await startMcpAuthorization(page);
    await page.goto(consent_url);
    await expect(page.getByRole('heading', { name: 'Unlock Encryption Key' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Approve' })).toHaveCount(0);

    await page.getByRole('button', { name: 'Authenticate with Passkey' }).click();
    await expect(page.locator('#unlock-status')).toContainText('Data unlocked!');
    // The consent screen re-renders itself with the unlocked key.
    await expect(page.getByRole('button', { name: 'Approve' })).toBeVisible({ timeout: 10_000 });
    await page.getByRole('button', { name: 'Approve' }).click();
    expect(new URL(page.url()).searchParams.get('code')).toBeTruthy();
  });
});

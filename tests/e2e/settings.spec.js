// User settings (/settings) and MCP API keys (/settings/api-keys).

const { test, expect, expectToast, txCard } = require('./fixtures');

test.describe('User settings', () => {
  test('shows the current preferences', async ({ page, seeded }) => {
    await page.goto('/settings');
    await expect(page.locator('#language')).toHaveValue('en');
    await expect(page.locator('#currency')).toHaveValue('USD');
    await expect(page.locator('.settings-summary')).toContainText('Currency: USD');
    await expect(page.locator('.settings-summary')).toContainText('Language: English (en)');
  });

  test('changing the default currency converts totals @mobile', async ({ page, seeded }) => {
    await page.goto('/settings');
    await page.locator('#currency').selectOption('EUR');
    await page.locator('#language').selectOption('it');
    await page.getByRole('button', { name: 'Save Settings' }).click();
    await expectToast(page, 'Settings saved successfully');

    await page.reload();
    await expect(page.locator('#currency')).toHaveValue('EUR');
    await expect(page.locator('#language')).toHaveValue('it');
    await expect(page.locator('.settings-summary')).toContainText('Currency: EUR');
    await expect(page.locator('.settings-summary')).toContainText('Last Updated:');

    // USD transactions are now shown with their EUR equivalent.
    await page.goto('/review');
    await expect(page.locator('#total-amount')).toHaveText(/^€/);
    await expect(txCard(page, seeded.ids.transactions.supermarket).locator('.info-value[data-amount]')).toContainText(
      '(≈€'
    );
    await page.goto('/charts');
    await expect(page.locator('#total-expenses')).toHaveText(/^€/);
  });
});

test.describe('MCP API keys', () => {
  test('creates, lists and revokes keys', async ({ page, seeded }) => {
    await page.goto('/settings/api-keys');
    await expect(page.locator('#keys-list')).toHaveText('No keys yet.');

    await page.locator('#key-label').fill('laptop-claude');
    await page.locator('#key-scope').selectOption('readwrite');
    await page.getByRole('button', { name: 'Generate key' }).click();

    await expect(page.locator('#new-key-box')).toBeVisible();
    const key = await page.locator('#new-key-value').textContent();
    expect(key.length).toBeGreaterThan(20);
    const card = page.locator('#keys-list .card', { hasText: 'laptop-claude' });
    await expect(card).toContainText('Scope: readwrite');

    // The raw key is only shown once.
    await page.reload();
    await expect(page.locator('#new-key-box')).toBeHidden();
    await expect(page.locator('#keys-list .card', { hasText: 'laptop-claude' })).toBeVisible();

    page.once('dialog', (dialog) => dialog.accept());
    await page.locator('#keys-list .card', { hasText: 'laptop-claude' }).getByRole('button', { name: 'Revoke' }).click();
    await expect(page.locator('#keys-list .card', { hasText: 'laptop-claude' })).toContainText('(revoked)');
    await expect(
      page.locator('#keys-list .card', { hasText: 'laptop-claude' }).getByRole('button', { name: 'Revoke' })
    ).toHaveCount(0);
  });

  test('dismissing the revoke prompt keeps the key active', async ({ page, seeded }) => {
    await page.goto('/settings/api-keys');
    await page.locator('#key-label').fill('keep-me');
    await page.getByRole('button', { name: 'Generate key' }).click();
    const card = page.locator('#keys-list .card', { hasText: 'keep-me' });
    await expect(card).toBeVisible();

    page.once('dialog', (dialog) => dialog.dismiss());
    await card.getByRole('button', { name: 'Revoke' }).click();
    await expect(card).not.toContainText('(revoked)');
  });

  test('a label is required', async ({ page, seeded }) => {
    await page.goto('/settings/api-keys');
    let message = null;
    page.once('dialog', (dialog) => {
      message = dialog.message();
      dialog.accept();
    });
    await page.getByRole('button', { name: 'Generate key' }).click();
    await expect.poll(() => message).toBe('Label is required.');
    await expect(page.locator('#new-key-box')).toBeHidden();
  });
});

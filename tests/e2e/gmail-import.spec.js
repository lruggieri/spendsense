// Gmail import (/fetch-gmail -> /fetch-gmail/progress), driven against a fake
// Gmail API and a fake Google Identity Services token client.

const { test, expect } = require('./fixtures');

async function openFetchPage(page) {
  const config = page.waitForResponse('**/api/email/config');
  await page.goto('/fetch-gmail');
  await config;
  // The token client is initialised right after the config arrives.
  await page.waitForFunction(() => !!(window.google && window.google.accounts));
}

test.describe('Gmail import', () => {
  test('shows enabled fetchers and a default start date', async ({ page, seeded }) => {
    await openFetchPage(page);
    const checkbox = page.locator('input[name="fetchers"]');
    await expect(checkbox).toHaveCount(1);
    await expect(checkbox).toBeChecked();
    await expect(checkbox).toHaveAttribute('value', seeded.ids.fetchers['Test Bank']);
    await expect(page.getByText('Test Bank: alerts@testbank.example')).toBeVisible();
    // Defaults to the date of the most recent transaction.
    await expect(page.locator('#after_date')).toHaveValue(/^\d{4}-\d{2}-\d{2}$/);
    await expect(page.locator('#gmail-status-badge')).toContainText('Connect Gmail');
  });

  test('without fetchers the user is pointed to the configuration page', async ({ page, login }) => {
    await login();
    await page.goto('/fetch-gmail');
    await expect(page.getByText('No fetchers configured yet.')).toBeVisible();
    await expect(page.locator('#start-btn')).toBeDisabled();
    await page.getByRole('link', { name: 'Configure Fetchers' }).click();
    await expect(page).toHaveURL(/\/settings\/fetchers$/);
  });

  test('imports transactions from Gmail and skips them on the next run', async ({ page, seeded, gmail }) => {
    gmail.emailAddress = seeded.userId;
    const yesterday = new Date(Date.now() - 24 * 3600 * 1000);
    gmail.addMessage({ id: 'aa01', body: 'Merchant: Garden Center\nAmount: $41.99', date: yesterday });
    gmail.addMessage({ id: 'aa02', body: 'Merchant: SUPERMARKET DELUXE\nAmount: $18.40', date: yesterday });
    gmail.addMessage({ id: 'aa03', body: 'This email has nothing to parse', date: yesterday });

    await openFetchPage(page);
    await page.locator('#after_date').fill('2020-01-01');
    await page.locator('#start-btn').click();

    await expect(page).toHaveURL(/\/fetch-gmail\/progress\?/);
    expect(new URL(page.url()).searchParams.get('after_date')).toBe('2020-01-01');
    expect(new URL(page.url()).searchParams.getAll('fetchers')).toEqual([seeded.ids.fetchers['Test Bank']]);

    await expect(page.locator('#complete-message')).toBeVisible();
    await expect(page.locator('#results-summary')).toContainText('Test Bank: 2 imported');
    await expect(page.locator('#log-container')).toContainText('Found 3 message(s)');
    // The Gmail search honours the fetcher's sender and subject filter and the date.
    const listQuery = decodeURIComponent(gmail.requests.find((r) => r.includes('/messages?')));
    expect(listQuery).toContain('from:alerts@testbank.example');
    expect(listQuery).toContain('subject:transaction');
    expect(listQuery).toContain('after:2020-01-01');

    await page.getByRole('link', { name: 'Go to Review Page' }).click();
    const garden = page.locator('.transaction-card', { hasText: 'Garden Center' });
    await expect(garden).toBeVisible();
    await expect(garden.locator('.info-value[data-amount]')).toContainText('$41.99');
    // Imported transactions go through the normal classification pipeline.
    const deluxe = page.locator('.transaction-card', { hasText: 'SUPERMARKET DELUXE' });
    await expect(deluxe.locator('.badge-category')).toHaveText('Groceries');
    await expect(page.locator('#filter-form [name="transaction_source"] option', { hasText: 'Test Bank' })).toHaveCount(1);
    await expect(page.locator('.transaction-card')).toHaveCount(9);

    // The token is cached, so a second run needs no new authorisation and
    // already-imported messages are skipped.
    await openFetchPage(page);
    await expect(page.locator('#gmail-status-badge')).toHaveText('Gmail Connected');
    await page.locator('#after_date').fill('2020-01-01');
    await page.locator('#start-btn').click();
    // The unparseable email was never imported, so only it is fetched again.
    await expect(page.locator('#log-container')).toContainText('1 new, 2 already imported');
    await expect(page.locator('#results-summary')).toContainText('Test Bank: 0 imported');
    // The progress page sends the user to the review page on its own.
    await expect(page).toHaveURL(/\/review\?sort_by=date/, { timeout: 10_000 });
    await expect(page.locator('.transaction-card')).toHaveCount(9);
  });

  test('refuses a Gmail account that differs from the signed-in user', async ({ page, seeded, gmail }) => {
    gmail.emailAddress = 'somebody-else@example.com';
    await openFetchPage(page);
    await page.locator('#start-btn').click();
    await expect(page.locator('#auth-error')).toContainText('Gmail account mismatch');
    await expect(page.locator('#start-btn')).toBeEnabled();
    await expect(page).toHaveURL(/\/fetch-gmail$/);
  });

  test('the progress page explains when Gmail is not connected', async ({ page, seeded }) => {
    await page.goto('/fetch-gmail/progress');
    await expect(page.locator('#error-message')).toBeVisible();
    await expect(page.locator('#error-text')).toContainText('Gmail is not connected');
    await page.getByRole('link', { name: 'Try Again' }).click();
    await expect(page).toHaveURL(/\/fetch-gmail$/);
  });
});

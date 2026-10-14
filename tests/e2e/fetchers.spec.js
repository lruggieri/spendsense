// Email fetcher configuration (/settings/fetchers).

const { test, expect, expectToast, confirmDialog, clickFabAction } = require('./fixtures');

const fetcherRow = (page, name) =>
  page.locator('.fetcher-table tbody tr', { has: page.locator('.fetcher-name', { hasText: new RegExp(`^${name}$`) }) });

const EMAIL = 'Card purchase\nMerchant: Neighborhood Grocer\nAmount: $23.10\n';

async function fillFetcherBasics(page, name) {
  await page.locator('#fetcher-name').fill(name);
  await page.locator('.from-email-input').first().fill('notify@shop.example');
  await expect(page.locator('#default-currency option[value="EUR"]')).toBeAttached();
  await page.locator('#default-currency').selectOption('EUR');
}

async function enableExpertMode(page) {
  await page.locator('.toggle-switch').click();
  await expect(page.locator('#confirm-title')).toHaveText('Enable Expert Mode?');
  await confirmDialog(page);
  await expectToast(page, 'Expert mode enabled');
}

test.describe('Fetchers', () => {
  test('lists fetchers with their configuration', async ({ page, seeded }) => {
    await page.goto('/settings/fetchers');
    const row = fetcherRow(page, 'Test Bank');
    await expect(row).toBeVisible();
    await expect(row.locator('.email-col')).toContainText('alerts@testbank.example');
    await expect(row.locator('.subject-col')).toHaveText('transaction');
    await expect(row.locator('.status-badge')).toHaveText('Enabled');
    await expect(row.locator('.version-badge')).toHaveCount(0);
  });

  test('shows an empty state without fetchers', async ({ page, login }) => {
    await login();
    await page.goto('/settings/fetchers');
    await expect(page.getByText('No fetchers configured yet.')).toBeVisible();
  });

  test('disables and re-enables a fetcher', async ({ page, seeded }) => {
    await page.goto('/settings/fetchers');
    const row = fetcherRow(page, 'Test Bank');

    await row.getByTitle('Disable').click();
    await expectToast(page, 'Fetcher disabled');
    await expect(row.locator('.status-badge')).toHaveText('Disabled');
    await expect(row.getByTitle('Enable')).toBeVisible();

    await row.getByTitle('Enable').click();
    await expectToast(page, 'Fetcher enabled');
    await expect(row.locator('.status-badge')).toHaveText('Enabled');

    await page.reload();
    await expect(fetcherRow(page, 'Test Bank').locator('.status-badge')).toHaveText('Enabled');
  });

  test('disabled fetchers are not offered for Gmail imports', async ({ page, seeded }) => {
    await page.goto('/settings/fetchers');
    await fetcherRow(page, 'Test Bank').getByTitle('Disable').click();
    await expectToast(page, 'Fetcher disabled');

    await page.goto('/fetch-gmail');
    await expect(page.getByText('No fetchers configured yet.')).toBeVisible();
    await expect(page.locator('#start-btn')).toBeDisabled();
  });

  test('the floating action button opens the create page', async ({ page, seeded }) => {
    await page.goto('/settings/fetchers');
    await clickFabAction(page, 'Create Fetcher');
    await expect(page).toHaveURL(/\/settings\/fetchers\/new$/);
    await expect(page.locator('#fetcher-name')).toHaveValue('');
    await expect(page.locator('.email-example-card')).toHaveCount(1);
    await expect(page.locator('.from-email-input')).toHaveCount(1);
  });

  test('creates a fetcher with LLM-generated patterns', async ({ page, seeded }) => {
    await page.goto('/settings/fetchers/new');
    await fillFetcherBasics(page, 'Grocer Card');
    await page.locator('textarea[id^="email-text-"]').first().fill(EMAIL);
    await page.getByRole('button', { name: 'Generate Patterns & Parse' }).click();

    await expect(page.locator('#results-section')).toBeVisible();
    await expect(page.locator('#transactions-container')).toContainText('Neighborhood Grocer');
    // Generated patterns are read-only outside expert mode.
    await expect(page.locator('#amount-pattern')).toHaveAttribute('readonly', 'readonly');

    await page.getByRole('button', { name: '+ Add Test Email Example' }).click();
    await page.locator('textarea[id^="test-email-text-"]').first().fill(EMAIL.replace('23.10', '99.99'));
    await page.getByRole('button', { name: 'Test Patterns' }).click();
    await expect(page.locator('#test-transactions-container')).toContainText('99.99');

    await page.getByRole('button', { name: 'Save Fetcher Configuration' }).click();
    await expectToast(page, 'Fetcher saved successfully!');

    await page.goto('/settings/fetchers');
    await expect(fetcherRow(page, 'Grocer Card')).toBeVisible();
    await expect(fetcherRow(page, 'Grocer Card').locator('.email-col')).toContainText('notify@shop.example');
  });

  test('tests patterns against Gmail messages from the configured senders', async ({ page, seeded, gmail }) => {
    gmail.addMessage({ body: 'Merchant: Mail Order Co\nAmount: $8.00' });
    gmail.addMessage({ body: 'Merchant: Bookshop\nAmount: $15.75' });

    await page.goto('/settings/fetchers/new');
    await fillFetcherBasics(page, 'From Gmail');
    await page.locator('textarea[id^="email-text-"]').first().fill(EMAIL);
    await page.getByRole('button', { name: 'Generate Patterns & Parse' }).click();
    await expect(page.locator('#pattern-test-section')).toBeVisible();

    // No explicit test emails: the latest messages from the sender are fetched.
    await page.getByRole('button', { name: 'Test Patterns' }).click();
    const results = page.locator('#test-transactions-container');
    await expect(results).toContainText('Mail Order Co');
    await expect(results).toContainText('Bookshop');
    expect(gmail.requests.some((r) => r.includes('from%3Anotify%40shop.example'))).toBeTruthy();
    await expect(page.locator('#save-fetcher-section')).toBeVisible();
  });

  test('requires an email example and a valid configuration', async ({ page, seeded }) => {
    await page.goto('/settings/fetchers/new');
    await page.getByRole('button', { name: 'Generate Patterns & Parse' }).click();
    await expectToast(page, 'Please add at least one email example');

    // Remove/add example cards; at least one card always remains.
    await page.getByRole('button', { name: '+ Add Email Example' }).click();
    await expect(page.locator('.email-example-card')).toHaveCount(2);
    await page.locator('.email-example-card').nth(1).getByTitle('Remove').click();
    await page.locator('.email-example-card').nth(0).getByTitle('Remove').click();
    await expect(page.locator('.email-example-card')).toHaveCount(1);

    // Multiple sender addresses can be added and removed.
    await page.getByRole('button', { name: '+ Add Email Address' }).click();
    await expect(page.locator('.from-email-input')).toHaveCount(2);
    await page.locator('.from-email-input-wrapper').nth(1).locator('button').click();
    await expect(page.locator('.from-email-input')).toHaveCount(1);
    await expect(page.locator('.from-email-input-wrapper button')).toBeDisabled();
  });

  test('expert mode allows hand-written patterns with validation', async ({ page, seeded }) => {
    await page.goto('/settings/fetchers/new');
    await fillFetcherBasics(page, 'Handwritten');

    await enableExpertMode(page);
    await expect(page.locator('#results-section')).toBeVisible();
    await expect(page.locator('#amount-pattern')).not.toHaveAttribute('readonly', /.*/);

    // Invalid regex is flagged on blur.
    await page.locator('#amount-pattern').fill('Amount: ([0-9');
    await page.locator('#merchant-pattern').click();
    await expect(page.locator('#amount-pattern-error')).toHaveClass(/visible/);
    await page.getByRole('button', { name: '+ Add Test Email Example' }).click();
    await page.locator('textarea[id^="test-email-text-"]').first().fill(EMAIL);
    await page.getByRole('button', { name: 'Test Patterns' }).click();
    await expectToast(page, 'Invalid amount pattern');

    await page.locator('#amount-pattern').fill('Amount: \\$([\\d.]+)');
    await page.locator('#merchant-pattern').fill('Merchant: (.+)');
    await expect(page.locator('#amount-pattern-error')).not.toHaveClass(/visible/);
    await page.getByRole('button', { name: 'Test Patterns' }).click();
    await expect(page.locator('#test-transactions-container')).toContainText('Neighborhood Grocer');
    await expect(page.locator('#test-transactions-container')).toContainText('23.10');

    await page.getByRole('button', { name: 'Save Fetcher Configuration' }).click();
    await expectToast(page, 'Fetcher saved successfully!');

    // The preference sticks: a new create page starts in expert mode.
    await page.goto('/settings/fetchers/new');
    await expect(page.locator('#expert-mode-toggle')).toBeChecked();
    await expect(page.locator('#results-section')).toBeVisible();

    await page.locator('.toggle-switch').click();
    await expectToast(page, 'Expert mode disabled.');
    await expect(page.locator('#amount-pattern')).toHaveAttribute('readonly', 'readonly');
  });

  test('cancelling the expert mode prompt leaves it off', async ({ page, seeded }) => {
    await page.goto('/settings/fetchers/new');
    await page.locator('.toggle-switch').click();
    await confirmDialog(page, { accept: false });
    await expect(page.locator('#expert-mode-toggle')).not.toBeChecked();
    await expect(page.locator('#results-section')).toBeHidden();
  });

  test('editing a fetcher saves a new version', async ({ page, seeded }) => {
    const originalId = seeded.ids.fetchers['Test Bank'];
    await page.goto('/settings/fetchers');
    await fetcherRow(page, 'Test Bank').getByTitle('Edit').click();
    await expect(page).toHaveURL(new RegExp(`/settings/fetchers/${originalId}$`));

    // The form is pre-filled from the stored fetcher.
    await expect(page.locator('#fetcher-name')).toHaveValue('Test Bank');
    await expect(page.locator('.from-email-input').first()).toHaveValue('alerts@testbank.example');
    await expect(page.locator('#subject-filter')).toHaveValue('transaction');
    await expect(page.locator('#default-currency')).toHaveValue('USD');
    await expect(page.locator('#amount-pattern')).toHaveValue(/Amount/);
    await expect(page.locator('#save-fetcher-section')).toBeVisible();
    await expect(page.locator('.version-note')).toBeVisible();

    await page.locator('#fetcher-name').fill('Test Bank Gold');
    await page.locator('#subject-filter').fill('alert');
    await page.getByRole('button', { name: 'Save as New Version' }).click();
    await expectToast(page, 'Fetcher updated to version 2!');
    await expect(page).not.toHaveURL(new RegExp(`/settings/fetchers/${originalId}$`));
    await expect(page.locator('#fetcher-name')).toHaveValue('Test Bank Gold');

    await page.goto('/settings/fetchers');
    await expect(page.locator('.fetcher-table tbody tr')).toHaveCount(1);
    const row = fetcherRow(page, 'Test Bank Gold');
    await expect(row.locator('.version-badge')).toHaveText('v2');
    await expect(row.locator('.subject-col')).toHaveText('alert');
  });

  test('an unknown fetcher id redirects with an error', async ({ page, seeded }) => {
    await page.goto('/settings/fetchers/does-not-exist');
    await expect(page).toHaveURL(/\/settings$/);
    await expect(page.locator('.flash-error')).toContainText('Fetcher not found');
  });
});

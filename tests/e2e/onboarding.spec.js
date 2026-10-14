// Onboarding wizard: fetchers -> categories -> patterns -> (optional) passkey.

const { test, expect, expectToast, addVirtualAuthenticator } = require('./fixtures');

const SAMPLE_EMAIL = 'Your card was charged.\nMerchant: Blue Bottle Coffee\nAmount: $4.50\nThank you.';
const TEST_EMAIL = 'Your card was charged.\nMerchant: Corner Bakery\nAmount: $12.25\nThank you.';

/** Fill and save a fetcher on the wizard's step 1 (LLM is faked server-side). */
async function createFetcherInWizard(page, name) {
  await page.locator('#fetcher-name').fill(name);
  await page.locator('.from-email-input').first().fill('alerts@mybank.example');
  await page.locator('#subject-filter').fill('purchase');
  await expect(page.locator('#default-currency option[value="USD"]')).toBeAttached();
  await page.locator('#default-currency').selectOption('USD');
  await page.locator('textarea[id^="email-text-"]').first().fill(SAMPLE_EMAIL);

  await page.getByRole('button', { name: 'Generate Patterns & Parse' }).click();

  const results = page.locator('#results-section');
  await expect(results).toBeVisible();
  await expect(page.locator('#amount-pattern')).toHaveValue(/Amount/);
  await expect(page.locator('#merchant-pattern')).toHaveValue(/Merchant/);
  await expect(page.locator('#transactions-container')).toContainText('Blue Bottle Coffee');
  await expect(page.locator('#transactions-container')).toContainText('4.50');

  // Test the generated patterns against a different email, client-side.
  await expect(page.locator('#pattern-test-section')).toBeVisible();
  await page.getByRole('button', { name: '+ Add Test Email Example' }).click();
  await page.locator('textarea[id^="test-email-text-"]').first().fill(TEST_EMAIL);
  await page.getByRole('button', { name: 'Test Patterns' }).click();
  await expect(page.locator('#test-transactions-container')).toContainText('Corner Bakery');

  await page.getByRole('button', { name: 'Save Fetcher Configuration' }).click();
  await expectToast(page, 'Fetcher saved successfully!');
}

test.describe('Onboarding wizard', () => {
  test('a new user is redirected into the wizard from any page', async ({ page, login }) => {
    await login({ onboarded: false });

    await page.goto('/review');
    await expect(page).toHaveURL(/\/onboarding\/step\/1$/);
    // Main navigation is hidden while onboarding.
    await expect(page.locator('header.header')).toHaveCount(0);
    await expect(page.locator('.stepper__step--active')).toContainText('Set Up Email Fetchers');
    await expect(page.locator('.stepper__step')).toHaveCount(4);
    await expect(page.locator('#continue-btn')).toBeDisabled();
    await expect(page.locator('#continue-btn')).toHaveText(/Continue/);
    await expect(page.locator('#back-btn')).toHaveCount(0);
    await expect(page.locator('#fetcher-item-list')).toContainText('No fetchers created yet');

    for (const path of ['/charts', '/groups', '/settings']) {
      await page.goto(path);
      await expect(page).toHaveURL(/\/onboarding\/step\/1$/);
    }
  });

  test('completes all steps end to end and lands on the dashboard', async ({ page, login }) => {
    await login({ onboarded: false });
    await page.goto('/onboarding');
    await expect(page).toHaveURL(/\/onboarding\/step\/1$/);

    // ---- Step 1: fetcher -------------------------------------------------
    await createFetcherInWizard(page, 'My Bank');
    await expect(page.locator('#fetcher-count')).toHaveText('1');
    await expect(page.locator('#fetcher-item-list')).toContainText('My Bank');
    await expect(page.locator('#add-another-fetcher-btn')).toBeVisible();
    await expect(page.locator('#continue-btn')).toBeEnabled();
    await page.locator('#continue-btn').click();

    // ---- Step 2: categories ----------------------------------------------
    await expect(page).toHaveURL(/\/onboarding\/step\/2$/);
    await expect(page.locator('.stepper__step--active')).toContainText('Configure Categories');
    await expect(page.locator('.stepper__step').first()).toHaveClass(/stepper__step--complete/);
    // The built-in "Unknown" category does not count as a user category.
    await expect(page.locator('#category-count')).toHaveText('0');
    await expect(page.locator('#category-item-list')).toContainText('No categories created yet');
    await expect(page.locator('#continue-btn')).toBeDisabled();

    await page.locator('#category-name').fill('Food');
    await page.locator('#category-description').fill('Eating and drinking');
    await page.getByRole('button', { name: 'Save Category' }).click();
    await expectToast(page, 'Category created successfully');
    await expect(page.locator('#category-count')).toHaveText('1');
    await expect(page.locator('#continue-btn')).toBeEnabled();

    // "Add another" re-opens the form for a second category.
    await page.locator('#add-another-category-btn button').click();
    await expect(page.locator('#category-name')).toHaveValue('');
    await page.locator('#category-name').fill('Coffee');
    await page.getByRole('button', { name: 'Save Category' }).click();
    await expect(page.locator('#category-count')).toHaveText('2');
    await expect(page.locator('#category-item-list')).toContainText('Food');
    await expect(page.locator('#category-item-list')).toContainText('Coffee');
    await page.locator('#continue-btn').click();

    // ---- Step 3: patterns ------------------------------------------------
    await expect(page).toHaveURL(/\/onboarding\/step\/3$/);
    await expect(page.locator('#continue-btn')).toBeDisabled();
    await page.locator('#pattern-name').fill('Coffee shops');
    await page.locator('#pattern-category').selectOption({ label: 'Coffee' });
    await page.locator('.rule-keyword').first().fill('COFFEE');
    await expect(page.locator('#preview-description')).toContainText('COFFEE');
    await page.getByRole('button', { name: 'Save Pattern' }).click();
    await expectToast(page, 'Pattern created successfully');
    await expect(page.locator('#pattern-count')).toHaveText('1');
    await expect(page.locator('#pattern-item-list')).toContainText('Coffee shops');
    await expect(page.locator('#pattern-item-list')).toContainText('Coffee');
    await page.locator('#continue-btn').click();

    // ---- Step 4: encryption (optional) -----------------------------------
    await expect(page).toHaveURL(/\/onboarding\/step\/4$/);
    await expect(page.locator('.step-title')).toHaveText('Protect Your Data');
    await expect(page.locator('#register-passkey-btn')).toBeVisible();
    await expect(page.locator('#continue-btn')).toHaveText(/Finish/);
    await expect(page.locator('#continue-btn')).toBeEnabled();
    await page.locator('#continue-btn').click();

    // ---- Completion ------------------------------------------------------
    await expect(page).toHaveURL(/\/onboarding\/complete$/);
    await expect(page.getByRole('heading', { name: "You're All Set!" })).toBeVisible();
    const counts = page.locator('.summary-item');
    await expect(counts.filter({ hasText: 'Fetchers' }).locator('.summary-count')).toHaveText('1');
    await expect(counts.filter({ hasText: 'Categories' }).locator('.summary-count')).toHaveText('2');
    await expect(counts.filter({ hasText: 'Patterns' }).locator('.summary-count')).toHaveText('1');
    await expect(page.getByRole('link', { name: 'Fetch Emails Now' })).toHaveAttribute('href', '/fetch-gmail');

    await page.getByRole('link', { name: 'Go to Dashboard' }).click();
    await expect(page).toHaveURL(/\/review/);
    await expect(page.locator('header.header')).toBeVisible();

    // Onboarding is done: the wizard now bounces back to the app.
    await page.goto('/onboarding');
    await expect(page).toHaveURL(/\/review/);
    await page.goto('/onboarding/step/2');
    await expect(page).toHaveURL(/\/review/);
  });

  test('progress is kept when the user comes back later', async ({ page, login }) => {
    await login({ onboarded: false });
    await page.goto('/onboarding/step/1');
    await createFetcherInWizard(page, 'Resumable Bank');
    await page.locator('#continue-btn').click();
    await expect(page).toHaveURL(/\/onboarding\/step\/2$/);

    // Leaving and coming back resumes at step 2, and the fetcher is still listed.
    await page.goto('/review');
    await expect(page).toHaveURL(/\/onboarding\/step\/2$/);
    await page.locator('#back-btn').click();
    await expect(page).toHaveURL(/\/onboarding\/step\/1$/);
    await expect(page.locator('#fetcher-count')).toHaveText('1');
    await expect(page.locator('#fetcher-item-list')).toContainText('Resumable Bank');
    await expect(page.locator('#continue-btn')).toBeEnabled();
  });

  test('steps cannot be skipped before earlier steps are complete', async ({ page, login }) => {
    await login({ onboarded: false });
    await page.goto('/onboarding/step/1');

    await page.goto('/onboarding/step/3');
    await expect(page).toHaveURL(/\/onboarding\/step\/1$/);
    await page.goto('/onboarding/step/99');
    await expect(page).toHaveURL(/\/onboarding\/step\/1$/);
    await page.goto('/onboarding/complete');
    await expect(page).toHaveURL(/\/onboarding\/step\/1$/);

    // The API refuses to advance without at least one item.
    const resp = await page.request.post('/api/onboarding/advance', { data: { current_step: 1 } });
    expect(resp.status()).toBe(400);
    expect((await resp.json()).error).toContain('at least one item');
  });

  test('wizard forms validate required fields', async ({ page, login }) => {
    await login({ onboarded: false, seed: 'basic', onboardingStep: 2 });

    await page.goto('/onboarding/step/2');
    await expect(page.locator('#category-count')).toHaveText('5');
    await page.getByRole('button', { name: 'Save Category' }).click();
    await expectToast(page, 'Category Name is required');

    await page.goto('/onboarding/step/3');
    await expect(page.locator('#pattern-count')).toHaveText('2');
    await page.getByRole('button', { name: 'Save Pattern' }).click();
    await expectToast(page, 'Pattern name is required');
    await page.locator('#pattern-name').fill('No category');
    await page.getByRole('button', { name: 'Save Pattern' }).click();
    await expectToast(page, 'Target category is required');
  });

  test('fetcher step requires an email example before generating patterns', async ({ page, login }) => {
    await login({ onboarded: false });
    await page.goto('/onboarding/step/1');
    await page.getByRole('button', { name: 'Generate Patterns & Parse' }).click();
    await expectToast(page, 'Please add at least one email example');
    await expect(page.locator('#results-section')).toBeHidden();
  });

  test('a passkey can be registered on the encryption step', async ({ page, context, login }) => {
    await login({ onboarded: false, seed: 'basic', onboardingStep: 4 });

    await addVirtualAuthenticator(context, page);

    await page.goto('/onboarding/step/4');
    await page.locator('#register-passkey-btn').click();
    await expect(page.locator('#setup-status')).toContainText('Passkey registered and encryption enabled!');
    expect(await page.evaluate(() => localStorage.getItem('encryption_dek'))).toBeTruthy();

    // Reloading shows the registered passkey.
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Registered Passkeys' })).toBeVisible();
    await expect(page.locator('.credential-item')).toHaveCount(1);
    await expect(page.locator('.stepper__step--active')).toContainText('Protect Your Data');

    await page.locator('#continue-btn').click();
    await expect(page).toHaveURL(/\/onboarding\/complete$/);
  });
});

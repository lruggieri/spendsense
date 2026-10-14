// Public pages, authentication guards, navigation and global UI chrome.

const { test, expect } = require('./fixtures');

test.describe('Public pages', () => {
  test('the landing page invites anonymous visitors to sign in @mobile', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('.hero-title')).toHaveText('SpendSense');
    await expect(page.locator('.google-login-btn')).toHaveAttribute('href', '/login/start');
    await expect(page.locator('header.header')).toHaveCount(0);

    await page.getByRole('link', { name: 'Privacy Policy' }).click();
    await expect(page).toHaveURL(/\/privacy-policy$/);
    await expect(page.locator('body')).toContainText('Google API Services User Data Policy');
  });

  test('the login page starts the Google OAuth flow', async ({ page }) => {
    await page.goto('/login?next=/charts');
    await expect(page.locator('.login-title')).toHaveText('SpendSense');
    const link = page.locator('.google-login-btn');
    await expect(link).toHaveAttribute('href', '/login/start?next=/charts');

    // Following it redirects to Google's consent screen (blocked by the test network stub).
    const googleRequest = page.waitForRequest((req) => req.url().startsWith('https://accounts.google.com/'));
    await link.click().catch(() => {});
    const url = new URL((await googleRequest).url());
    expect(url.pathname).toBe('/o/oauth2/auth');
    expect(url.searchParams.get('client_id')).toBe('e2e-client-id.apps.googleusercontent.com');
    expect(url.searchParams.get('redirect_uri')).toMatch(/\/login\/callback$/);
    expect(url.searchParams.get('scope')).toContain('openid');
    expect(url.searchParams.get('scope')).not.toContain('gmail');
  });

  test('robots.txt, sitemap and PWA assets are served', async ({ request }) => {
    const robots = await request.get('/robots.txt');
    expect(robots.ok()).toBeTruthy();
    expect(await robots.text()).toContain('Disallow: /review');

    const sitemap = await request.get('/sitemap.xml');
    expect(await sitemap.text()).toContain('/privacy-policy</loc>');

    const sw = await request.get('/service-worker.js');
    expect(sw.ok()).toBeTruthy();
    expect(await sw.text()).toContain('PRECACHE_ASSETS');

    const manifest = await request.get('/static/manifest.json');
    expect((await manifest.json()).name).toBeTruthy();
  });

  test('unknown pages render the 404 error page', async ({ page }) => {
    const resp = await page.goto('/this/does/not/exist');
    expect(resp.status()).toBe(404);
    await expect(page.locator('body')).toContainText('Page Not Found');
  });
});

test.describe('Authentication guards', () => {
  test('protected pages redirect anonymous users to login and keep the target', async ({ page }) => {
    await page.goto('/groups?group_id=abc');
    await expect(page).toHaveURL(/\/login\?next=/);
    expect(new URL(page.url()).searchParams.get('next')).toBe('/groups?group_id=abc');
    await expect(page.locator('.flash-error')).toContainText('Please sign in to access this page.');
  });

  test('an expired or forged session is cleared', async ({ page, context, baseURL }) => {
    await context.addCookies([{ name: 'session_token', value: 'forged-token', url: baseURL }]);
    await page.goto('/review');
    await expect(page).toHaveURL(/\/login/);
    await expect(page.locator('.flash-error')).toContainText('Your session has expired');
    const cookies = await context.cookies();
    expect(cookies.find((c) => c.name === 'session_token')).toBeUndefined();
  });

  test('signed-in users skip the landing and login pages', async ({ page, seeded }) => {
    await page.goto('/');
    await expect(page).toHaveURL(/\/review$/);
    await page.goto('/login');
    await expect(page).toHaveURL(/\/review$/);
    await page.goto('/login?next=/trends');
    await expect(page).toHaveURL(/\/trends$/);
    // Open redirects are refused.
    await page.goto('/login?next=//evil.example.com');
    await expect(page).toHaveURL(/\/review$/);
  });

  test('logging out from the user menu ends the session', async ({ page, login }) => {
    const { userId } = await login({ seed: 'basic', userName: 'Ada Lovelace' });
    await page.goto('/review');

    await page.locator('#userMenuTrigger').click();
    const menu = page.locator('#userMenuDropdown');
    await expect(menu).toHaveClass(/active/);
    await expect(menu.locator('.user-menu-name')).toHaveText('Ada Lovelace');
    await expect(menu.locator('.user-menu-email')).toHaveText(userId);
    await expect(page.locator('.user-avatar-fallback')).toHaveText('A');

    await menu.getByRole('link', { name: 'Logout' }).click();
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.locator('.flash-success')).toContainText('Successfully signed out');

    await page.goto('/review');
    await expect(page).toHaveURL(/\/login\?next=/);
  });
});

test.describe('Navigation', () => {
  test('the desktop menu reaches every section @desktop-only', async ({ page, seeded, isMobile }) => {
    test.skip(isMobile, 'desktop navigation');
    await page.goto('/review');

    const destinations = [
      ['Transactions', 'Groups', /\/groups$/, 'Groups'],
      ['Analytics', 'Charts', /\/charts$/, 'Expense Analysis'],
      ['Analytics', 'Trends', /\/trends$/, null],
      ['Settings', 'Categories', /\/categories$/, 'Category Settings'],
      ['Settings', 'Patterns', /\/patterns$/, 'Pattern Settings'],
      ['Settings', 'Fetchers', /\/settings\/fetchers$/, null],
      ['Settings', 'API Keys', /\/settings\/api-keys$/, 'MCP API Keys'],
      ['Tools', 'Fetch Gmail', /\/fetch-gmail$/, null],
      ['Transactions', 'Review', /\/review$/, 'Review Transactions'],
    ];
    for (const [section, link, url, heading] of destinations) {
      const menuButton = page.locator('.nav-menu__link', { hasText: section });
      await menuButton.click();
      await expect(menuButton).toHaveAttribute('aria-expanded', 'true');
      await page.locator('.nav-menu__dropdown-link', { hasText: new RegExp(`^${link}$`) }).click();
      await expect(page).toHaveURL(url);
      if (heading) await expect(page.locator('.header-branding h1')).toContainText(heading);
    }
  });

  test('dropdowns close on Escape and outside clicks @desktop-only', async ({ page, seeded, isMobile }) => {
    test.skip(isMobile, 'desktop navigation');
    await page.goto('/review');
    const item = page.locator('.nav-menu__item', { hasText: 'Settings' });
    await item.locator('.nav-menu__link').click();
    await expect(item).toHaveClass(/active/);
    await page.keyboard.press('Escape');
    await expect(item).not.toHaveClass(/active/);

    await item.locator('.nav-menu__link').click();
    await page.locator('.info-note').click();
    await expect(item).not.toHaveClass(/active/);
  });

  test('the mobile menu opens, navigates and closes @mobile-only', async ({ page, seeded, isMobile }) => {
    test.skip(!isMobile, 'mobile navigation');
    await page.goto('/review');

    await expect(page.locator('.main-nav')).toBeHidden();
    const overlay = page.locator('#mobileMenuOverlay');
    await page.locator('#mobileMenuTrigger').click();
    await expect(overlay).toHaveClass(/active/);
    await page.locator('#mobileMenuClose').click();
    await expect(overlay).not.toHaveClass(/active/);

    await page.locator('#mobileMenuTrigger').click();
    await page.keyboard.press('Escape');
    await expect(overlay).not.toHaveClass(/active/);

    await page.locator('#mobileMenuTrigger').click();
    await overlay.getByRole('link', { name: 'Patterns' }).click();
    await expect(page).toHaveURL(/\/patterns$/);
    await page.locator('#mobileMenuTrigger').click();
    await expect(overlay.locator('.mobile-menu-link.active')).toHaveText('Patterns');
  });

  test('the user menu links to settings @mobile', async ({ page, seeded }) => {
    await page.goto('/charts');
    await page.locator('#userMenuTrigger').click();
    await page.locator('#userMenuDropdown').getByRole('link', { name: 'Settings' }).click();
    await expect(page).toHaveURL(/\/settings$/);
    // Clicking outside closes the menu.
    await page.locator('#userMenuTrigger').click();
    await page.locator('.info-note').click();
    await expect(page.locator('#userMenuDropdown')).not.toHaveClass(/active/);
  });

  test('the floating action button only appears on pages with actions @mobile', async ({ page, seeded }) => {
    for (const path of ['/review', '/groups', '/patterns', '/categories', '/settings/fetchers']) {
      await page.goto(path);
      await expect(page.locator('#fab-container'), path).toBeVisible();
    }
    for (const path of ['/charts', '/trends', '/settings', '/fetch-gmail']) {
      await page.goto(path);
      await expect(page.locator('#fab-container'), path).toBeHidden();
    }

    await page.goto('/review');
    const fab = page.locator('#fab-main');
    await fab.click();
    await expect(fab).toHaveAttribute('aria-expanded', 'true');
    await expect(page.locator('.fab-action__label')).toHaveText(['Add Transaction', 'Re-categorize All']);
    await page.keyboard.press('Escape');
    await expect(fab).toHaveAttribute('aria-expanded', 'false');
  });

  test('triple-tapping the logo opens the debug panel', async ({ page, seeded }) => {
    await page.goto('/review');
    const logo = page.locator('.header-logo');
    await logo.click();
    await logo.click();
    await logo.click();
    await expect(page.locator('#debug-panel')).toBeVisible();
    await expect(page.locator('#debug-content')).not.toBeEmpty();
  });
});

test.describe('Encryption banner', () => {
  test('prompts to set up a passkey until dismissed', async ({ page, login }) => {
    await login({ seed: 'basic', showEncryptionBanner: true });
    await page.goto('/review');

    const banner = page.locator('#encryption-banner');
    await expect(banner).toBeVisible();
    await expect(banner.getByRole('link', { name: 'Set up a passkey' })).toHaveAttribute('href', '/passkey/setup');

    await banner.getByRole('button', { name: 'Dismiss' }).click();
    await expect(banner).toHaveCount(0);
    await page.reload();
    await expect(page.locator('#encryption-banner')).toHaveCount(0);
  });
});

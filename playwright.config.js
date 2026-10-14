// @ts-check
const { defineConfig, devices } = require('@playwright/test');

const PORT = Number(process.env.E2E_PORT || 5055);
// WebAuthn rejects IP addresses as RP IDs, so the suite must use "localhost".
const BASE_URL = `http://localhost:${PORT}`;

module.exports = defineConfig({
  testDir: './tests/e2e',
  testMatch: '**/*.spec.js',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  // Every test logs in as its own user, so tests are isolated; the cap only
  // keeps SQLite write contention on the shared test server reasonable.
  workers: process.env.CI ? 2 : 4,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  timeout: 30_000,
  expect: { timeout: 7_000 },
  use: {
    baseURL: BASE_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    // The service worker caches static assets aggressively; tests must hit the server.
    serviceWorkers: 'block',
    timezoneId: 'UTC',
    locale: 'en-US',
  },
  projects: [
    {
      name: 'desktop',
      use: { ...devices['Desktop Chrome'] },
      grepInvert: /@mobile-only/,
    },
    {
      name: 'mobile',
      use: { ...devices['Pixel 7'] },
      // Only specs tagged @mobile run on the phone viewport.
      grep: /@mobile/,
    },
  ],
  webServer: {
    command: `${process.env.PYTHON || 'python3'} tests/e2e/server.py`,
    url: `${BASE_URL}/__e2e__/health`,
    env: { E2E_PORT: String(PORT) },
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
    stdout: 'pipe',
    stderr: 'pipe',
  },
});

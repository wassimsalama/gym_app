import { defineConfig, devices } from '@playwright/test';

/**
 * End-to-end tests against the production web bundle, served the way
 * Cloudflare Pages serves it: static files with a single-page-app fallback.
 *
 *   npm run e2e:build   # after any app change
 *   npm run e2e         # runs against that build
 *
 * The bundle goes to dist-e2e, never dist, so a test build can never be the
 * folder a deploy uploads. It is built with fixed, unresolvable service URLs
 * (see e2e/fixtures.ts), and the fixture aborts any request that leaves the
 * local server, so no test can reach the real API or Supabase project.
 */
const PORT = 4173;

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  // Ends a hung run as a reported failure, well inside the CI job's 20 minutes,
  // so the report still uploads: a job killed by timeout-minutes is cancelled,
  // and the upload step skips cancelled jobs. `--debug` turns it off.
  globalTimeout: 10 * 60_000,
  // One retry in CI. A test that fails and then passes is reported as
  // "flaky" rather than hidden, which is what the flaky-test rate is read from.
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: 'retain-on-failure',
    // Name the step that hung instead of reporting a bare test timeout.
    actionTimeout: 10_000,
    navigationTimeout: 15_000,
  },
  projects: [
    // iPhone Safari is the device the app is built for, and WebKit is the
    // engine where the icon-font bug showed up while Chrome looked fine.
    { name: 'mobile-safari', use: { ...devices['iPhone 13'] } },
    { name: 'desktop-chrome', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: {
    command: `node e2e/serve.js dist-e2e ${PORT}`,
    url: `http://127.0.0.1:${PORT}`,
    // Never reuse a server already on the port. serve.js starts in
    // milliseconds, and 4173 is also `vite preview`'s default, so reuse could
    // quietly run the suite against a different site.
    reuseExistingServer: false,
    timeout: 15_000,
  },
});

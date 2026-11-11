/**
 * Every end-to-end test imports `test` and `expect` from here rather than from
 * @playwright/test.
 *
 * The bundle is built with the service URLs below (`npm run e2e:build`). The
 * `.invalid` domain is reserved and never resolves, so nothing could reach a
 * real service even without the guard. The guard makes that explicit: any
 * request that leaves the local server is aborted unless the test has routed it
 * itself. Tests need no secrets in CI, and nothing they do touches production.
 *
 * To fake an endpoint, register a route for it in the test. Playwright tries
 * routes newest first, so the test's route wins over this guard:
 *
 *   await page.route(`${API_URL}/**`, (route) => route.fulfill({ status: 503 }));
 */
import { test as base, expect } from '@playwright/test';

export const API_URL = 'http://api.e2e.invalid';
export const SUPABASE_URL = 'https://e2e.supabase.invalid';

export const test = base.extend<{ blockExternalRequests: void }>({
  blockExternalRequests: [
    async ({ page, baseURL }, use) => {
      const local = new URL(baseURL ?? 'http://127.0.0.1').origin;
      await page.route(
        (url) => url.origin !== local,
        (route) => route.abort('blockedbyclient'),
      );
      await use();
    },
    { auto: true },
  ],
});

export { expect };

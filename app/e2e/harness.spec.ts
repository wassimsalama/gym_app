/**
 * Harness checks, not tests of app behaviour. They prove what every real
 * end-to-end test relies on: the production bundle boots in both browsers, the
 * router runs, and deep links are served the way Cloudflare Pages serves them.
 * Real tests are designed from the graph-coverage model of the user flows and
 * go alongside this file.
 */
import { expect, test } from './fixtures';

test('the bundle boots and a signed-out visitor lands on sign-in', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveURL(/\/sign-in$/);
  await expect(page.getByPlaceholder('Email')).toBeVisible();
});

test('a deep link is answered by the single-page-app fallback', async ({ page }) => {
  const response = await page.goto('/reset-password');
  expect(response?.status()).toBe(200);
  expect(response?.headers()['content-type']).toContain('text/html');
});

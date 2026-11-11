/**
 * Harness checks, not tests of app behaviour. They prove what every real
 * end-to-end test relies on: the production bundle boots in both browsers, the
 * router runs, the HTML shell carries the same patches users get, and deep
 * links are served the way Cloudflare Pages serves them.
 * Real tests are designed from the graph-coverage model of the user flows and
 * go alongside this file.
 */
import { expect, test } from './fixtures';

test('the bundle boots and a signed-out visitor lands on sign-in', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveURL(/\/sign-in$/);
  await expect(page.getByPlaceholder('Email')).toBeVisible();
});

test('the HTML shell is patched the way production is', async ({ page }) => {
  // scripts/patch-html.js runs after every export, and these are the three
  // patches verify-build.js asserts. Without viewport-fit=cover iOS reports
  // every safe-area inset as zero, so Mobile Safari tests would be laying out a
  // page users never see.
  await page.goto('/');
  await expect(page.locator('meta[name="viewport"]')).toHaveAttribute(
    'content',
    /viewport-fit=cover/,
  );
  await expect(page.locator('meta[name="theme-color"]')).toHaveCount(1);
  await expect(page.locator('style#mobile-shell')).toHaveCount(1);
});

test('a deep link is answered by the single-page-app fallback', async ({ page }) => {
  const response = await page.goto('/reset-password');
  expect(response?.status()).toBe(200);
  expect(response?.headers()['content-type']).toContain('text/html');
});

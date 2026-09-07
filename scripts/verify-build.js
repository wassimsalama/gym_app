/**
 * Refuse to ship a web build that points at a development address.
 *
 * EXPO_PUBLIC_* values are inlined at build time by a Babel transform, and
 * Metro caches that transform — so changing the environment does not
 * necessarily change the bundle. A production build once came out pointing at
 * a laptop's LAN IP: it loads perfectly and then fails every request for
 * everyone not on that network. Nothing in the build output looks wrong. You
 * have to read the bundle.
 *
 * The check distinguishes two cases, because they are not the same:
 *
 *   - A private LAN address is never a library default. If one is in there, it
 *     came from our configuration, and shipping it is always wrong.
 *   - `localhost` does appear in dependencies as an unused fallback —
 *     gotrue-js carries http://localhost:9999. It only matters if there is no
 *     real API URL, which would mean ours went missing.
 */

const fs = require('node:fs');
const path = require('node:path');

const DIST = path.join(__dirname, '..', 'app', 'dist');
const BUNDLE_DIR = path.join(DIST, '_expo', 'static', 'js', 'web');

const LAN_ADDRESS =
  /https?:\/\/(10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(:\d+)?/g;
const PRODUCTION_API = /https:\/\/[a-z0-9][a-z0-9.-]*\.(up\.railway\.app|fly\.dev|onrender\.com|run\.app)[^"'`\s]*/;
const SUPABASE = /https:\/\/[a-z0-9]+\.supabase\.co/;

function fail(message) {
  console.error(`\n  BUILD REJECTED: ${message}\n`);
  process.exit(1);
}

if (!fs.existsSync(BUNDLE_DIR)) fail(`no bundle at ${BUNDLE_DIR} — run the build first`);

const bundles = fs.readdirSync(BUNDLE_DIR).filter((f) => f.endsWith('.js'));
if (bundles.length === 0) fail('the build produced no javascript');

const source = bundles
  .map((f) => fs.readFileSync(path.join(BUNDLE_DIR, f), 'utf8'))
  .join('\n');

const lan = [...new Set(source.match(LAN_ADDRESS) ?? [])];
if (lan.length > 0) {
  fail(
    `the bundle points at a local network address: ${lan.join(', ')}\n` +
      '  That came from configuration, not a dependency. Check app/.env.production\n' +
      '  and rebuild with --clear — Metro caches inlined values and will otherwise\n' +
      '  reuse the old ones.',
  );
}

const api = source.match(PRODUCTION_API)?.[0];
if (!api) {
  fail(
    'no production API URL found in the bundle.\n' +
      '  EXPO_PUBLIC_API_URL is probably unset, so every request would fail.',
  );
}

const supabase = source.match(SUPABASE)?.[0];
if (!supabase) fail('no Supabase URL in the bundle — EXPO_PUBLIC_SUPABASE_URL is unset');

if (!fs.existsSync(path.join(DIST, 'privacy.html'))) {
  fail('privacy.html is missing — the policy is linked from Settings and would 404');
}

console.log('\n  Build is shippable:');
console.log(`    api       ${api}`);
console.log(`    supabase  ${supabase}`);
console.log('    privacy   present');
console.log('    no local network addresses\n');

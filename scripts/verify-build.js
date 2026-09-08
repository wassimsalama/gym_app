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

const fs = require("node:fs");
const path = require("node:path");

const DIST = path.join(__dirname, "..", "app", "dist");
const BUNDLE_DIR = path.join(DIST, "_expo", "static", "js", "web");

const LAN_ADDRESS =
  /https?:\/\/(10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(:\d+)?/g;
const PRODUCTION_API =
  /https:\/\/[a-z0-9][a-z0-9.-]*\.(up\.railway\.app|fly\.dev|onrender\.com|run\.app)[^"'`\s]*/;
const SUPABASE = /https:\/\/[a-z0-9]+\.supabase\.co/;

function fail(message) {
  console.error(`\n  BUILD REJECTED: ${message}\n`);
  process.exit(1);
}

if (!fs.existsSync(BUNDLE_DIR))
  fail(`no bundle at ${BUNDLE_DIR} — run the build first`);

const bundles = fs.readdirSync(BUNDLE_DIR).filter((f) => f.endsWith(".js"));
if (bundles.length === 0) fail("the build produced no javascript");

const source = bundles
  .map((f) => fs.readFileSync(path.join(BUNDLE_DIR, f), "utf8"))
  .join("\n");

const lan = [...new Set(source.match(LAN_ADDRESS) ?? [])];
if (lan.length > 0) {
  fail(
    `the bundle points at a local network address: ${lan.join(", ")}\n` +
      "  That came from configuration, not a dependency. Check app/.env.production\n" +
      "  and rebuild with --clear — Metro caches inlined values and will otherwise\n" +
      "  reuse the old ones.",
  );
}

const api = source.match(PRODUCTION_API)?.[0];
if (!api) {
  // Report what the build actually saw. On a hosted builder the usual cause is
  // that the variables were set as *runtime* variables rather than *build*
  // ones, and the difference is invisible from the error alone.
  const seen = Object.keys(process.env)
    .filter((k) => k.startsWith("EXPO_PUBLIC_"))
    .sort();

  const inventory = [
    "EXPO_PUBLIC_API_URL",
    "EXPO_PUBLIC_SUPABASE_URL",
    "EXPO_PUBLIC_SUPABASE_ANON_KEY",
  ]
    .map((k) => `    ${k}  ${process.env[k] ? "set" : "NOT SET"}`)
    .join("\n");

  fail(
    "no production API URL in the bundle — every request would fail.\n\n" +
      `  Environment during this build:\n${inventory}\n` +
      (seen.length === 0
        ? "\n  No EXPO_PUBLIC_* variables were visible at all. On Cloudflare these\n" +
          "  must be set as BUILD variables (Settings -> Build), not runtime\n" +
          "  variables — Expo inlines them while bundling, long before the Worker\n" +
          "  ever runs.\n"
        : "\n  Locally, set them in app/.env.production.\n"),
  );
}

const supabase = source.match(SUPABASE)?.[0];
if (!supabase)
  fail("no Supabase URL in the bundle — EXPO_PUBLIC_SUPABASE_URL is unset");

// Wrangler silently skips every path containing `node_modules` when it uploads,
// so an asset emitted under assets/node_modules/... builds fine, passes every
// local check, and is simply absent in production — the request falls through to
// the SPA fallback and the browser receives index.html. That is how the icon font
// went missing: Chrome had a cached copy and looked fine, Safari asked for it,
// got HTML, and correctly refused. Metro mirrors an asset's source path into the
// output, so anything required straight out of a package lands there. Vendor it
// into app/assets instead.
const assetsDir = path.join(DIST, "assets");
if (fs.existsSync(assetsDir)) {
  const walk = (dir) =>
    fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
      const full = path.join(dir, entry.name);
      return entry.isDirectory() ? walk(full) : [full];
    });

  const emitted = walk(assetsDir).map((f) => path.relative(DIST, f));
  const underNodeModules = (f) => f.split(path.sep).includes("node_modules");
  const isFont = (f) => /\.(ttf|otf|woff2?)$/i.test(f);

  // Wrangler silently skips every path containing `node_modules`, so an asset
  // emitted there is absent in production and the request falls through to the
  // SPA fallback — the browser gets index.html where the file should be. Metro
  // mirrors an asset's source path into the output, so anything required
  // straight out of a package lands in exactly that dead zone.
  //
  // A missing font is not a missing picture: every glyph drawn from it vanishes.
  // That is how the tab bar lost its icons in Safari while Chrome sat on a
  // cached copy and looked correct.
  //
  // The check is that a *deployable* copy exists, not that the package copy is
  // absent. The icon package references its own font whatever we do; what
  // matters is that the copy we register at runtime is one wrangler will upload.
  const strandedFonts = emitted.filter((f) => isFont(f) && underNodeModules(f));
  const deployableFonts = emitted.filter(
    (f) => isFont(f) && !underNodeModules(f),
  );

  for (const font of strandedFonts) {
    const name = path.basename(font);
    if (!deployableFonts.some((f) => path.basename(f) === name)) {
      fail(
        `${name} is only emitted under node_modules, where wrangler will not ` +
          "upload it — the browser will receive HTML instead of a font and every " +
          "glyph drawn from it will disappear.\n\n" +
          "  Copy it into app/assets/fonts and require it from there.",
      );
    }
  }

  const strandedImages = emitted.filter(
    (f) => !isFont(f) && underNodeModules(f),
  );
  if (strandedImages.length > 0) {
    console.warn(
      `\n  Note: ${strandedImages.length} package image(s) under node_modules will not ` +
        "be uploaded. None is user-facing today; if one becomes so, vendor it.",
    );
  }
}

// The shell is patched after export by patch-html.js because Expo ignores
// +html.tsx under `web.output: "single"`. Without viewport-fit=cover every
// safe-area inset reads zero on iOS and the page is letterboxed in white, which
// is invisible on a desktop browser — exactly the kind of break that reaches
// users. Assert it rather than trust it.
const indexHtml = fs.readFileSync(path.join(DIST, "index.html"), "utf8");
for (const [needle, why] of [
  ["viewport-fit=cover", "safe-area insets will read zero on iOS"],
  ['name="theme-color"', "Safari's toolbars will not match the app"],
  [
    'id="mobile-shell"',
    "html/body have no background and overscroll shows white",
  ],
]) {
  if (!indexHtml.includes(needle)) {
    fail(`index.html is missing ${needle} — ${why}. Did patch-html.js run?`);
  }
}

if (!fs.existsSync(path.join(DIST, "privacy.html"))) {
  fail(
    "privacy.html is missing — the policy is linked from Settings and would 404",
  );
}

console.log("\n  Build is shippable:");
console.log(`    api       ${api}`);
console.log(`    supabase  ${supabase}`);
console.log("    privacy   present");
console.log("    no local network addresses\n");

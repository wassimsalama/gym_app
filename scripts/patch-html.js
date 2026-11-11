#!/usr/bin/env node
/**
 * Applies the mobile-web parts of the HTML shell that Expo will not.
 *
 * Expo Router's `app/+html.tsx` is the documented way to control the document.
 * It is ignored here: this project exports with `web.output: "single"`, and in
 * that mode the exporter emits its own default `index.html` — verified by
 * writing a `+html.tsx` and watching the output keep the default viewport tag
 * and a `<title>` the file never declared. Switching to `output: "static"` to
 * regain it would change how every route is served, which is not a trade worth
 * making for four lines of head.
 *
 * So the document is patched after export, and `verify-build.js` asserts the
 * patch landed. If a future Expo version starts honouring `+html.tsx`, or
 * renames what this matches, the build fails loudly rather than silently
 * shipping a page that is broken on a phone.
 *
 * What each change is for:
 *
 * - `viewport-fit=cover`: without it iOS Safari reports every
 *   `env(safe-area-inset-*)` as zero and letterboxes the page inside the safe
 *   area. Every screen positions itself with `insets.top` from
 *   react-native-safe-area-context, which on web reads exactly those variables,
 *   so the app was laid out as though the notch did not exist.
 *
 * - Background colours: nothing sets one on html/body, so the letterbox bars
 *   and the rubber-band overscroll area render browser-default white against a
 *   near-black app.
 *
 * - `theme-color`: tints Safari's toolbars to match instead of leaving white.
 *
 * - `color-scheme: dark`: stops Safari painting a white autofill background
 *   over the inputs.
 */

const fs = require("node:fs");
const path = require("node:path");

const INK = "#0B0F14";
const INDEX = path.join(__dirname, "..", "app", "dist", "index.html");

function fail(message) {
  console.error(`\n  HTML PATCH FAILED: ${message}\n`);
  process.exit(1);
}

if (!fs.existsSync(INDEX))
  fail(`no index.html at ${INDEX} — run the export first`);

let html = fs.readFileSync(INDEX, "utf8");

const VIEWPORT = /<meta\s+name="viewport"\s+content="([^"]*)"\s*\/?>/i;
const found = html.match(VIEWPORT);
if (!found) fail("no viewport meta tag to patch — Expo changed its template");

if (!found[1].includes("viewport-fit=cover")) {
  html = html.replace(
    VIEWPORT,
    `<meta name="viewport" content="${found[1]}, viewport-fit=cover" />`,
  );
}

if (!html.includes('name="theme-color"')) {
  html = html.replace(
    "</head>",
    `  <meta name="theme-color" content="${INK}" />\n  </head>`,
  );
}

if (!html.includes('id="mobile-shell"')) {
  const style = `  <style id="mobile-shell">
      :root { color-scheme: dark; }
      html, body, #root { background-color: ${INK}; }
      body { overscroll-behavior-y: none; }
    </style>\n  `;
  html = html.replace("</head>", `${style}</head>`);
}

fs.writeFileSync(INDEX, html);
console.log(
  "  HTML shell patched: viewport-fit=cover, theme-color, dark background",
);

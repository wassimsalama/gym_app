/**
 * Serve a web export the way Cloudflare Pages does: real files as they are, and
 * index.html for every other path, because expo-router resolves routes in the
 * browser (web.output "single"). A direct visit to /reset-password has to work
 * here exactly as it does in production.
 *
 * Like Pages, the fallback also answers for a missing asset — a font that was
 * never uploaded comes back as HTML with status 200. That is how the icon-font
 * bug reached users, so the harness keeps the behaviour rather than tidying it.
 *
 *   node e2e/serve.js <dir> <port>
 */
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');

const root = path.resolve(process.argv[2] ?? 'dist-e2e');
const port = Number(process.argv[3] ?? 4173);

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.ttf': 'font/ttf',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
};

const index = path.join(root, 'index.html');
if (!fs.existsSync(index)) {
  console.error(`No build at ${root}. Run \`npm run e2e:build\` first.`);
  process.exit(1);
}

http
  .createServer((req, res) => {
    const pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
    let file = path.join(root, pathname);
    const inside = file.startsWith(root + path.sep);
    if (!inside || !fs.existsSync(file) || fs.statSync(file).isDirectory()) file = index;

    res.writeHead(200, { 'Content-Type': TYPES[path.extname(file)] ?? 'application/octet-stream' });
    fs.createReadStream(file).pipe(res);
  })
  .listen(port, '127.0.0.1', () => console.log(`Serving ${root} on http://127.0.0.1:${port}`));

import http, { createServer } from 'node:http';
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
// Demo server runs from apps/demo/, repo root is two levels up
const REPO_ROOT = join(__dirname, '..', '..');
const PORT = process.env.PORT || 3000;
const MEDIALANE_API_KEY = process.env.MEDIALANE_API_KEY;
const STARKNET_RPC = process.env.STARKNET_RPC || 'https://starknet-sepolia.infura.io/v3/YOUR_INFURA_KEY';

const server = createServer((req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');

  if (req.method === 'GET' && req.url === '/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'ok' }));
    return;
  }

  // Proxy Medialane API requests — keeps API key server-side
  if (req.url?.startsWith('/api/medialane/')) {
    if (!MEDIALANE_API_KEY) {
      res.writeHead(502, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'MEDIALANE_API_KEY not configured' }));
      return;
    }
    const target = 'https://api.medialane.io' + req.url.slice('/api/medialane'.length);
    const proxyReq = http.request(target, {
      method: req.method,
      headers: { 'x-api-key': MEDIALANE_API_KEY, 'Content-Type': 'application/json' }
    }, (proxyRes) => {
      res.writeHead(proxyRes.statusCode, proxyRes.headers);
      proxyRes.pipe(res, { end: true });
    });
    req.pipe(proxyReq, { end: true });
    return;
  }

  // Serve built TypeScript packages from /packages/<pkg>/dist/index.js
  // e.g. /packages/wallet/dist/index.js → REPO_ROOT/packages/wallet/dist/index.js
  const packagesMatch = req.url?.match(/^\/packages\/([^/]+)\/dist\/(index\.js|.*\.js)$/);
  if (packagesMatch) {
    const pkgName = packagesMatch[1]; // e.g. "wallet"
    const file = packagesMatch[2];    // e.g. "index.js" or a subpath
    const filePath = join(REPO_ROOT, 'packages', pkgName, 'dist', file);
    if (existsSync(filePath)) {
      res.writeHead(200, { 'Content-Type': 'application/javascript' });
      res.end(readFileSync(filePath));
      return;
    }
  }

  // Serve static files from apps/demo/
  if (req.method === 'GET') {
    let filePath = req.url === '/' ? '/index.html' : req.url;
    const fullPath = join(__dirname, filePath);
    if (existsSync(fullPath)) {
      const ext = fullPath.split('.').pop();
      const types = { html: 'text/html', js: 'application/javascript', css: 'text/css' };
      res.writeHead(200, { 'Content-Type': types[ext] || 'text/plain' });
      res.end(readFileSync(fullPath));
      return;
    }
  }

  res.writeHead(404, { 'Content-Type': 'text/plain' });
  res.end('Not found');
});

server.listen(PORT, () => {
  console.log(`Demo server running on http://localhost:${PORT}`);
  console.log(`STARKNET_RPC: ${STARKNET_RPC ? '(configured)' : '(not set)'}`);
});

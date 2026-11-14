// Local server for MEDvital: serves ./public without caching and stores feedback in ./feedback/<time>_<id>/.
import http from 'node:http'; import fs from 'node:fs'; import path from 'node:path'; import { fileURLToPath } from 'node:url';
const root = path.dirname(fileURLToPath(import.meta.url)), pub = path.join(root, 'public'), fbDir = path.join(root, 'feedback');
const PORT = +process.env.PORT || 8080;
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.webmanifest': 'application/manifest+json', '.png': 'image/png', '.gz': 'application/octet-stream', '.wasm': 'application/wasm', '.txt': 'text/plain', '.task': 'application/octet-stream' };
const send = (res, code, body, type = 'text/plain') => { res.writeHead(code, { 'content-type': type, 'cache-control': 'no-store' }); res.end(body); };
http.createServer((req, res) => {
  const u = new URL(req.url, 'http://x');
  if (req.method === 'POST' && u.pathname === '/api/feedback') {
    const chunks = []; let n = 0;
    req.on('data', c => { n += c.length; if (n > 8e6) req.destroy(); else chunks.push(c); });
    req.on('end', () => {
      try {
        const b = JSON.parse(Buffer.concat(chunks).toString()), text = String(b.text || '').slice(0, 4000), id = String(b.id || '').replace(/[^\w-]/g, '').slice(0, 40);
        if (!text || !id) return send(res, 400, '{"error":"empty"}', 'application/json');
        const d = path.join(fbDir, new Date(Number(b.t) || Date.now()).toISOString().replace(/[:.]/g, '-').slice(0, 19) + '_' + id);
        fs.mkdirSync(d, { recursive: true });
        fs.writeFileSync(path.join(d, 'state.json'), JSON.stringify(b.state || {}, null, 2));
        if (typeof b.shot === 'string' && b.shot.startsWith('data:image/jpeg;base64,')) fs.writeFileSync(path.join(d, 'screenshot.jpg'), Buffer.from(b.shot.split(',')[1], 'base64'));
        const st = b.state || {};
        fs.writeFileSync(path.join(d, 'feedback.md'), `# Feedback ${new Date().toISOString()}\n\n${text}\n\n- Build: ${st.build || ''}\n- Device: ${st.ua || ''}\n- Viewport: ${st.viewport || ''}\n- Pointer events seen on the 3D view: ${JSON.stringify(st.pointer || {})}\n- Errors: ${(st.errors || []).length}\n`);
        console.log('feedback saved:', path.basename(d), '-', text.slice(0, 60)); send(res, 200, '{"ok":true}', 'application/json');
      } catch (e) { send(res, 400, '{"error":"json"}', 'application/json'); }
    });
    return;
  }
  let p = decodeURIComponent(u.pathname); if (p.endsWith('/')) p += 'index.html';
  const f = path.normalize(path.join(pub, p));
  if (!f.startsWith(pub)) return send(res, 403, 'forbidden');
  fs.readFile(f, (e, data) => e ? send(res, 404, 'not found') : send(res, 200, data, MIME[path.extname(f)] || 'application/octet-stream'));
}).listen(PORT, () => console.log(`MEDvital running at http://localhost:${PORT} (Ctrl+C to stop). Feedback is saved in ${fbDir}`));

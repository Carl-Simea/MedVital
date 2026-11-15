import test from 'node:test'; import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs'; import { gunzipSync } from 'node:zlib';
const meta = JSON.parse(readFileSync(new URL('../public/data/anatomy.json', import.meta.url)));
const raw = gunzipSync(readFileSync(new URL('../public/data/anatomy.bin.gz', import.meta.url)));
const buf = raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.byteLength);
function layer(name) {
  const L = meta.layers[name]; let o = L.off;
  const q = new Uint16Array(buf, o, L.nv * 3); o += L.nv * 6; const g = new Uint8Array(buf, o, L.nv); o += L.nv; o += o % 2;
  const p = new Uint16Array(buf, o, L.nv); o += L.nv * 2; o += (4 - (o % 4)) % 4; const f = new Uint32Array(buf, o, L.nf * 3);
  return { L, q, g, p, f };
}
const span = [0, 1, 2].map(a => (meta.bmax[a] - meta.bmin[a]) / 65535);
test('the anatomy file has the layout the loader expects and every vertex points at a listed part', () => {
  assert.equal(meta.v, 2);
  for (const name of ['bone', 'organ', 'muscle']) { const { L, p, f, g } = layer(name);
    let maxP = 0, maxF = 0, maxG = 0; for (const x of p) if (x > maxP) maxP = x; for (const x of f) if (x > maxF) maxF = x; for (const x of g) if (x > maxG) maxG = x;
    assert.ok(maxP < meta.parts.length, name); assert.ok(maxF < L.nv, name); assert.ok(maxG < meta.groups.length, name); }
});
test('no needle triangles: no edge is longer than 100 mm in any layer', () => {
  for (const name of ['bone', 'organ', 'muscle']) { const { q, f } = layer(name); let worst = 0;
    for (let i = 0; i < f.length; i += 3) for (let e = 0; e < 3; e++) { const a = f[i + e] * 3, b = f[i + (e + 1) % 3] * 3;
      const d = Math.hypot((q[a] - q[b]) * span[0], (q[a + 1] - q[b + 1]) * span[1], (q[a + 2] - q[b + 2]) * span[2]); if (d > worst) worst = d; }
    assert.ok(worst < 100, `${name}: longest edge ${worst.toFixed(0)} mm`); }
});
test('single bones and muscles carry a name, a group and, for muscles, a fibre axis', () => {
  const b = meta.parts.filter(p => p.l === 'b'), m = meta.parts.filter(p => p.l === 'm');
  assert.ok(b.length > 200 && m.length > 300);
  for (const p of [...b, ...m]) { assert.ok(p.n && p.g < meta.groups.length); }
  for (const p of m) assert.ok(Math.abs(Math.hypot(...p.a) - 1) < 0.05, p.n);
});

import test from 'node:test'; import assert from 'node:assert/strict';
import { CATALOG, PANELS, refRange, farRange, hypnogram } from '../public/panels.mjs';
import { INDICATORS, evaluate, SRC } from '../public/parts.mjs';

test('catalogue entries are complete and consistent', () => {
  const ids = new Set(PANELS.map(p => p.id)), keys = new Set();
  for (const x of CATALOG) {
    assert.ok(!keys.has(x.key), 'duplicate ' + x.key); keys.add(x.key);
    assert.ok(ids.has(x.panel), x.key + ' panel'); assert.ok(INDICATORS[x.key], x.key + ' indicator');
    assert.equal(x.demo.length, 3, x.key); for (const v of x.demo) assert.ok(v >= x.plaus[0] && v <= x.plaus[1], `${x.key} demo ${v}`);
    for (const sex of ['m', 'f']) { const r = refRange(x, { sex }), f = farRange(x, { sex }); if (r) { assert.ok(r[0] < r[1], x.key); if (f) assert.ok(f[0] <= r[0] && f[1] >= r[1], x.key + ' far'); } }
    if (x.basis === 'verified') assert.ok(SRC[x.tsrc] && /^https:/.test(SRC[x.tsrc].url), x.key + ' source');
    if (x.msrc) assert.ok(SRC[x.msrc], x.key + ' msrc');
    assert.ok(!/[)α]$/.test(x.label), x.key + ': a label must end in a word character for the reader');
  }
});
test('sleep quality follows the NSF adult thresholds', () => {
  const lv = (k, v) => Object.values(evaluate({ [k]: v })).flatMap(s => [...s.warnings, ...s.notes]).find(w => w.key === k).level;
  assert.equal(lv('sleep.latencyMin', 30), 0); assert.equal(lv('sleep.latencyMin', 31), 1);
  assert.equal(lv('sleep.wasoMin', 20), 0); assert.equal(lv('sleep.wasoMin', 41), 1);
  assert.equal(lv('sleep.awakenings', 1), 0); assert.equal(lv('sleep.awakenings', 4), 1);
  assert.equal(lv('sleep.remPct', 21), 0); assert.equal(lv('sleep.remPct', 18), 1);
  assert.equal(lv('sleep.n3Pct', 16), 0); assert.equal(lv('sleep.n3Pct', 12), 1);
});
test('a ranged catalogue value is rated by sex where the range depends on it', () => {
  const lv = (M) => Object.values(evaluate(M)).flatMap(s => [...s.warnings, ...s.notes]).find(w => w.key === 'rbc.M').level;
  assert.equal(lv({ 'rbc.M': 4.3, sex: 'f' }), 0); assert.equal(lv({ 'rbc.M': 4.3, sex: 'm' }), 1); assert.equal(lv({ 'rbc.M': 2.5, sex: 'm' }), 2);
});
test('the reconstructed hypnogram matches the night summary', () => {
  const M = { 'sleep.inBedH': 8, 'sleep.hours': 7.2, 'sleep.latencyMin': 15, 'sleep.wasoMin': 20, 'sleep.awakenings': 2, 'sleep.n1Pct': 5, 'sleep.n3Pct': 20, 'sleep.remPct': 24, 'sleep.cycles': 5 };
  const hy = hypnogram(M), ep = hy.epochs, n = ep.length, sleep = ep.filter(e => e !== 'W').length;
  assert.equal(hy.real, false); assert.ok(n >= 96 && n <= 104, 'length ' + n);
  assert.deepEqual(ep.slice(0, 3), ['W', 'W', 'W']);                                  // 15 min to fall asleep
  const share = s => ep.filter(e => e === s).length / sleep * 100;
  assert.ok(Math.abs(share('3') - 20) < 6 && Math.abs(share('R') - 24) < 6, `N3 ${share('3')} REM ${share('R')}`);
  const half = Math.floor(n / 2), early3 = ep.slice(0, half).filter(e => e === '3').length, late3 = ep.slice(half).filter(e => e === '3').length;
  assert.ok(early3 > late3, 'deep sleep comes early');
  assert.deepEqual(hypnogram({ 'sleep.hypnogram': 'WW12R' }).epochs, ['W', 'W', '1', '2', 'R']);
  assert.equal(hypnogram({}), null);
});

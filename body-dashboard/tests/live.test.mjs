import test from 'node:test'; import assert from 'node:assert/strict';
import { createLive, targets, ACTIVITY_IDS, LIVE_KEYS, TIMELINE } from '../public/live.mjs';
import { SCENARIOS } from '../public/testdata.mjs';
import { RANGES } from '../public/intake.mjs';
import { INDICATORS, evaluate } from '../public/parts.mjs';

const run = (base, activity, n = 60, seed = 3) => { const L = createLive({ base, seed }); let v; for (let i = 0; i < n; i++) v = L.step(1, activity); return v; };
test('the stream is deterministic', () => { assert.deepEqual(run(SCENARIOS.nominal.data, 'exercise'), run(SCENARIOS.nominal.data, 'exercise')); });
test('every live key is a known indicator and stays in a plausible range for every activity and scenario', () => {
  for (const id in SCENARIOS) for (const a of ACTIVITY_IDS) { const v = run(SCENARIOS[id].data, a);
    for (const k of LIVE_KEYS) { assert.ok(INDICATORS[k], k); assert.ok(v[k] >= RANGES[k][0] && v[k] <= RANGES[k][1], `${id} ${a} ${k}=${v[k]}`); } }
});
test('exercise raises heart and breathing rate, sleep lowers the heart rate', () => {
  const b = SCENARIOS.nominal.data, rest = run(b, 'rest'), ex = run(b, 'exercise'), sl = run(b, 'sleep');
  assert.ok(ex['hr.now'] > rest['hr.now'] + 40); assert.ok(ex['resp.rate'] > rest['resp.rate'] + 8); assert.ok(sl['hr.now'] < rest['hr.now']); assert.ok(ex['hrv.rmssdMs'] < rest['hrv.rmssdMs']);
});
test('a high heart or breathing rate during exercise is not flagged, the same values at rest are', () => {
  const b = SCENARIOS.nominal.data, ex = run(b, 'exercise');
  const during = evaluate({ ...b, ...ex, activity: 'exercise' }), atRest = evaluate({ ...b, ...ex, activity: 'rest' });
  assert.equal(during.heart.level, 0); assert.equal(during.lung.level, 0);
  assert.ok(atRest.heart.level >= 2); assert.ok(atRest.lung.level >= 1);
  const recovering = evaluate({ ...b, ...ex, activity: 'rest', recovering: true }); assert.equal(recovering.heart.level, 0); assert.equal(recovering.lung.level, 0);
});
test('the demo timeline visits every activity except the spacewalk and repeats', () => {
  const L = createLive({}), total = TIMELINE.reduce((a, b) => a + b[1], 0), seen = new Set();
  for (let t = 0; t < total; t++) seen.add(L.activityAt(t));
  assert.deepEqual([...seen].sort(), ['exercise', 'rest', 'sleep', 'work']); assert.equal(L.activityAt(3), L.activityAt(3 + total));
  assert.deepEqual(targets({}, 'unknown'), targets({}, 'rest'));
});

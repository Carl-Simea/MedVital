import test from 'node:test';
import assert from 'node:assert/strict';
import { PARTS, SRC, GROUP_IDS, PAIRED, SAMPLE, evaluate, summarize, bodyColors, LEVEL } from '../public/parts.mjs';
import { readFileSync } from 'node:fs';

const meta = JSON.parse(readFileSync(new URL('../public/data/anatomy.json', import.meta.url)));

test('every anatomy group has a part entry (and vice versa, except body)', () => {
  for (const g of meta.groups) assert.ok(PARTS[g], 'missing part ' + g);
  for (const g of GROUP_IDS) if (g !== 'body') assert.ok(meta.groups.includes(g), 'unknown group ' + g);
});
test('every fact and help cites a known source with a URL', () => {
  for (const [id, p] of Object.entries(PARTS)) for (const x of [...p.facts, ...p.helps]) { assert.ok(SRC[x.s], `${id}: ${x.s}`); assert.match(SRC[x.s].url, /^https:\/\//); }
});
test('every part without facts declares a gap', () => {
  for (const [id, p] of Object.entries(PARTS)) if (!p.facts.length) assert.ok(p.gap, id + ' has neither facts nor a gap note');
});
test('paired groups exist', () => { for (const g of PAIRED) assert.ok(PARTS[g], g); });
test('no data -> every part is nodata and nothing needs attention', () => {
  const s = evaluate({}); assert.ok(GROUP_IDS.every(g => s[g].level === LEVEL.nodata)); assert.equal(summarize(s).attention.length, 0);
});
test('hip bone loss: within mean ok, >1x watch, >2x warn', () => {
  const lv = v => evaluate({ 'bmd.hipPct': v, 'mission.month': 4 }).femur.level;
  assert.equal(lv(-5), 0); assert.equal(lv(-9), 1); assert.equal(lv(-13), 2);
});
test('bone loss without mission month never warns', () => { assert.equal(evaluate({ 'bmd.hipPct': -20 }).femur.level, 0); });
test('radiation limits: 600 mSv career and 250 mSv per event are critical', () => {
  assert.equal(evaluate({ 'radiation.careerMsv': 600 }).body.level, 3);
  assert.equal(evaluate({ 'radiation.eventMsv': 250 }).body.level, 3);
  assert.equal(evaluate({ 'radiation.careerMsv': 100 }).body.level, 0);
});
test('thrombus in the jugular vein is critical, stagnant flow is watch', () => {
  assert.equal(evaluate({ 'jugular.flow': 'thrombus' }).vein.level, 3);
  assert.equal(evaluate({ 'jugular.flow': 'stagnant' }).vein.level, 1);
});
test('hemoglobin uses the sex-specific cut-off', () => {
  assert.equal(evaluate({ 'hemoglobin.gdl': 12.5, sex: 'f' }).spleen.level, 0);
  assert.equal(evaluate({ 'hemoglobin.gdl': 12.5, sex: 'm' }).spleen.level, 2);
  assert.equal(evaluate({ 'hemoglobin.gdl': 7.5 }).spleen.level, 3);
});
test('tendon is never rated from strength data', () => { assert.equal(evaluate({ 'strength.changePct': -30 }).tendon.level, LEVEL.nodata); });
test('a PVT value above 20 lapses is critical only when confirmed', () => {
  assert.equal(evaluate({ 'pvt.lapses': 22 }).brain.level, 2);
  assert.equal(evaluate({ 'pvt.lapses': 22, 'pvt.confirmed': true }).brain.level, 3);
});
test('heart rate rules come from the engine', () => {
  assert.equal(evaluate({ 'hr.rest': 130 }).heart.level, 3); assert.equal(evaluate({ 'hr.rest': 65 }).heart.level, 0);
});
test('sample data is deterministic and flags the expected parts', () => {
  const a = JSON.stringify(evaluate(SAMPLE)), b = JSON.stringify(evaluate(SAMPLE)); assert.equal(a, b);
  const s = evaluate(SAMPLE); assert.equal(s.spineL.level, 2); assert.equal(s.spleen.level, 2); assert.equal(s.vein.level, 1);
  assert.ok(Object.keys(bodyColors(s)).length >= 10);
});
test('every warning carries a basis label', () => {
  const s = evaluate(SAMPLE); for (const id of GROUP_IDS) for (const w of [...s[id].warnings, ...s[id].notes]) assert.ok(['verified', 'reference', 'convention', 'model'].includes(w.basis), id + w.rule);
});

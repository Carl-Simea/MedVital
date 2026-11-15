import test from 'node:test';
import assert from 'node:assert/strict';
import { DOMAINS, DOMAIN_IDS, SCORE_SRC, SCORE_SAMPLE, scoreDomain, scoreAll, scoreColor, scale } from '../public/scores.mjs';
import { SRC, SAMPLE } from '../public/parts.mjs';

test('weights of every domain sum to 100 and every source key resolves to an https link', () => {
  const all = { ...SRC, ...SCORE_SRC };
  for (const id of DOMAIN_IDS) {
    assert.equal(DOMAINS[id].components.reduce((a, c) => a + c.weight, 0), 100, id);
    for (const c of DOMAINS[id].components) { if (c.src) { assert.ok(all[c.src], `${id}: ${c.src}`); assert.match(all[c.src].url, /^https:\/\//); } else assert.equal(c.basis, 'convention'); }
  }
});
test('no data gives no score, not a made-up one', () => {
  for (const id of DOMAIN_IDS) { const s = scoreDomain(id, {}); assert.equal(s.score, null); assert.equal(s.coverage.have, 0); }
});
test('scores stay within 1..100 and missing inputs lower coverage, not the score', () => {
  const full = scoreAll({ ...SAMPLE, ...SCORE_SAMPLE });
  for (const id of DOMAIN_IDS) { assert.ok(full[id].score >= 1 && full[id].score <= 100, id); assert.equal(full[id].coverage.have, full[id].coverage.total, id); }
  const part = scoreDomain('sleep', { 'sleep.hours': 8 }); assert.equal(part.score, 100); assert.deepEqual(part.coverage, { have: 1, total: 8 });
  assert.equal(scoreDomain('sleep', { 'sleep.hours': 2, 'pvt.lapses': 40, 'sleep.quality': 1 }).score, 1);
});
test('anchors: 6 h sleep = 50, ISS-average strength loss = 50, protein in range = 100, fluid target depends on sex', () => {
  assert.equal(scoreDomain('sleep', { 'sleep.hours': 6 }).items[0].score, 50);
  assert.equal(scoreDomain('exercise', { 'strength.changePct': -10 }).score, 50);
  assert.equal(scoreDomain('nutrition', { 'nutrition.proteinGkg': 1.5 }).score, 100);
  assert.equal(scoreDomain('nutrition', { 'nutrition.fluidL': 2.1, sex: 'f' }).score, 100);
  assert.ok(scoreDomain('nutrition', { 'nutrition.fluidL': 2.1, sex: 'm' }).score < 100);
});
test('more is not always better: over-eating and excess protein score lower', () => {
  assert.ok(scoreDomain('nutrition', { 'nutrition.energyPct': 150 }).score < scoreDomain('nutrition', { 'nutrition.energyPct': 100 }).score);
  assert.ok(scoreDomain('nutrition', { 'nutrition.proteinGkg': 2.6 }).score < 100);
});
test('colour runs from red to green; scale is flat outside its anchors', () => {
  assert.match(scoreColor(1), /^hsl\(1 /); assert.match(scoreColor(100), /^hsl\(130 /); assert.equal(scale([[0, 0], [10, 100]])(-5), 0); assert.equal(scale([[0, 0], [10, 100]])(50), 100);
});

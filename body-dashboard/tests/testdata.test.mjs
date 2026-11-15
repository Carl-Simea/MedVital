import test from 'node:test'; import assert from 'node:assert/strict';
import { SCENARIOS, SCENARIO_IDS, reportText } from '../public/testdata.mjs';
import { INDICATORS, evaluate, summarize } from '../public/parts.mjs';
import { SCORE_KEYS, scoreAll } from '../public/scores.mjs';
import { extract, RANGES } from '../public/intake.mjs';

test('every scenario covers every indicator and every score input', () => {
  for (const id of SCENARIO_IDS) for (const k of [...Object.keys(INDICATORS), ...SCORE_KEYS, 'mission.month', 'sex']) assert.ok(k in SCENARIOS[id].data, `${id} lacks ${k}`);
});
test('all numbers are inside the plausible ranges of the reader', () => {
  for (const id of SCENARIO_IDS) for (const [k, v] of Object.entries(SCENARIOS[id].data)) if (typeof v === 'number' && RANGES[k]) assert.ok(v >= RANGES[k][0] && v <= RANGES[k][1], `${id} ${k}=${v}`);
});
test('nominal has no finding, mixed has raised values but nothing critical, critical has critical findings', () => {
  const lv = id => { const s = summarize(evaluate(SCENARIOS[id].data)); return s.counts; };
  const n = lv('nominal'); assert.equal(n.watch + n.warn + n.alert, 0); assert.equal(n.nodata, 1);   // only tendons have no indicator
  const m = lv('mixed'); assert.ok(m.watch > 0 && m.warn > 0); assert.equal(m.alert, 0);
  assert.ok(lv('critical').alert > 0);
});
test('scores fall from nominal to critical and all have full coverage', () => {
  const S = Object.fromEntries(SCENARIO_IDS.map(id => [id, scoreAll(SCENARIOS[id].data)]));
  for (const d of ['sleep', 'exercise', 'nutrition']) {
    assert.ok(S.nominal[d].score >= 85, `${d} nominal ${S.nominal[d].score}`);
    assert.ok(S.nominal[d].score > S.mixed[d].score && S.mixed[d].score > S.critical[d].score, d);
    assert.equal(S.mixed[d].coverage.have, S.mixed[d].coverage.total);
  }
});
test('the text report of a scenario is read back completely and unchanged', () => {
  for (const id of SCENARIO_IDS) {
    const s = SCENARIOS[id], r = extract(reportText(id)), want = { ...s.data, 'body.heightCm': s.body.heightCm, 'body.massKg': s.body.massKg };
    delete want['pvt.confirmed'];
    assert.deepEqual(r.rejected, [], id); assert.deepEqual(r.unread, [], id);
    for (const [k, v] of Object.entries(want)) assert.equal(r.values[k], v, `${id} ${k}`);
  }
});

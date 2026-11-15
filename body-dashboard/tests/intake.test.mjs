import test from 'node:test';
import assert from 'node:assert/strict';
import { extract, normalize } from '../public/intake.mjs';
import { INDICATORS } from '../public/parts.mjs';
import { SCORE_KEYS } from '../public/scores.mjs';
import { RANGES } from '../public/intake.mjs';

test('free-text medical report', () => {
  const r = extract(`Crew medical conference, flight day 112 (mission month 4)
Resting heart rate 68 bpm, BP 118/76 mmHg, SpO2 97 %, respiratory rate 14/min, temperature 98.6 °F.
Labs: hemoglobin 12.9 g/dL, 25-OH vitamin D 62 nmol/L, glucose 5.2 mmol/L.
24-hour urine volume 1450 mL, urinary calcium 280 mg.
DXA (postflight): hip BMD -6.4 %, lumbar spine BMD -5.1 %.
Optic disc edema: none. No dizziness on standing. Jugular vein flow stagnant.
Slept 6 h 10 min; sleep quality 3/5. PVT lapses 7, mean reaction time 290 ms.`);
  const v = r.values;
  assert.equal(v['hr.rest'], 68); assert.equal(v['bp.sys'], 118); assert.equal(v['bp.dia'], 76); assert.equal(v['spo2.pct'], 97);
  assert.equal(v['resp.rate'], 14); assert.equal(v['temp.c'], 37); assert.equal(v['hemoglobin.gdl'], 12.9); assert.equal(v['vitd.ngml'], 25);
  assert.equal(v['glucose.mgdl'], 94); assert.equal(v['urine.volumeL'], 1.45); assert.equal(v['urine.calciumMgDay'], 280);
  assert.equal(v['bmd.hipPct'], -6.4); assert.equal(v['bmd.lumbarPct'], -5.1); assert.equal(v['sans.discEdema'], false);
  assert.equal(v['orthostatic.presyncope'], false); assert.equal(v['jugular.flow'], 'stagnant');
  assert.equal(v['sleep.hours'], 6); assert.equal(v['sleep.quality'], 3); assert.equal(v['pvt.lapses'], 7); assert.equal(v['pvt.meanRtMs'], 290);
  assert.equal(v['mission.month'], 4);
});
test('JSON export with indicator keys and with name/value objects', () => {
  assert.deepEqual(extract('{"hr.rest": 64, "spo2.pct": 98, "nutrition.proteinGkg": 1.4}').values, { 'hr.rest': 64, 'spo2.pct': 98, 'nutrition.proteinGkg': 1.4 });
  assert.equal(extract('[{"name":"Heart rate","value":72,"unit":"bpm"}]').values['hr.rest'], 72);
});
test('CSV and TSV', () => {
  const v = extract('measure,value,unit\nHeart rate,70,bpm\nExercise time,560,min\nFluid intake,2.3,L', 'vitals.csv').values;
  assert.equal(v['hr.rest'], 70); assert.equal(v['exercise.minPerWeek'], 560); assert.equal(v['nutrition.fluidL'], 2.3);
  assert.equal(extract('Strength change\t-12 %\nVO2peak change\t-9 %').values['aerobic.changePct'], -9);
});
test('implausible values are rejected, unknown lines are reported, nothing is invented', () => {
  const r = extract('heart rate 400\ncholesterol 190 mg/dL');
  assert.equal(r.values['hr.rest'], undefined); assert.equal(r.rejected[0].key, 'hr.rest');
  assert.ok(r.unread.some(l => /cholesterol/.test(l)));
  assert.deepEqual(extract('Patient feels well.').values, {});
});
test('every key it can produce exists in the app', () => {
  for (const k of Object.keys(RANGES)) assert.ok(INDICATORS[k] || SCORE_KEYS.includes(k) || k === 'mission.month' || k === 'pvt.meanRtMs' || k.startsWith('body.'), k);
});

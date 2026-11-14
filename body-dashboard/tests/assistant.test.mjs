import test from 'node:test';
import assert from 'node:assert/strict';
import { answer, parseMeasurements } from '../public/assistant.mjs';
import { evaluate, SAMPLE } from '../public/parts.mjs';
const ctx = (M = SAMPLE) => ({ parts: evaluate(M), M });

test('parses values from free text', () => {
  const p = parseMeasurements('my heart rate is 72, blood pressure 120/80, slept 6,5 hours, SpO2 96');
  assert.equal(p.set['hr.rest'], 72); assert.equal(p.set['bp.sys'], 120); assert.equal(p.set['bp.dia'], 80); assert.equal(p.set['spo2.pct'], 96);
  assert.equal(parseMeasurements('I slept 6.5 hours').set['sleep.hours'], 6.5);
});
test('rejects implausible values', () => {
  const p = parseMeasurements('heart rate 500'); assert.deepEqual(p.set, {}); assert.ok(p.rejected.length);
  assert.match(answer('heart rate 500', ctx({})).text, /plausible/);
});
test('entering a value returns it for saving', () => { const a = answer('my heart rate is 72', ctx({})); assert.equal(a.set['hr.rest'], 72); assert.ok(a.afterUpdate); });
test('overall summary lists attention items and focuses a part', () => {
  const a = answer('How am I doing?', ctx()); assert.match(a.text, /need attention/); assert.ok(a.focus);
});
test('no data: asks for data instead of inventing', () => { assert.match(answer('how am I doing', ctx({})).text, /no health data/i); });
test('part answer has status, warnings, help and sources from the catalogue', () => {
  const a = answer('what helps my back?', ctx()); assert.match(a.text, /Elevated|Watch/); assert.match(a.text, /What helps/); assert.match(a.text, /Sources:/); assert.equal(a.focus, 'spineL');
});
test('measure question lists how and whether in flight', () => {
  const a = answer('how is bone density measured', ctx()); assert.match(a.text, /DXA/); assert.match(a.text, /not measurable in flight/);
});
test('escalation: critical goes to "now", warnings to next contact', () => {
  const a = answer('should I call the flight surgeon?', ctx({ 'spo2.pct': 85, 'bp.sys': 165 })); assert.match(a.text, /now:/); assert.match(a.text, /Blood oxygen/);
  assert.match(answer('should I call a doctor', ctx({ 'hr.rest': 60 })).text, /Nothing in your data/);
});
test('unknown question admits its limits', () => { assert.match(answer('what is the meaning of life', ctx()).text, /only answer from your health data/); });
test('never cites a source that is not in the catalogue', () => {
  for (const q of ['kidney', 'heart', 'lungs', 'bones', 'muscles', 'brain', 'eyes', 'liver', 'radiation', 'blood']) assert.doesNotMatch(answer(q, ctx()).text, /undefined/);
});

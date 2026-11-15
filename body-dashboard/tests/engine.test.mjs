import test from 'node:test';
import assert from 'node:assert/strict';
import { CONTEXTS, withOneWay, latencyClass, roundTripSec, scorePvt, Baseline, evalPvt, evalHeartRate, evalBoneModel,
  finding, triage, summarizeBySystem, uiStatus, fmtDuration } from '../public/engine.mjs';
import { PvtSession } from '../public/pvt.mjs';

const trialsWith = (n, rt, lapses = 0, lapseRt = 600) =>
  [...Array(n - lapses).fill(0).map(() => ({ rt })), ...Array(lapses).fill(0).map(() => ({ rt: lapseRt }))];

test('latency classes: ISS live, Moon live, Mars autonomous (even at the shortest distance)', () => {
  assert.equal(latencyClass(CONTEXTS.leo), 'live');
  assert.equal(latencyClass(CONTEXTS.moon), 'live');
  assert.equal(latencyClass(CONTEXTS.mars), 'autonomous');
  assert.equal(latencyClass(withOneWay(CONTEXTS.mars, CONTEXTS.mars.minOneWaySec)), 'autonomous');
  assert.equal(latencyClass(withOneWay(CONTEXTS.mars, 60)), 'delayed');
  assert.equal(roundTripSec(CONTEXTS.moon), 2.6);
  assert.equal(fmtDuration(1500), '25 min');
});

test('scorePvt: false starts, lapses, timeout', () => {
  const s = scorePvt([{ rt: 250 }, { rt: 300 }, { rt: 400 }, { rt: null }, { rt: 50 }], { lapseMs: 355, timeoutMs: 5000, premature: 2 });
  assert.equal(s.falseStarts, 3);        // 1 too fast + 2 premature presses
  assert.equal(s.responses, 3);
  assert.equal(s.lapses, 2);             // 400 ms and timeout
  assert.ok(Math.abs(s.meanRt - (250 + 300 + 400 + 5000) / 4) < 1e-9);
  assert.ok(Math.abs(s.meanInvRt - (4 + 1000 / 300 + 2.5 + 0.2) / 4) < 1e-9);
});

test('baseline: z-score only from 3 values, sd floor', () => {
  const b = new Baseline();
  b.add('x', 10); b.add('x', 10);
  assert.equal(b.z('x', 12), null);
  b.add('x', 10);
  assert.ok(Math.abs(b.z('x', 12) - 4) < 1e-6);   // sd-Untergrenze 5 % von 10 = 0,5 → (12−10)/0,5
  const copy = Baseline.from(JSON.parse(JSON.stringify(b)));
  assert.deepEqual(copy.stats('x'), b.stats('x'));
});

test('evalPvt: absolute thresholds 11/20 lapses at 355 ms, confirmation needed for alert', () => {
  const mk = l => scorePvt(trialsWith(60, 250, l), { lapseMs: 355 });
  assert.equal(evalPvt(mk(10)).severity, 0);
  assert.equal(evalPvt(mk(11)).severity, 2);
  const f20 = evalPvt(mk(20));
  assert.equal(f20.severity, 2); assert.ok(f20.rules.includes('pvt.needs-confirmation'));
  assert.equal(evalPvt(mk(20), { confirmed: true }).severity, 3);
});

test('evalPvt: too few responses → watch, baseline z triggers watch/warn', () => {
  assert.equal(evalPvt(scorePvt(trialsWith(5, 250), { lapseMs: 355 })).severity, 0);       // quick check, normal
  assert.equal(evalPvt(scorePvt(trialsWith(5, 250, 3), { lapseMs: 355 })).severity, 1);    // 3 of 5 slow → watch
  assert.ok(evalPvt(scorePvt(trialsWith(2, 250), { lapseMs: 355 })).rules.includes('pvt.invalid'));
  assert.equal(evalPvt(scorePvt(trialsWith(5, 600, 5), { lapseMs: 355 })).severity, 1);   // never alert without a baseline
  const b = new Baseline();
  for (const v of [4.4, 4.5, 4.6, 4.5, 4.4]) b.add('pvt.invRt', v);
  const mk = rt => scorePvt(trialsWith(60, rt, 0), { lapseMs: 355 });
  assert.equal(evalPvt(mk(222), { baseline: b }).severity, 0);
  assert.ok(evalPvt(mk(260), { baseline: b }).severity >= 1);
  assert.equal(evalPvt(mk(330), { baseline: b }).severity, 2);
});

test('evalHeartRate: resting heart-rate thresholds and source cap', () => {
  assert.equal(evalHeartRate({ bpm: 72 }).severity, 0);
  assert.equal(evalHeartRate({ bpm: 104 }).severity, 2);
  assert.equal(evalHeartRate({ bpm: 130, source: 'manual' }).severity, 3);
  const cam = evalHeartRate({ bpm: 130, source: 'camera' });
  assert.equal(cam.severity, 2); assert.ok(cam.rules.includes('cap.camera'));
  assert.equal(evalHeartRate({ bpm: 130, context: 'exercise' }).severity, 0);
});

test('evalBoneModel: model only, never above watch; rates as in the sources', () => {
  const f = evalBoneModel(6);
  assert.equal(f.source, 'model'); assert.equal(f.severity, 1);
  assert.deepEqual(f.detail.avg, [6, 9]);
  assert.equal(f.detail.hip, 9); assert.equal(f.detail.lumbar, 6); assert.ok(Math.abs(f.detail.wholeBody - 1.8) < 1e-9);
  assert.equal(evalBoneModel(0.5).severity, 0);
  assert.equal(finding('b', 'skeleton', 'model', 3, 't').severity, 1);
});

const F = (sev, over = {}) => finding('t', 'brain', 'measured', sev, 'Testbefund', [], over);

test('triage: severity × latency matrix', () => {
  const leo = CONTEXTS.leo, mars = CONTEXTS.mars;
  assert.equal(triage([F(0)], leo).action, 'none');
  assert.equal(triage([F(1)], mars).action, 'remeasure');
  assert.equal(triage([F(2)], leo).action, 'contact_ground');
  assert.equal(triage([F(2)], leo).waitForReply, true);
  const m2 = triage([F(2)], mars);
  assert.equal(m2.action, 'self_treat'); assert.equal(m2.waitForReply, false);
  assert.ok(m2.steps.some(s => s.includes('25 min')));
  assert.equal(triage([F(3)], leo).action, 'contact_ground_now');
  const m3 = triage([F(3)], mars);
  assert.equal(m3.action, 'contact_ground_now'); assert.equal(m3.waitForReply, false);
});

test('triage: persistence escalates warn → alert, except for camera/model sources', () => {
  const t = triage([F(2, { consecutive: 2 })], CONTEXTS.mars);
  assert.equal(t.action, 'contact_ground_now'); assert.deepEqual(t.rulesFired, ['persist.t']);
  const cam = finding('hr', 'cardio', 'camera', 2, 'Kamera-Puls', [], { consecutive: 3 });
  const tc = triage([cam], CONTEXTS.mars);
  assert.equal(tc.action, 'self_treat'); assert.ok(tc.caveats.length === 1);
});

test('triage: deterministic and with reasons', () => {
  const fs = [F(1), finding('hr', 'cardio', 'manual', 2, 'Resting heart rate 104 bpm')];
  const a = triage(fs, CONTEXTS.moon), b = triage(fs, CONTEXTS.moon);
  assert.equal(JSON.stringify(a), JSON.stringify(b));
  assert.deepEqual(a.drivers, ['hr']); assert.ok(a.reasons[0].includes('Resting heart rate 104 bpm'));
  assert.equal(a.disclaimer, 'Decision support, not a diagnosis.');
});

test('summarizeBySystem: worst finding per system, UI status', () => {
  const s = summarizeBySystem([finding('a', 'brain', 'measured', 1, 'a'), finding('b', 'brain', 'measured', 2, 'b'), finding('c', 'cardio', 'manual', 0, 'c')]);
  assert.equal(s.brain.status, 'warn'); assert.equal(s.brain.text, 'b'); assert.equal(s.cardio.status, 'ok');
  assert.equal(uiStatus(3), 'alert');
});

test('PvtSession: flow, false start, timeout, end after 3 min', () => {
  let r = 0; const seq = [0.5, 0.1, 0.9]; const rand = () => seq[r++ % seq.length];
  const s = new PvtSession({ rand }).start(0);                 // erste Wartezeit 1500 ms
  assert.equal(s.tick(1000), null);
  assert.equal(s.press(1100), 'premature');
  assert.equal(s.tick(1500), 'stimulus');
  assert.equal(s.press(1750), 'response');                    // RT 250
  assert.equal(s.tick(2000), null);                           // feedback is showing
  assert.equal(s.tick(2750), 'delay');                        // next wait 300 ms
  assert.equal(s.tick(3050), 'stimulus');
  assert.equal(s.tick(3050 + 30000), 'timeout');
  // skip the rest of the time
  s.tick(3050 + 31000);
  const t = 181000; let ev; for (let i = 0; i < 5 && !s.done; i++) ev = s.tick(t + i * 4000);
  assert.ok(s.done);
  const res = s.result();
  assert.equal(res.responses, 1); assert.equal(res.lapses, 1); assert.equal(res.falseStarts, 1);
});

import { KNOWLEDGE, SOURCES, GAPS, HAZARDS } from '../public/knowledge.mjs';
test('knowledge: every statement has an existing source with an https URL', () => {
  for (const [sys, k] of Object.entries(KNOWLEDGE)) {
    assert.ok(k.facts.length > 0, sys);
    for (const f of k.facts) { assert.ok(f.text.length > 20, sys); assert.ok(SOURCES[f.source], `${sys}: ${f.source}`); }
  }
  for (const [id, s] of Object.entries(SOURCES)) { assert.match(s.url, /^https:\/\//, id); assert.ok(['primary', 'secondary'].includes(s.kind), id); }
  assert.ok(SOURCES[HAZARDS.source]); assert.equal(HAZARDS.list.length, 5);
});
test('knowledge: systems without a card are listed in GAPS instead of invented text', () => {
  const all = ['skeleton', 'cardio', 'lung', 'digest', 'brain', 'muscle'];
  for (const s of all) assert.ok(KNOWLEDGE[s] || GAPS[s], s);
});
test('knowledge: bone figures match the model', () => {
  const txt = KNOWLEDGE.skeleton.facts.map(f => f.text).join(' ');
  assert.match(txt, /1–1\.5 %/); assert.match(txt, /hip about 1\.5 %/); assert.match(txt, /lumbar spine about 1 %/);
  const m = evalBoneModel(1).detail; assert.equal(m.hip, 1.5); assert.equal(m.lumbar, 1);
});

test('PvtSession with trialCount: ends after 5 trials, regardless of time', () => {
  const s = new PvtSession({ trialCount: 5, delayMinMs: 2500, delayMaxMs: 6500, feedbackMs: 1200, rand: () => 0.5 }).start(0);
  let t = 0, n = 0;
  while (!s.done && n++ < 2000) {
    t += 100; const ev = s.tick(t);
    if (ev === 'stimulus') { t += 300; assert.equal(s.press(t), 'response'); }
  }
  assert.ok(s.done); assert.equal(s.trials.length, 5); assert.equal(s.progress(t), 1);
  assert.ok(s.trials.every(x => x.rt === 300));
});

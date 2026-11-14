/* health.mjs — check-in, alertness test (PVT-B inspired) and decision logic for MEDvital/AstroBody.
   Self-contained: builds its own DOM and CSS and only uses window.AstroBody (setVital, setPredictions).
   Everything stays local; storage only in the browser (localStorage). */
import { CONTEXTS, withOneWay, roundTripSec, latencyClass, fmtDuration, Baseline, evalPvt, evalHeartRate, evalBoneModel, triage, uiStatus } from './engine.mjs';
import { PvtSession } from './pvt.mjs';

const $ = id => document.getElementById(id);
const KEY = 'astrobody.health.v1';
const load = () => { try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch { return {}; } };
const save = () => { try { localStorage.setItem(KEY, JSON.stringify({ baseline: baseline.toJSON(), streak, ctxId, marsSec, month })); } catch { /* storage not available */ } };

const saved = load();
const baseline = Baseline.from(saved.baseline);
const streak = saved.streak || {};
let ctxId = CONTEXTS[saved.ctxId] ? saved.ctxId : 'leo';
let marsSec = Number.isFinite(saved.marsSec) ? saved.marsSec : CONTEXTS.mars.oneWaySec;
let month = Number.isFinite(saved.month) ? saved.month : null;
const findings = {};
const ctx = () => (ctxId === 'mars' ? withOneWay(CONTEXTS.mars, marsSec) : CONTEXTS[ctxId]);
const ACTION = { none: 'No finding', remeasure: 'Re-measure', self_treat: 'Self-treat, inform ground',
  contact_ground: 'Contact ground', contact_ground_now: 'Contact ground now' };
const SHORT = ['Normal', 'Slight deviation', 'Elevated', 'Critical'];

/* ---------- DOM ---------- */
function ensureDom() {
  if (!document.querySelector('link[data-hl]')) {
    const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = 'health.css'; l.dataset.hl = '1'; document.head.append(l);
  }
  if ($('hlCheck')) return;
  const wrap = document.createElement('div');
  wrap.innerHTML = `
<div class="overlay" id="hlCheck" hidden>
  <div class="sheet">
    <h2>Check-in</h2>
    <div class="field"><label>Link to Earth <span id="hlLat"></span></label>
      <div class="seg small" id="hlCtx"><button data-ctx="leo">ISS</button><button data-ctx="moon">Moon</button><button data-ctx="mars">Mars</button></div></div>
    <div class="field" id="hlMarsF" hidden><label>One-way light time <span id="hlMarsV"></span></label><input id="hlMars" type="range" min="182" max="1337" value="750"></div>
    <div class="field"><label>Resting heart rate (bpm), entered by hand</label><input id="hlHr" type="number" inputmode="numeric" min="20" max="220" placeholder="e.g. 68"></div>
    <div class="field"><label>Mission month (for the bone model)</label><input id="hlMon" type="number" inputmode="decimal" min="0" max="48" step="0.5" placeholder="e.g. 4"></div>
    <div class="two"><button class="plain" id="hlPvt">Alertness test, 3 min</button><button class="primary" id="hlDone">Done</button></div>
    <button class="plain" id="hlReset" style="height:40px;font-size:14px;color:var(--muted)">Clear baseline</button>
  </div>
</div>
<div class="pvt" id="hlTest" hidden>
  <button class="pvtX" id="hlX" aria-label="Cancel">✕</button>
  <div class="pvtMsg" id="hlMsg"></div>
  <div class="pvtNum" id="hlNum"></div>
  <div class="pvtBar"><i id="hlBar"></i></div>
  <button class="primary pvtClose" id="hlClose" hidden>Close</button>
</div>`;
  while (wrap.firstElementChild) document.body.append(wrap.firstElementChild);
  const open = document.createElement('button'); open.id = 'hlOpen'; open.textContent = 'Check-in';
  const bar = document.querySelector('.bar');
  if (bar) { open.className = 'plain'; bar.append(open); } else { open.className = 'hl-open'; document.body.append(open); }
}

/* ---------- Befunde → MEDvital ---------- */
const hist = k => (baseline.d[k] || []).slice(-14);
function record(f, { count = false } = {}) {
  if (count) streak[f.id] = f.severity >= 2 ? (streak[f.id] || 0) + 1 : 0;
  findings[f.id] = f; save(); render();
}
function render() {
  const AB = window.AstroBody; if (!AB) return;
  const list = Object.values(findings).map(f => ({ ...f, consecutive: streak[f.id] || 0 }));
  if (!list.length) return;                                   // do not overwrite anything until there is a measurement
  const c = ctx(), t = triage(list, c);
  const items = [{ text: ACTION[t.action], note: `${c.label} · round trip ${fmtDuration(roundTripSec(c))} (${{ live: 'real time', delayed: 'delayed', autonomous: 'autonomous' }[latencyClass(c)]})` }];
  if (t.reasons[0]) items.push({ text: t.reasons[0], note: t.caveats[0] || t.disclaimer });
  if (t.steps[0]) items.push({ text: t.steps[0], note: t.steps.slice(1).join(' ') });
  if (findings.bone) items.push({ text: findings.bone.text, note: 'See docs/SOURCES.md' });
  AB.setPredictions(items);
}
function pushVital(id, value, f, text) {
  const AB = window.AstroBody; if (!AB) return;
  AB.setVital(id, { value, status: uiStatus(f.severity), text, history: hist(id === 'hr' ? 'hr.rest' : 'pvt.rt') });
}

/* ---------- Check-in ---------- */
function syncUi() {
  document.querySelectorAll('#hlCtx button').forEach(x => x.classList.toggle('on', x.dataset.ctx === ctxId));
  $('hlMarsF').hidden = ctxId !== 'mars'; $('hlMars').value = marsSec; $('hlMarsV').textContent = fmtDuration(marsSec);
  $('hlLat').textContent = fmtDuration(roundTripSec(ctx())) + ' round trip';
}
function wireCheckin() {
  document.querySelectorAll('#hlCtx button').forEach(x => x.onclick = () => { ctxId = x.dataset.ctx; save(); syncUi(); render(); });
  $('hlMars').oninput = e => { marsSec = +e.target.value; save(); syncUi(); render(); };
  $('hlHr').onchange = e => {
    const bpm = Math.round(+e.target.value); if (!(bpm >= 20 && bpm <= 220)) return;
    const f = evalHeartRate({ bpm, source: 'manual', context: 'rest' }, baseline);
    baseline.add('hr.rest', bpm); record(f, { count: true });
    pushVital('hr', bpm, f, SHORT[f.severity]);
  };
  $('hlMon').onchange = e => {
    const v = e.target.value === '' ? null : +e.target.value; if (v !== null && !(v >= 0 && v <= 48)) return;
    month = v; if (v !== null) record(evalBoneModel(v)); else { delete findings.bone; save(); render(); }
  };
  $('hlReset').onclick = () => { for (const k of Object.keys(baseline.d)) delete baseline.d[k]; for (const k of Object.keys(streak)) delete streak[k]; for (const k of Object.keys(findings)) delete findings[k]; save(); };
  $('hlOpen').onclick = () => { syncUi(); if (month !== null) $('hlMon').value = month; $('hlCheck').hidden = false; };
  $('hlDone').onclick = () => { $('hlCheck').hidden = true; };
  $('hlCheck').onclick = e => { if (e.target === $('hlCheck')) $('hlCheck').hidden = true; };
}

/* ---------- Wachheits-Test ---------- */
let sess = null, raf = 0, armed = false;
const msg = t => { $('hlMsg').textContent = t; }, num = t => { $('hlNum').textContent = t; };
function openTest() {
  $('hlCheck').hidden = true; $('hlTest').hidden = false; sess = null; armed = true; cancelAnimationFrame(raf);
  msg('Tap anywhere as soon as the red number appears. Tap once now to start. Duration: 3 minutes.'); num(''); $('hlBar').style.width = '0'; $('hlClose').hidden = true;
}
function closeTest() { cancelAnimationFrame(raf); sess = null; armed = false; $('hlTest').hidden = true; }
function press(e) {
  if ($('hlTest').hidden || (e.target.closest && e.target.closest('button'))) return;
  const t = e.timeStamp || performance.now();
  if (armed) { armed = false; sess = new PvtSession().start(performance.now()); msg('Waiting for the number …'); loop(); return; }
  if (!sess || sess.done) return;
  const r = sess.press(t);
  if (r === 'response') { num(Math.round(sess.lastRt) + ' ms'); msg(''); }
  if (r === 'premature') msg('Too early. Wait until the number appears.');
}
function loop() {
  const t = performance.now(); const ev = sess.tick(t);
  if (ev === 'stimulus') { msg(''); num('0'); } else if (ev === 'timeout') num('–'); else if (ev === 'delay') num('');
  if (sess.phase === 'stim') num(String(Math.round(t - sess.stimAt)));
  $('hlBar').style.width = (sess.progress(t) * 100).toFixed(1) + '%';
  if (sess.done) return finish();
  raf = requestAnimationFrame(loop);
}
function finish() {
  const res = sess.result();
  const f = evalPvt(res, { baseline, confirmed: (streak.pvt || 0) >= 1 });
  const valid = !f.rules.includes('pvt.invalid');
  if (valid) { baseline.add('pvt.invRt', res.meanInvRt); baseline.add('pvt.rt', Math.round(res.meanRt)); }
  record(f, { count: valid });
  if (valid) pushVital('rt', Math.round(res.meanRt), f, `${res.lapses} lapses · ${SHORT[f.severity]}`);
  num(''); msg(`Done. ${res.lapses} lapses, mean ${Math.round(res.meanRt)} ms, ${res.falseStarts} false starts.` + (valid ? '' : ' Too few valid responses.'));
  $('hlBar').style.width = '100%'; $('hlClose').hidden = false;
}
function wireTest() {
  $('hlPvt').onclick = openTest; $('hlX').onclick = closeTest; $('hlClose').onclick = closeTest;
  $('hlTest').addEventListener('pointerdown', press);
  addEventListener('keydown', e => { if (e.code === 'Space' && !$('hlTest').hidden) { e.preventDefault(); press(e); } });
}

/* ---------- Start ---------- */
for (let i = 0; i < 100 && !window.AstroBody; i++) await new Promise(r => setTimeout(r, 100));
ensureDom(); wireCheckin(); wireTest();
if (month !== null) findings.bone = evalBoneModel(month);
window.AstroHealth = { baseline, findings, streak, get ctx() { return ctx(); }, render };

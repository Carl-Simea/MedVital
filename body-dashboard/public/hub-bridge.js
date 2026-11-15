// Live link from the spacecraft hub to the 3D body: the astronaut's MedVital screen.
// Active only when opened as /body/?astronaut=<id>. Without it the dashboard works on its own, as before.
//
// Every second: all tiles, scores, past data and the 3D heart follow the hub. The astronaut's own buttons
// (Sleep, Leave the spacecraft, Urine test for bone loss, Mood) go to the spacecraft database and on to NASA.
// Alerts take over the screen and buzz. The Demo controls drive the presentation (button or key D).
const id = new URLSearchParams(location.search).get('astronaut');
const $ = s => document.getElementById(s);
const PATTERNS = {
  RETURN_NOW: { vib: [800, 250, 800, 250, 800], text: '3 long buzzes, repeating until you are back inside' },
  CHECK_VITALS: { vib: [180, 120, 180], text: '2 short buzzes' },
  GO_INSIDE: { vib: [300, 150, 300], text: '2 buzzes' },
  CHECK_IN: { vib: [160], text: '1 short buzz' },
  INFO: { vib: [160], text: '1 short buzz' },
};
const TITLES = { RETURN_NOW: 'Return now', CHECK_VITALS: 'Check vitals', GO_INSIDE: 'Go back inside soon', CHECK_IN: 'Check-in', INFO: 'Info' };
const HISTORY_VITALS = ['hr', 'spo2', 'resp', 'temp', 'bp', 'glucose', 'rt', 'sleep', 'pain', 'hgb', 'urine', 'mass', 'rad', 'hip', 'str', 'vitd'];

async function api(path, body) {
  const r = await fetch(path, body === undefined ? { cache: 'no-store' }
    : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || `${path}: HTTP ${r.status}`);
  return data;
}

function el(tag, cls, text) { const n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; }
const hm = min => { const h = Math.floor(min / 60), m = Math.round(min % 60); return h ? `${h} h ${String(m).padStart(2, '0')} min` : `${m} min`; };

// ------------------------------------------------------------------ page furniture added in hub mode
function furnish() {
  const css = el('style');
  css.textContent = `
  .tile[data-vital="hr"] .td{animation:mvbeat var(--beat,1s) infinite}
  .tile[data-vital="hr"] .tv{animation:mvthump var(--beat,1s) infinite;transform-origin:left center}
  @keyframes mvbeat{0%,100%{transform:scale(1)}12%{transform:scale(1.9)}24%{transform:scale(1)}}
  @keyframes mvthump{0%,100%{transform:scale(1)}12%{transform:scale(1.04)}}
  @media (prefers-reduced-motion: reduce){.tile[data-vital="hr"] .td,.tile[data-vital="hr"] .tv,.mv-alert.RETURN_NOW{animation:none}}
  .mv-clock{font-variant-numeric:tabular-nums}
  .mv-acts{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-top:8px}
  .mv-acts button{min-height:46px;border-radius:12px;background:var(--fill);color:var(--ink);font-weight:600;font-size:14px;line-height:1.15;padding:6px 8px}
  .mv-acts button.on{background:var(--brand-teal,#126f70);color:#fff}
  .mv-acts button.out{background:#b4561c;color:#fff}
  .mv-acts button:disabled{opacity:.45}
  .mv-eva{margin-top:8px;padding:10px 12px;border-radius:12px;background:#fff1e6;color:#5c2a00;font-size:14px;display:flex;gap:10px;align-items:center}
  .mv-eva[hidden]{display:none}
  .mv-eva b{font-variant-numeric:tabular-nums}
  .mv-eva .cd{margin-left:auto;font-size:22px;font-weight:800;min-width:2.4ch;text-align:right;font-variant-numeric:tabular-nums;color:#b4561c}
  .mv-log{margin-top:10px;font-size:13px}
  .mv-log h4{margin:0 0 4px;font-size:13px;color:var(--muted)}
  .mv-log ul{list-style:none;margin:0;padding:0}.mv-log li{padding:4px 0;border-top:1px solid var(--line,rgba(127,127,127,.2))}
  .mv-alert{position:fixed;inset:0;z-index:90;display:grid;place-items:center;padding:24px;color:#fff;background:var(--a);text-align:center}
  .mv-alert[hidden]{display:none}
  .mv-alert.RETURN_NOW{--a:#d62828;animation:mvpulse 1.1s ease-in-out infinite}
  .mv-alert.CHECK_VITALS{--a:#e8730c}
  .mv-alert.INFO,.mv-alert.CHECK_IN,.mv-alert.GO_INSIDE{--a:#2768d8;inset:auto 18px 18px auto;max-width:460px;border-radius:14px;place-items:start;text-align:left;box-shadow:0 10px 30px rgba(0,0,0,.4)}
  .mv-alert.GO_INSIDE{--a:#b4561c}
  @keyframes mvpulse{50%{background:#8f1414}}
  .mv-alert .c{font-size:clamp(50px,10vw,128px);font-weight:800;line-height:.95;margin:0}
  .mv-alert.INFO .c,.mv-alert.CHECK_IN .c,.mv-alert.GO_INSIDE .c{font-size:26px}
  .mv-alert .m{font-size:clamp(19px,2.4vw,30px);line-height:1.35;margin:16px 0;max-width:820px}
  .mv-alert.INFO .m,.mv-alert.CHECK_IN .m,.mv-alert.GO_INSIDE .m{font-size:17px;margin:6px 0}
  .mv-alert .p{opacity:.85;margin:0 0 18px}
  .mv-alert button{padding:12px 30px;border:3px solid #fff;background:transparent;color:#fff;font-size:20px;font-weight:700;border-radius:999px;cursor:pointer}
  .mv-alert.INFO button,.mv-alert.CHECK_IN button,.mv-alert.GO_INSIDE button{font-size:15px;padding:6px 16px;border-width:2px}
  .mv-sheet{position:fixed;inset:0;z-index:85;background:rgba(0,0,0,.45);display:grid;place-items:center;padding:16px}
  .mv-sheet[hidden]{display:none}
  .mv-sheet form{background:var(--card,#fff);color:var(--ink);border-radius:16px;padding:20px;width:min(520px,100%);max-height:90vh;overflow:auto}
  .mv-sheet h2{margin:0 0 4px;font-size:20px}.mv-sheet p{margin:0 0 12px;font-size:13px;color:var(--muted)}
  .mv-sheet label{display:grid;grid-template-columns:1fr 130px;align-items:center;gap:10px;padding:6px 0;font-size:14px;border-top:1px solid var(--line,rgba(127,127,127,.2))}
  .mv-sheet input{font:inherit;padding:7px 9px;border-radius:8px;border:1px solid rgba(127,127,127,.4);background:transparent;color:inherit;width:100%}
  .mv-sheet .row{display:flex;gap:8px;margin-top:14px}.mv-sheet .row button{flex:1;height:44px;border-radius:12px;font-weight:600}
  .mv-sheet .mood{display:grid;grid-template-columns:repeat(5,1fr);gap:6px}
  .mv-sheet .mood button{height:56px;border-radius:12px;background:var(--fill);font-size:20px;font-weight:700;color:var(--ink)}
  .mv-sheet .scale{display:flex;justify-content:space-between;font-size:12px;color:var(--muted);margin-top:4px}
  .mv-sheet .msg{min-height:1.2em;font-size:13px;margin-top:8px}
  .mv-demobtn{position:fixed;left:18px;bottom:18px;z-index:79;padding:9px 14px;border-radius:999px;background:var(--card,#1c1c1e);color:var(--ink);font-weight:600;font-size:13px;box-shadow:0 6px 18px rgba(0,0,0,.3);border:1px solid rgba(127,127,127,.3)}
  .mv-demo{position:fixed;left:18px;bottom:64px;z-index:80;background:var(--card,#1c1c1e);color:var(--ink,#fff);border-radius:14px;padding:14px;box-shadow:0 10px 30px rgba(0,0,0,.45);width:310px}
  .mv-demo[hidden]{display:none}
  .mv-demo h3{margin:0 0 4px;font-size:15px}.mv-demo p{margin:0 0 10px;font-size:12px;opacity:.7}
  .mv-demo .g{display:grid;grid-template-columns:1fr 1fr;gap:6px}
  .mv-demo button,.mv-demo input{padding:8px;border-radius:9px;border:1px solid rgba(127,127,127,.35);background:transparent;color:inherit;font:inherit;font-size:13px}
  .mv-demo button{cursor:pointer}.mv-demo button.on{background:#0a84ff;border-color:#0a84ff;color:#fff}
  .mv-demo .skip{display:grid;grid-template-columns:1fr 70px auto;gap:6px;margin-top:8px}
  .mv-demo .msg{min-height:1.2em;font-size:12px;margin-top:8px;opacity:.8}`;
  document.head.append(css);

  // Alert overlay
  const ov = el('div', 'mv-alert'); ov.hidden = true; ov.setAttribute('role', 'alertdialog');
  ov.append(el('p', 'c'), el('p', 'm'), el('p', 'p'), el('button', '', 'OK'));
  document.body.append(ov);

  // The astronaut's own buttons, under the body
  const bar = document.querySelector('.col.center .bar') || $('seg').parentNode;
  const acts = el('div', 'mv-acts');
  const sleepBtn = el('button', '', 'Sleep'), evaBtn = el('button', '', 'Leave the spacecraft');
  const urineBtn = el('button', '', 'Urine test (bone loss)'), moodBtn = el('button', '', 'Mood check-in');
  acts.append(sleepBtn, evaBtn, urineBtn, moodBtn);
  const evaBox = el('div', 'mv-eva'); evaBox.hidden = true; evaBox.setAttribute('role', 'status');
  bar.after(acts); acts.after(evaBox);
  sleepBtn.onclick = () => act(`/hub/astronauts/${encodeURIComponent(id)}/sleep`, { asleep: !state.asleep });
  evaBtn.onclick = () => act(`/hub/astronauts/${encodeURIComponent(id)}/eva`, { outside: !state.outside });
  urineBtn.onclick = () => openUrine();
  moodBtn.onclick = () => { ui.mood.hidden = false; };

  // Spacewalk log, under past data
  const log = el('div', 'mv-log'); log.append(el('h4', '', 'Spacewalks'), el('ul'));
  ($('stats') || $('chart')).after(log);

  // Urine test form (NASA's bone-loss urine panel; values as measured, no "normal" labels)
  const urine = el('div', 'mv-sheet'); urine.hidden = true;
  const uf = el('form'); uf.append(el('h2', '', 'Urine test for bone loss'),
    el('p', '', '24-hour urine collection. Enter what the analyser shows; leave blank what was not measured. Saved to the spacecraft and sent to NASA.'));
  const ufields = el('div'), umsg = el('div', 'msg');
  const urow = el('div', 'row'); const ucancel = el('button', '', 'Cancel'); ucancel.type = 'button'; const usave = el('button', 'primary', 'Save results');
  urow.append(ucancel, usave); uf.append(ufields, urow, umsg); urine.append(uf); document.body.append(urine);
  ucancel.onclick = () => { urine.hidden = true; };
  uf.onsubmit = async e => {
    e.preventDefault();
    const values = {};
    for (const i of ufields.querySelectorAll('input')) if (i.value !== '') values[i.name] = Number(i.value);
    if (!Object.keys(values).length) { umsg.textContent = 'Enter at least one result.'; return; }
    try { await api(`/hub/labs/${encodeURIComponent(id)}`, values); umsg.textContent = 'Saved. NASA gets it with the day-end batch.';
      setTimeout(() => { urine.hidden = true; umsg.textContent = ''; uf.reset(); }, 1200); }
    catch (err) { umsg.textContent = err.message; }
  };

  // Mood check-in
  const mood = el('div', 'mv-sheet'); mood.hidden = true;
  const mf = el('form'); mf.append(el('h2', '', 'How do you feel today?'), el('p', '', 'One tap. Together with your sleep it helps the flight surgeon know when to check in.'));
  const mg = el('div', 'mood'), mmsg = el('div', 'msg');
  for (let n = 1; n <= 5; n++) { const b = el('button', '', String(n)); b.type = 'button';
    b.onclick = async () => { try { await api(`/hub/astronauts/${encodeURIComponent(id)}/mood`, { score: n }); mmsg.textContent = `Saved: ${n} of 5.`;
      setTimeout(() => { mood.hidden = true; mmsg.textContent = ''; }, 900); } catch (err) { mmsg.textContent = err.message; } };
    mg.append(b); }
  const sc = el('div', 'scale'); sc.append(el('span', '', '1 very low'), el('span', '', '5 very good'));
  const mrow = el('div', 'row'); const mcancel = el('button', '', 'Close'); mcancel.type = 'button'; mcancel.onclick = () => { mood.hidden = true; };
  mrow.append(mcancel); mf.append(mg, sc, mrow, mmsg); mood.append(mf); document.body.append(mood);
  for (const s of [urine, mood]) s.addEventListener('click', e => { if (e.target === s) s.hidden = true; });

  // Demo controls (visible button; key D also toggles)
  const db = el('button', 'mv-demobtn', 'Demo controls');
  const dr = el('div', 'mv-demo'); dr.hidden = true;
  dr.append(el('h3', '', 'Demo controls'), el('p', '', 'For the presentation. Key D shows or hides this.'));
  const g = el('div', 'g');
  for (const [a, label] of [['auto', 'Follow the plan'], ['exercise', 'Exercise now'], ['hr_spike', 'Heart-rate spike'], ['solar', 'Solar event'],
    ['glitch', 'Sensor glitch'], ['fake', 'Fake device'], ['wear', 'Take off wearable'], ['summary', 'Write day summary']]) {
    const b = el('button', '', label); b.dataset.act = a; b.onclick = () => demo(a, b); g.append(b);
  }
  const skip = el('div', 'skip');
  const toSolar = el('button', '', 'Skip to 2 h before the next solar event'); toSolar.style.gridColumn = '1 / -1';
  const dayIn = el('input'); dayIn.type = 'number'; dayIn.min = '1'; dayIn.placeholder = 'day'; dayIn.setAttribute('aria-label', 'Mission day');
  const toDay = el('button', '', 'Jump');
  skip.append(toSolar, el('span', '', 'Jump to mission day'), dayIn, toDay);
  toSolar.onclick = () => skipTo({ to: 'solar' });
  toDay.onclick = () => skipTo({ to: 'day', day: Number(dayIn.value) });
  dr.append(g, skip, el('div', 'msg')); document.body.append(db, dr);
  db.onclick = () => { dr.hidden = !dr.hidden; };
  document.addEventListener('keydown', e => { if (e.target.closest('input,textarea')) return; if (e.key.toLowerCase() === 'd') dr.hidden = !dr.hidden; });

  return { ov, dr, sleepBtn, evaBtn, evaBox, log, urine, ufields, mood };
}

let ui, worn = true, shown = null, audio = null;
const state = { asleep: false, outside: false, urinePanel: [] };
const unlock = () => { try { audio = audio || new AudioContext(); audio.resume(); } catch { audio = null; } };
document.addEventListener('pointerdown', unlock, { once: true });
function beep(p) {
  if (!audio) return; let t = audio.currentTime;
  p.forEach((ms, i) => { if (i % 2 === 0) { const o = audio.createOscillator(), g = audio.createGain(); o.frequency.value = p.length > 3 ? 660 : 880;
    g.gain.setValueAtTime(.15, t); g.gain.setValueAtTime(0, t + ms / 1000); o.connect(g).connect(audio.destination); o.start(t); o.stop(t + ms / 1000); } t += ms / 1000; });
}

async function act(path, body) {
  try { await api(path, body); } catch (e) { flash(e.message); }
  if (window.AstroBody) pull(window.AstroBody);
}
function flash(text) { const s = $('sSub'); if (s) { s.textContent = text; } }

function openUrine() {
  const f = ui.ufields; f.replaceChildren();
  for (const p of state.urinePanel) {
    const l = el('label'); const i = el('input'); i.name = p.key; i.type = 'number'; i.step = 'any'; i.min = '0';
    l.append(el('span', '', `${p.label} (${p.unit})`), i); f.append(l);
  }
  ui.urine.hidden = false;
}

async function demo(a, btn) {
  const msg = ui.dr.querySelector('.msg');
  try {
    const body = a === 'wear' ? { action: 'wear', on: !worn } : { action: a };
    const r = await api(`/hub/demo/${encodeURIComponent(id)}`, body);
    if (a === 'wear') { worn = r.worn; btn.textContent = worn ? 'Take off wearable' : 'Put on wearable'; }
    ui.dr.querySelectorAll('button[data-act]').forEach(b => b.classList.toggle('on', b.dataset.act === r.scenario && r.scenario !== 'auto'));
    msg.textContent = a === 'fake' ? (r.blocked ? 'Fake device blocked by the private network.' : 'The fake got through?!')
      : a === 'solar' ? `Replayed ${r.event} from NASA DONKI.` : a === 'summary' ? 'Daily summary written.' : 'Done.';
  } catch (e) { msg.textContent = e.message; }
}
async function skipTo(body) {
  const msg = ui.dr.querySelector('.msg');
  try { const r = await api('/hub/skip', body); msg.textContent = `Now ${r.now}: ${r.what}.`; } catch (e) { msg.textContent = e.message; }
}

function showAlert(a) {
  const p = PATTERNS[a.code] || PATTERNS.INFO;
  if (navigator.vibrate) navigator.vibrate(p.vib);
  beep(p.vib);
  if (shown === a.id) return;   // dismissed: RETURN_NOW keeps buzzing but does not cover the screen again
  shown = a.id;
  const ov = ui.ov; ov.className = 'mv-alert ' + (PATTERNS[a.code] ? a.code : 'INFO');
  ov.querySelector('.c').textContent = TITLES[a.code] || a.code;
  ov.querySelector('.m').textContent = a.ai_message || a.message;
  ov.querySelector('.p').textContent = `Wearable: ${p.text}`;
  const b = ov.querySelector('button');
  const goIn = a.code === 'RETURN_NOW' || a.code === 'GO_INSIDE';
  b.textContent = goIn ? 'Go back inside' : 'OK';
  b.onclick = () => {
    ov.hidden = true;
    if (a.code === 'GO_INSIDE') act(`/hub/astronauts/${encodeURIComponent(id)}/eva`, { outside: false });
    api(`/hub/alerts/${encodeURIComponent(a.id)}/ack`, {}).catch(() => {});
  };
  ov.hidden = false;
  if (a.code === 'INFO' || a.code === 'CHECK_IN') setTimeout(() => { if (shown === a.id) ov.hidden = true; }, 6000);
}

function drawButtons(d) {
  state.asleep = d.sleeping !== null && d.sleeping !== undefined;
  state.outside = !!d.eva;
  state.urinePanel = d.urinePanel || [];
  ui.sleepBtn.textContent = state.asleep ? `Wake up (${d.sleeping} h)` : 'Sleep';
  ui.sleepBtn.classList.toggle('on', state.asleep);
  ui.sleepBtn.disabled = state.outside;
  ui.evaBtn.textContent = state.outside ? 'Go back inside' : 'Leave the spacecraft';
  ui.evaBtn.classList.toggle('out', state.outside);
  ui.evaBtn.disabled = state.asleep;
  const e = d.eva, box = ui.evaBox;
  if (!e) { box.hidden = true; return; }
  box.hidden = false;
  const parts = [el('span', '', 'Outside since '), el('b', '', e.since), el('span', '', ` · ${hm(e.minutes)} · ${e.doseMsv.toFixed(3)} mSv received`)];
  if (e.solarMinutes) parts.push(el('span', '', ` · ${hm(e.solarMinutes)} during a solar event`));
  if (e.warning) {
    parts.push(el('span', '', ` · Upcoming: ${e.warning.event} at ${e.warning.when}. Inside by ${e.warning.deadline}.`));
    parts.push(el('span', 'cd', `${Math.ceil(e.warning.secondsLeft)}s`));
  }
  box.replaceChildren(...parts);
}

function drawUpcoming(AB, d) {
  const env = [];
  if (d.alert && d.alert.status === 'active' && !['INFO', 'CHECK_IN'].includes(d.alert.code)) env.push({ text: `${TITLES[d.alert.code] || d.alert.code}: ${d.alert.message}`, note: 'Active alert' });
  env.push({ text: `Radiation now ${d.doseRate?.toFixed(1) ?? '–'} µSv/h`, note: d.radRef ? `Curiosity RAD ${d.radRef.replace('RAD ', '')}` : 'Curiosity RAD' });
  // space weather on the mission calendar: mission time, the real date, and the duration only when NASA reports one
  for (const e of d.spaceWeather.slice(0, 4)) {
    const dur = e.durationMin ? `lasted ${hm(e.durationMin)}` : (e.durationNote || '');
    env.push({ text: `${e.title} · ${e.when}`, note: `${e.utc || ''} · ${dur} · ${e.source}` });
  }
  const live = (d.liveSpaceWeather || [])[0];
  if (live) env.push({ text: `Live now: ${live.summary}`, note: `${live.event_time.replace('T', ' ').replace('Z', ' UTC')} · ${live.source}` });
  AB.setEnvironment(env);
  AB.setPredictions(d.upcoming.filter(e => e.kind !== 'space_weather').slice(0, 5)
    .map(e => ({ text: `${e.title} · ${e.when}`, note: e.realSeconds > 0 ? `in ${Math.round(e.realSeconds)} s (demo time)` : 'now' })));
  const ul = ui.log.querySelector('ul');
  const rows = (d.evaLog || []).filter(e => e.status === 'done' || e.detail);
  ul.replaceChildren(...(rows.length ? rows.slice(0, 4).map(e => el('li', '', `${e.when}: ${e.detail || e.title}`)) : [el('li', '', 'No spacewalks yet.')]));
}

// ------------------------------------------------------------------ the live loop
const seen = new Set();
let first = true;
async function pull(AB) {
  let d;
  try { d = await api(`/hub/body/${encodeURIComponent(id)}`); }
  catch { $('sSub').textContent = 'Spacecraft unreachable · showing last data'; return; }
  const name = $('crewName'); if (name && document.activeElement !== name) name.value = d.name;
  const c = d.clock;
  $('sSub').textContent = `Mission day ${c.day} · ${c.time} · ${c.phaseLabel}` + (c.sepActive ? ' · solar event' : '') + (c.blackout ? ' · link blackout' : '');
  $('sSub').classList.add('mv-clock');

  const sample = $('sampleChip') && !$('sampleChip').hidden;   // "Load sample data" pauses the live tiles
  if (!sample) {
    const values = { ...d.values };
    if (d.sleeping !== null && d.sleeping !== undefined) values['sleep.hours'] = d.sleeping;   // the sleep tile counts the hours
    AB.setMeasurements(values);
    for (const v of HISTORY_VITALS) {
      const h = (d.history[v] || []).filter(x => x !== null && x !== undefined);
      if (h.length) AB.setVital(v, v === 'hr' ? { value: d.values['hr.rest'], history: h } : { history: h });
    }
    drawUpcoming(AB, d);
  }
  const bpm = d.values['hr.rest'];
  if (bpm) $('tiles').style.setProperty('--beat', `${(60 / bpm).toFixed(2)}s`);
  drawButtons(d);

  const a = d.alert;
  if (a && (a.status === 'active' || a.status === 'delivered')) {
    if (first) seen.add(a.id);   // do not replay old alerts when the page opens
    else if (!seen.has(a.id) || (a.code === 'RETURN_NOW' && a.status === 'active')) { seen.add(a.id); showAlert(a); }
  }
  if (a && a.id === shown && a.status === 'resolved') ui.ov.hidden = true;
  if (a && a.id === shown && a.code === 'GO_INSIDE' && !d.eva) ui.ov.hidden = true;
  if (d.device) worn = d.device.worn;
  first = false;
}

async function waitForApi() {
  for (let i = 0; i < 200 && !window.AstroBody; i++) await new Promise(r => setTimeout(r, 100));
  return window.AstroBody;
}

if (id) {
  ui = furnish();
  // Past data: live vitals are readings (one per second = 24 mission minutes); the rest are test results.
  window.MedVitalHistoryLabel = (vid, n) => ['hr', 'spo2', 'resp', 'temp', 'rad'].includes(vid)
    ? `last ${n} readings (${Math.round(n * 24 / 60)} mission hours)` : `last ${n} results`;
  // The Assistant tab asks the spacecraft's onboard AI agent (the hub screen draws the question's path).
  window.MedVitalAsk = q => api(`/hub/agent/${encodeURIComponent(id)}`, { question: q });
  // Values typed or pasted into "Data input" go to the spacecraft database (and on to NASA).
  window.addEventListener('medvital:applied', async e => {
    try { await api(`/hub/labs/${encodeURIComponent(id)}`, e.detail); }
    catch (err) { console.warn('could not save to the spacecraft', err); }
  });
  waitForApi().then(AB => { if (!AB) return; pull(AB); setInterval(() => pull(AB), 1000); });
}

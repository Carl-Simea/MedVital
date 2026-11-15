// Live link from the spacecraft hub to the 3D body: the astronaut's MedVital screen.
// Active only when opened as /body/?astronaut=<id>. Without it the dashboard works on its own, as before.
//
// Every second: all tiles, scores, past data and the 3D heart follow the hub. Alerts take over the screen
// and buzz. Values typed into "Data input" go to the spacecraft database. A hidden Demo drawer (key D)
// drives the presentation.
const id = new URLSearchParams(location.search).get('astronaut');
const $ = s => document.getElementById(s);
const PATTERNS = {
  RETURN_NOW: { vib: [800, 250, 800, 250, 800], text: '3 long buzzes, repeating until you are back inside' },
  CHECK_VITALS: { vib: [180, 120, 180], text: '2 short buzzes' },
  INFO: { vib: [160], text: '1 short buzz' },
};
const HISTORY_VITALS = ['hr', 'spo2', 'resp', 'temp', 'bp', 'glucose', 'rt', 'sleep', 'pain', 'hgb', 'urine', 'mass', 'rad', 'hip', 'str', 'vitd'];

async function api(path, body) {
  const r = await fetch(path, body === undefined ? { cache: 'no-store' }
    : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return r.json();
}

function el(tag, cls, text) { const n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; }

// ------------------------------------------------------------------ page furniture added in hub mode
function furnish() {
  const css = el('style');
  css.textContent = `
  .tile[data-vital="hr"] .td{animation:mvbeat var(--beat,1s) infinite}
  .tile[data-vital="hr"] .tv{animation:mvthump var(--beat,1s) infinite;transform-origin:left center}
  @keyframes mvbeat{0%,100%{transform:scale(1)}12%{transform:scale(1.9)}24%{transform:scale(1)}}
  @keyframes mvthump{0%,100%{transform:scale(1)}12%{transform:scale(1.04)}}
  .mv-clock{font-variant-numeric:tabular-nums}
  .mv-alert{position:fixed;inset:0;z-index:90;display:grid;place-items:center;padding:24px;color:#fff;background:var(--a);text-align:center}
  .mv-alert[hidden]{display:none}
  .mv-alert.RETURN_NOW{--a:#d62828;animation:mvpulse 1.1s ease-in-out infinite}
  .mv-alert.CHECK_VITALS{--a:#e8730c}
  .mv-alert.INFO{--a:#2768d8;inset:auto 18px 18px auto;max-width:440px;border-radius:14px;place-items:start;text-align:left;box-shadow:0 10px 30px rgba(0,0,0,.4)}
  @keyframes mvpulse{50%{background:#8f1414}}
  .mv-alert .c{font-size:clamp(50px,10vw,128px);font-weight:800;line-height:.95;margin:0}
  .mv-alert.INFO .c{font-size:28px}
  .mv-alert .m{font-size:clamp(19px,2.4vw,30px);line-height:1.35;margin:16px 0;max-width:820px}
  .mv-alert.INFO .m{font-size:17px;margin:6px 0}
  .mv-alert .p{opacity:.85;margin:0 0 18px}
  .mv-alert button{padding:12px 30px;border:3px solid #fff;background:transparent;color:#fff;font-size:20px;font-weight:700;border-radius:999px;cursor:pointer}
  .mv-alert.INFO button{font-size:15px;padding:5px 16px;border-width:2px}
  .mv-demo{position:fixed;left:18px;bottom:18px;z-index:80;background:var(--card,#1c1c1e);color:var(--ink,#fff);border-radius:14px;padding:14px;box-shadow:0 10px 30px rgba(0,0,0,.45);width:300px}
  .mv-demo[hidden]{display:none}
  .mv-demo h3{margin:0 0 4px;font-size:15px}.mv-demo p{margin:0 0 10px;font-size:12px;opacity:.7}
  .mv-demo .g{display:grid;grid-template-columns:1fr 1fr;gap:6px}
  .mv-demo button{padding:8px;border-radius:9px;border:1px solid rgba(127,127,127,.35);background:transparent;color:inherit;font:inherit;font-size:13px;cursor:pointer}
  .mv-demo button.on{background:#0a84ff;border-color:#0a84ff;color:#fff}
  .mv-demo .msg{min-height:1.2em;font-size:12px;margin-top:8px;opacity:.8}`;
  document.head.append(css);

  // Alert overlay
  const ov = el('div', 'mv-alert'); ov.hidden = true; ov.setAttribute('role', 'alertdialog');
  ov.append(el('p', 'c'), el('p', 'm'), el('p', 'p'), el('button', '', 'OK'));
  document.body.append(ov);

  // Demo drawer (hidden; key D or the bottom button)
  const dr = el('div', 'mv-demo'); dr.hidden = true;
  dr.append(el('h3', '', 'Demo controls'), el('p', '', 'For the presentation only. Key D shows or hides this.'));
  const g = el('div', 'g');
  for (const [act, label] of [['auto', 'Follow the plan'], ['spacewalk', 'Spacewalk now'], ['exercise', 'Exercise now'], ['sleep', 'Sleep now'],
    ['hr_spike', 'Heart-rate spike'], ['solar', 'Solar event'], ['glitch', 'Sensor glitch'], ['fake', 'Fake device'],
    ['wear', 'Take off wearable'], ['summary', 'Write day summary']]) {
    const b = el('button', '', label); b.dataset.act = act; b.onclick = () => demo(act, b); g.append(b);
  }
  dr.append(g, el('div', 'msg')); document.body.append(dr);
  document.addEventListener('keydown', e => { if (e.target.closest('input,textarea')) return; if (e.key.toLowerCase() === 'd') dr.hidden = !dr.hidden; });

  // "Load sample data" makes no sense with live data: the button opens the demo drawer instead
  const sb = $('sampleBtn'); if (sb) { sb.textContent = 'Live from the spacecraft'; sb.onclick = () => { dr.hidden = !dr.hidden; }; }
  return { ov, dr };
}

let ui, worn = true, shown = null, audio = null;
const unlock = () => { try { audio = audio || new AudioContext(); audio.resume(); } catch { audio = null; } };
document.addEventListener('pointerdown', unlock, { once: true });
function beep(p) {
  if (!audio) return; let t = audio.currentTime;
  p.forEach((ms, i) => { if (i % 2 === 0) { const o = audio.createOscillator(), g = audio.createGain(); o.frequency.value = p.length > 3 ? 660 : 880;
    g.gain.setValueAtTime(.15, t); g.gain.setValueAtTime(0, t + ms / 1000); o.connect(g).connect(audio.destination); o.start(t); o.stop(t + ms / 1000); } t += ms / 1000; });
}

async function demo(act, btn) {
  const msg = ui.dr.querySelector('.msg');
  try {
    const body = act === 'wear' ? { action: 'wear', on: !worn } : { action: act };
    const r = await api(`/hub/demo/${encodeURIComponent(id)}`, body);
    if (act === 'wear') { worn = r.worn; btn.textContent = worn ? 'Take off wearable' : 'Put on wearable'; }
    ui.dr.querySelectorAll('button[data-act]').forEach(b => b.classList.toggle('on', b.dataset.act === r.scenario && r.scenario !== 'auto'));
    msg.textContent = act === 'fake' ? (r.blocked ? 'Fake device blocked by the private network.' : 'The fake got through?!')
      : act === 'solar' ? `Replayed ${r.event} from NASA DONKI.` : act === 'summary' ? 'Daily summary written.' : 'Done.';
  } catch (e) { msg.textContent = e.message; }
}

function showAlert(a) {
  const p = PATTERNS[a.code] || PATTERNS.INFO;
  if (navigator.vibrate) navigator.vibrate(p.vib);
  beep(p.vib);
  if (shown === a.id && !ui.ov.hidden) return;
  if (shown === a.id) return;   // dismissed: RETURN_NOW keeps buzzing but does not cover the screen again
  shown = a.id;
  const ov = ui.ov; ov.className = 'mv-alert ' + a.code;
  ov.querySelector('.c').textContent = a.code.replace('_', ' ');
  ov.querySelector('.m').textContent = a.ai_message || a.message;
  ov.querySelector('.p').textContent = `Wearable: ${p.text}`;
  const b = ov.querySelector('button'); b.textContent = a.code === 'RETURN_NOW' ? 'Heading back inside' : 'OK';
  b.onclick = () => { ov.hidden = true; api(`/hub/alerts/${encodeURIComponent(a.id)}/ack`, {}).catch(() => {}); };
  ov.hidden = false;
  if (a.code === 'INFO') setTimeout(() => { if (shown === a.id) ov.hidden = true; }, 5000);
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

  AB.setMeasurements(d.values);
  for (const v of HISTORY_VITALS) {
    const h = (d.history[v] || []).filter(x => x !== null && x !== undefined);
    if (h.length) AB.setVital(v, v === 'hr' ? { value: d.values['hr.rest'], history: h } : { history: h });
  }
  const bpm = d.values['hr.rest'];
  if (bpm) $('tiles').style.setProperty('--beat', `${(60 / bpm).toFixed(2)}s`);

  const env = [];
  if (d.alert && d.alert.status === 'active' && d.alert.code !== 'INFO') env.push({ text: `${d.alert.code}: ${d.alert.message}`, note: 'Active alert' });
  env.push({ text: `Radiation now ${d.doseRate?.toFixed(1) ?? '–'} µSv/h`, note: d.radRef ? `Curiosity RAD ${d.radRef.replace('RAD ', '')}` : 'Curiosity RAD' });
  for (const e of d.spaceWeather.slice(0, 3)) env.push({ text: `${e.title} · ${e.when}`, note: e.source });
  AB.setEnvironment(env);
  AB.setPredictions(d.upcoming.slice(0, 5).map(e => ({ text: `${e.title} · ${e.when}`, note: e.realSeconds > 0 ? `in ${Math.round(e.realSeconds)} s (demo time)` : 'now' })));

  const a = d.alert;
  if (a && (a.status === 'active' || a.status === 'delivered')) {
    if (first) seen.add(a.id);   // do not replay old alerts when the page opens
    else if (!seen.has(a.id) || (a.code === 'RETURN_NOW' && a.status === 'active')) { seen.add(a.id); showAlert(a); }
  }
  if (a && a.id === shown && a.status === 'resolved') ui.ov.hidden = true;
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
  // Values typed or pasted into "Data input" go to the spacecraft database (and on to NASA).
  window.addEventListener('medvital:applied', async e => {
    try { await api(`/hub/labs/${encodeURIComponent(id)}`, e.detail); }
    catch (err) { console.warn('could not save to the spacecraft', err); }
  });
  waitForApi().then(AB => { if (!AB) return; pull(AB); setInterval(() => pull(AB), 1000); });
}

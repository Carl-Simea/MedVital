import { createLobby } from './lobby.js';
import { PARTS, PAIRED, SRC, BASIS, LEVEL, LEVEL_NAME, LEVEL_LABEL, INDICATORS, evaluate, bodyColors, summarize } from './parts.mjs';
import { answer as assistantAnswer, SUGGESTIONS } from './assistant.mjs';
import { DOMAIN_IDS, SCORE_KEYS, SCORE_SRC, SCORE_INPUTS, scoreAll, scoreColor, scoreWord } from './scores.mjs';
import { extract, READABLE } from './intake.mjs';
import { SCENARIOS, SCENARIO_IDS, reportText } from './testdata.mjs';
import { createLive, ACTIVITIES, ACTIVITY_IDS } from './live.mjs';
const ALL_SRC = { ...SRC, ...SCORE_SRC };

const BUILD = 'v3.8 · 14 Nov 2026';
const errLog = [];
const logErr = m => { errLog.push(new Date().toISOString().slice(11, 19) + ' ' + String(m).slice(0, 200)); if (errLog.length > 20) errLog.shift(); };
addEventListener('error', e => logErr(e.message + ' @' + (e.filename || '').split('/').pop() + ':' + e.lineno));
addEventListener('unhandledrejection', e => logErr('promise: ' + (e.reason && e.reason.message || e.reason)));

const $ = id => document.getElementById(id);
const state = { vital: 'hr', look: 'solid', layer: 'bone', sample: false, sel: null };
let M = {};                                  // current measurements (keys of INDICATORS)
const body = { heightCm: null, massKg: null, sex: null };   // profile: stretches the model, sex also sets reference ranges
let parts = evaluate({});                    // evaluated state per anatomy group
let lobby = null;

/* ---------- Header ---------- */
const setSub = t => { $('sSub').textContent = t; };
const setDot = c => { $('dot').className = 'dot ' + (c || ''); };
const nameEl = $('crewName');
try { const n = localStorage.getItem('medvital.crew'); if (n) nameEl.value = n; } catch (e) {}
nameEl.oninput = () => { try { localStorage.setItem('medvital.crew', nameEl.value); } catch (e) {} };
nameEl.onkeydown = e => { if (e.key === 'Enter') nameEl.blur(); };
const tick = () => { $('clock').textContent = new Date().toLocaleString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }); }; tick(); setInterval(tick, 10000);

/* ---------- Evaluation ---------- */
const extFindings = () => {
  const F = (window.AstroHealth && window.AstroHealth.findings) || {};
  return { F, ext: { hr: F.hr || null, pvt: F.pvt || null, bone: F.bone || null } };
};
function currentInput() {
  const { F } = extFindings(), In = { ...M };
  if (body.sex && In.sex === undefined) In.sex = body.sex;
  if (In['pvt.lapses'] === undefined && F.pvt && F.pvt.score && typeof F.pvt.score.lapses === 'number') In['pvt.lapses'] = F.pvt.score.lapses;
  if (In['mission.month'] === undefined && F.bone && F.bone.detail) In['mission.month'] = F.bone.detail.avg[0];
  return In;
}
const manual = {};                           // legacy overrides from setGroupStatus / setSystemStatus
function recompute(light) {
  const { ext } = extFindings();
  // The engine's bone model is a reminder for weight-bearing sites only, not for every bone
  const boneExt = ext.bone ? { ...ext.bone } : null;
  parts = evaluate(currentInput(), { ...ext, bone: null });
  if (boneExt) for (const g of ['pelvis', 'femur', 'spineL']) {
    const s = parts[g]; if (s.level < 1 && !s.warnings.some(w => w.rule.startsWith('bmd:'))) {
      s.warnings.push({ rule: 'engine:bone', level: 1, text: boneExt.text, basis: 'model', src: 'boneER2017', key: 'bmd.wholeBodyPct' });
      s.level = 1; s.status = 'watch'; s.statusLabel = LEVEL_LABEL[1];
    }
  }
  for (const g in manual) if (parts[g] && LEVEL[manual[g]] > parts[g].level) { parts[g].level = LEVEL[manual[g]]; parts[g].status = manual[g]; parts[g].statusLabel = LEVEL_LABEL[parts[g].level]; }
  if (lobby) lobby.setStatus(bodyColors(parts));
  renderAttention(); renderTiles();
  if (!light) { renderScores(); if (state.sel) renderCard(); }
  else if (state.sel) {                                             // live tick: redraw the card only when its content changed, and keep its place
    const st = parts[state.sel.group], sig = JSON.stringify([st.level, st.warnings.map(w => w.text), st.notes.map(n => n.text), st.indicators.map(i => i.value)]), card = $('partCard');
    if (card.dataset.sig !== sig) { const y = card.scrollTop, open = !!(card.querySelector('.plist') || {}).open; renderCard(); card.dataset.sig = sig; card.scrollTop = y; const d = card.querySelector('.plist'); if (d) d.open = open; }
  }
  if (typeof assistantStatus === 'function') assistantStatus();
}
const keyLevel = key => {
  let lv = -1;
  for (const id in parts) for (const x of [...parts[id].warnings, ...parts[id].notes]) if (x.key === key) lv = Math.max(lv, x.level);
  return lv;
};
const levelToUi = lv => (lv < 0 ? null : LEVEL_NAME[lv]);

/* ---------- Tiles (left, no part selected) ---------- */
const num = v => typeof v === 'number' && Number.isFinite(v);
const VITALS = [
  { id: 'hr', label: 'Heart rate', unit: 'bpm', key: 'hr.rest', live: 'hr.now', group: 'heart', layer: 'organ' },
  { id: 'bp', label: 'Blood pressure', unit: 'mmHg', key: 'bp.sys', group: 'artery', layer: 'organ', val: M => (num(M['bp.sys']) && num(M['bp.dia']) ? `${M['bp.sys']}/${M['bp.dia']}` : undefined), base: M => M['bp.sys'] },
  { id: 'spo2', label: 'Blood oxygen', unit: '%', key: 'spo2.pct', live: 'spo2.pct', group: 'lung', layer: 'organ' },
  { id: 'resp', label: 'Breathing', unit: '/min', key: 'resp.rate', live: 'resp.rate', group: 'lung', layer: 'organ' },
  { id: 'hrv', label: 'Heart rate variability', unit: 'ms', key: 'hrv.rmssdMs', live: 'hrv.rmssdMs', group: 'heart', layer: 'organ' },
  { id: 'skin', label: 'Skin temperature', unit: '°C', key: 'skin.tempC', live: 'skin.tempC', group: 'body' },
  { id: 'eda', label: 'Skin conductance', unit: 'µS', key: 'eda.uS', live: 'eda.uS', group: 'body' },
  { id: 'temp', label: 'Temperature', unit: '°C', key: 'temp.c', group: 'body' },
  { id: 'glucose', label: 'Blood glucose', unit: 'mg/dL', key: 'glucose.mgdl', group: 'liver', layer: 'organ' },
  { id: 'rt', label: 'Reaction time', unit: 'ms', key: 'pvt.lapses', group: 'brain', layer: 'organ', val: M => M['pvt.meanRtMs'] },
  { id: 'sleep', label: 'Sleep', unit: 'h', key: 'sleep.hours', group: 'brain', layer: 'organ' },
  { id: 'pain', label: 'Back pain', unit: '/10', key: 'back.pain', group: 'spineL', layer: 'bone' },
  { id: 'hgb', label: 'Hemoglobin', unit: 'g/dL', key: 'hemoglobin.gdl', group: 'spleen', layer: 'organ' },
  { id: 'urine', label: 'Urine volume', unit: 'L/day', key: 'urine.volumeL', group: 'kidney', layer: 'organ' },
  { id: 'mass', label: 'Body mass', unit: '% vs. pre', key: 'mass.changePct', group: 'body' },
  { id: 'rad', label: 'Radiation', unit: 'mSv', key: 'radiation.careerMsv', group: 'body' },
  { id: 'dose', label: 'Dose rate', unit: 'µSv/h', key: 'radiation.rateUsvH', live: 'radiation.rateUsvH', group: 'body' },
  { id: 'hip', label: 'Hip bone', unit: '% vs. pre', key: 'bmd.hipPct', group: 'femur', layer: 'bone' },
  { id: 'str', label: 'Strength', unit: '% vs. pre', key: 'strength.changePct', group: 'mThigh', layer: 'muscle' },
  { id: 'vitd', label: 'Vitamin D', unit: 'ng/mL', key: 'vitd.ngml', group: 'body' }
];
const vitals = {}; const resetVitals = () => { for (const v of VITALS) vitals[v.id] = { value: null, status: null, text: 'No data', history: [] }; }; resetVitals();
let activeView = 'overview';
const viewGroups = {sleep:['sleep','rt','hrv','eda'],exercise:['str','hr','resp','hip','pain','skin'],nutrition:['mass','glucose','vitd','hgb']};
const viewCopy = {
 overview:['YOUR HEALTH AT A GLANCE','Daily overview'],
 sleep:['REST & RECOVERY','Sleep'],
 exercise:['MOVEMENT & STRENGTH','Exercise'],
 nutrition:['NUTRITION & METABOLISM','Nutrition']
};
function setView(view) {
  activeView = viewCopy[view] ? view : 'overview';
  document.querySelectorAll('[data-view]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.view === activeView)));
  const copy = viewCopy[activeView], intro = $('viewIntro');
  intro.querySelector('span').textContent = copy[0]; intro.querySelector('h2').textContent = copy[1];
  document.querySelector('.left').dataset.view = activeView;
  deselect();
  if (viewGroups[activeView]) state.vital = viewGroups[activeView][0];
  renderTiles(); renderScores(); renderPast();
}
document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => setView(button.dataset.view)));

/* ---------- Sleep / Exercise / Nutrition scores (scores.mjs) ---------- */
const RING_R = 42, RING_C = 2 * Math.PI * RING_R;
function ringSvg(sc) {
  const has = sc.score !== null, frac = has ? sc.score / 100 : 0, col = scoreColor(sc.score), cov = sc.coverage.have / sc.coverage.total;
  return `<svg class="ring" viewBox="0 0 100 100" role="img" aria-label="${sc.label} score ${has ? sc.score + ' of 100' : 'no data'}">
    <circle class="rtrack" cx="50" cy="50" r="${RING_R}"/>
    <circle class="rcov" cx="50" cy="50" r="48.5" stroke-dasharray="${(cov * 304.7).toFixed(1)} 304.7"/>
    <circle class="rval" cx="50" cy="50" r="${RING_R}" stroke="${col}" stroke-dasharray="${RING_C.toFixed(1)}" stroke-dashoffset="${RING_C.toFixed(1)}" data-off="${(RING_C * (1 - frac)).toFixed(1)}" style="filter:drop-shadow(0 0 5px ${col})"/>
    <text x="50" y="50" class="rnum">${has ? sc.score : '–'}</text></svg>`;
}
let lastScores = {};
function renderScores() {
  const box = $('scores'); if (!box) return;
  const all = scoreAll(currentInput()); box.innerHTML = '';
  if (state.sel) { box.hidden = true; return; } box.hidden = false;
  if (activeView === 'overview') {
    box.className = 'scores row';
    for (const id of DOMAIN_IDS) {
      const sc = all[id], b = el('button', 'ringcard'); b.type = 'button'; b.innerHTML = ringSvg(sc);
      b.append(el('b', '', sc.label), el('small', '', sc.score === null ? 'No data' : `${sc.coverage.have}/${sc.coverage.total} inputs`));
      b.onclick = () => setView(id); box.append(b);
    }
  } else {
    box.className = 'scores detail';
    const sc = all[activeView], hero = el('div', 'scorehero'); hero.innerHTML = ringSvg(sc);
    const txt = el('div', 'shtxt'); const w = el('b', '', scoreWord(sc.score)); w.style.color = scoreColor(sc.score);
    txt.append(w, el('span', '', `${sc.coverage.have} of ${sc.coverage.total} inputs`)); hero.append(txt); box.append(hero);
    for (const it of sc.items) {
      const d = el('details', 'comp'), sum = el('summary');
      const inp = el('input'); inp.type = 'number'; inp.inputMode = 'decimal'; inp.placeholder = '–'; inp.setAttribute('aria-label', it.label);
      if (it.edit) { inp.min = it.edit.min; inp.max = it.edit.max; inp.step = it.edit.step; }
      if (it.value !== null) inp.value = it.value;
      inp.onclick = e => e.stopPropagation(); inp.onkeydown = e => { e.stopPropagation(); if (e.key === 'Enter') inp.blur(); }; inp.onkeyup = e => e.preventDefault();
      inp.onchange = () => {
        if (inp.value === '') { delete M[it.key]; recompute(); syncTiles(false); return; }
        let v = Number(inp.value); if (!Number.isFinite(v)) return;
        if (it.edit) v = Math.max(it.edit.min, Math.min(it.edit.max, v));
        setMeasurements({ [it.key]: v });
      };
      const val = el('span', 'cv'); val.append(inp, el('small', '', it.unit));
      const bar = el('span', 'cbar'); const fill = el('i'); fill.style.width = (it.score === null ? 0 : Math.max(3, it.score)) + '%'; fill.style.background = scoreColor(it.score); bar.append(fill);
      sum.append(el('span', 'cl', it.label), val, bar); d.append(sum);
      const more = el('p', 'cmore', it.target + '. ' + (it.basis === 'reference' ? 'Anchored to: ' : 'General convention. '));
      const a = srcLink(it.src); if (a) more.append(a); d.append(more); box.append(d);
    }
  }
  requestAnimationFrame(() => box.querySelectorAll('.rval').forEach(c => { c.style.strokeDashoffset = c.dataset.off; }));
  lastScores = all;
}
function renderTiles() {
  const box = $('tiles'), list = VITALS.filter(v => !viewGroups[activeView] || viewGroups[activeView].includes(v.id)), sig = list.map(v => v.id).join();
  if (box.dataset.sig !== sig) {                                    // build once per view; afterwards the tiles are updated in place
    box.innerHTML = ''; box.dataset.sig = sig;
    for (const v of list) { const b = document.createElement('button'); b.dataset.id = v.id;
      b.innerHTML = '<span class="tl"></span><span class="td"></span><span class="tv"><span></span><small></small></span><span class="ts"></span><svg class="spark" viewBox="0 0 60 20" aria-hidden="true"><polyline points=""/></svg>';
      b.querySelector('.tl').textContent = v.label; b.onclick = () => selectVital(v.id); box.appendChild(b); }
  }
  for (const b of box.children) {
    const v = VITALS.find(x => x.id === b.dataset.id), s = vitals[v.id], isLive = live.on && !!v.live;
    b.className = 'tile' + (state.vital === v.id ? ' sel' : '') + (isLive ? ' live' : '');
    b.querySelector('.ts').textContent = s.text; b.querySelector('.td').className = 'td ' + (s.status || '');
    b.querySelector('.tv span').textContent = s.value === null ? '–' : s.value; b.querySelector('.tv small').textContent = s.value === null ? '' : v.unit;
    const sp = b.querySelector('.spark'), h = s.history;
    if (h.length > 2 && v.unit.length < 6) { const mn = Math.min(...h), mx = Math.max(...h), span = (mx - mn) || 1;
      sp.firstChild.setAttribute('points', h.map((x, i) => `${(i / (h.length - 1) * 60).toFixed(1)},${(18 - (x - mn) / span * 16).toFixed(1)}`).join(' ')); sp.style.display = ''; }
    else sp.style.display = 'none';
  }
}
function selectVital(id) {
  state.vital = id; const v = VITALS.find(x => x.id === id);
  if (v.layer) setLayer(v.layer); selectPart(v.group); renderPast();
}

/* ---------- Past data + upcoming (right) ---------- */
function renderPast() {
  const v = VITALS.find(x => x.id === state.vital), h = vitals[v.id].history;
  $('pastSub').textContent = h.length ? `${v.label} · ${live.on && v.live ? 'live, last ' + h.length + ' s' : 'last ' + h.length + ' days'}` : v.label;
  const chart = $('chart'), stats = $('stats');
  if (!h.length) { chart.textContent = 'No history yet'; stats.innerHTML = ''; return; }
  const mn = Math.min(...h), mx = Math.max(...h), pad = (mx - mn) * 0.15 || 1, lo = mn - pad, hi = mx + pad, W = 300, H = 110;
  const pts = h.map((x, i) => [(i / (h.length - 1 || 1)) * W, H - ((x - lo) / (hi - lo)) * H]);
  const line = pts.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join(' ');
  const last = pts[pts.length - 1];
  chart.innerHTML = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true"><defs><linearGradient id="cg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#63dbcd" stop-opacity=".32"/><stop offset="1" stop-color="#63dbcd" stop-opacity="0"/></linearGradient></defs><path d="${line} L${W} ${H} L0 ${H} Z" fill="url(#cg)"/><path d="${line}" fill="none" stroke="var(--ink)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"/></svg><i class="cdot" style="left:${(last[0] / W * 100).toFixed(2)}%;top:${(last[1] / H * 100).toFixed(2)}%"></i>`;
  const avg = h.reduce((a, b) => a + b, 0) / h.length, f = x => Math.round(x * 10) / 10;
  stats.innerHTML = `<div><span>Min</span><b>${f(mn)}</b></div><div><span>Average</span><b>${f(avg)}</b></div><div><span>Max</span><b>${f(mx)}</b></div>`;
}
let envItems = [], predItems = [];
function renderList(el, items) {
  el.innerHTML = '';
  if (!items.length) { const d = document.createElement('li'); d.className = 'none'; d.textContent = 'No data yet'; el.appendChild(d); return; }
  for (const it of items) { const li = document.createElement('li'); li.textContent = it.text; if (it.note) { const s = document.createElement('small'); s.textContent = it.note; li.appendChild(s); } el.appendChild(li); }
}
const renderUpcoming = () => { renderList($('envList'), envItems); renderList($('predList'), predItems); };

/* ---------- Attention chips (centre) ---------- */
function renderAttention() {
  const box = $('attn'), { counts, attention } = summarize(parts);
  const sig = counts.nodata + '|' + attention.map(a => a.id + a.level).join(); if (box.dataset.sig === sig) return;
  box.dataset.sig = sig; box.innerHTML = '';
  if (counts.nodata === Object.keys(parts).length) return;
  if (!attention.length) { const s = document.createElement('span'); s.textContent = 'Nothing needs attention in the data entered.'; box.appendChild(s); return; }
  for (const a of attention.slice(0, 6)) {
    const b = document.createElement('button'); b.innerHTML = '<i></i><span></span>'; b.firstChild.className = LEVEL_NAME[a.level];
    b.lastChild.textContent = `${a.label} · ${LEVEL_LABEL[a.level]}`; b.title = a.text; b.onclick = () => selectPart(a.id); box.appendChild(b);
  }
  if (attention.length > 6) { const s = document.createElement('span'); s.textContent = `+${attention.length - 6} more`; box.appendChild(s); }
}

/* ---------- Part card (left) ---------- */
const sideName = s => (s === 'left' ? 'Left ' : s === 'right' ? 'Right ' : '');
const SINGULAR = { lung: 'lung', kidney: 'kidney', eye: 'eye', mUpperArm: 'upper-arm muscles', mForearm: 'forearm muscles', mThigh: 'thigh muscles', mShin: 'lower-leg muscles', tendon: 'tendons', shoulder: 'shoulder girdle', arm: 'arm bones', hand: 'hand bones', femur: 'thigh bone (femur)', shin: 'lower-leg bones', foot: 'foot bones' };
const partName = (group, side) => (PAIRED.includes(group) && side && SINGULAR[group] ? sideName(side) + SINGULAR[group] : PARTS[group].label);
const cap = t => t.charAt(0).toUpperCase() + t.slice(1);
/** Display name of a single bone or muscle: the BodyParts3D name, with the side in front when the name does not carry it. */
const singleName = i => { const n = i.name.replace(/\bsecondary /, ''); return cap(/\b(left|right)\b/.test(n) || !i.named ? n : i.named + ' ' + n); };
const selName = sel => (sel.name ? singleName(sel) : partName(sel.group, sel.side));
function srcLink(key) {
  const s = ALL_SRC[key]; if (!s) return null;
  const a = document.createElement('a'); a.href = s.url; a.target = '_blank'; a.rel = 'noopener'; a.textContent = s.title; return a;
}
function el(tag, cls, text) { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; }
function renderCard() {
  const sel = state.sel, card = $('partCard'); if (!sel) { card.hidden = true; $('tiles').hidden = false; renderScores(); return; }
  const def = PARTS[sel.group], st = parts[sel.group];
  card.hidden = false; $('tiles').hidden = true; $('scores').hidden = true; card.innerHTML = '';
  const top = el('div', 'top'); const back = el('button', 'back', '‹'); back.setAttribute('aria-label', 'Back'); back.onclick = () => deselect();
  const pill = el('span', 'st ' + st.status); pill.append(el('i'), document.createTextNode(st.statusLabel));
  top.append(back, el('h2', '', selName(sel)), pill); card.append(top);
  if (sel.name) {                                                  // a single bone or muscle: it is rated with its group
    const row = el('div', 'partof'); row.append(el('span', '', (sel.layer === 'bone' ? 'Bone' : 'Muscle') + ' · part of'));
    const g = el('button', '', partName(sel.group, sel.side)); g.type = 'button'; g.title = 'Select the whole group'; g.onclick = () => selectPart(sel.group, sel.side); row.append(g); card.append(row);
    card.append(el('p', 'does', `${def.does} The status and the facts below apply to the whole group: the data entered is not specific to a single ${sel.layer === 'bone' ? 'bone' : 'muscle'}.`));
  } else {
    card.append(el('p', 'does', def.does));
    const list = lobby && sel.group !== 'body' ? lobby.partsOf(sel.group, PAIRED.includes(sel.group) ? sel.side : null) : [];
    if (list.length > 1) {
      const d = el('details', 'plist'); d.append(el('summary', '', `${list.length} single ${list[0].layer === 'bone' ? 'bones and joints' : 'muscles'} in this group`));
      const box = el('div', 'pchips'); for (const i of list.sort((a, b) => b.center.y - a.center.y)) { const b = el('button', '', singleName(i)); b.type = 'button'; b.onclick = () => lobby.select(i.pid, true); box.append(b); }
      d.append(box); card.append(d);
    }
  }
  if (st.warnings.length) {
    card.append(el('h3', '', 'Warnings'));
    for (const w of st.warnings) {
      const li = el('div', 'warnli lv' + w.level, w.text); const m = el('span', 'meta', BASIS[w.basis] || ''); if (w.src) { m.append(document.createTextNode(' · ')); const a = srcLink(w.src); if (a) m.append(a); } li.append(m); card.append(li);
    }
  } else if (st.level === LEVEL.nodata) {
    const rated = def.ind.filter(k => INDICATORS[k].rate !== false);
    card.append(el('div', 'gap', rated.length ? 'No rated data for this part yet. It is rated from: ' + rated.map(k => INDICATORS[k].label.toLowerCase()).join(', ') + '.' : 'No indicator is connected to this part, so it cannot be rated.'));
  } else card.append(el('div', 'gap', 'No warning in the data entered.'));
  if (st.level >= 2) card.append(el('div', 'gap', st.level >= 3 ? 'Contact the flight surgeon now.' : 'Re-measure, then tell the flight surgeon at the next contact.'));
  if (st.notes.length) { card.append(el('h3', '', 'In range')); const ul = el('ul'); for (const n of st.notes) { const li = el('li', '', n.text); ul.append(li); } card.append(ul); }
  if (def.ind.length) {
    card.append(el('h3', '', 'Indicators NASA tracks'));
    const g = el('div', 'ind');
    for (const i of st.indicators) {
      const v = i.value === null ? '–' : typeof i.value === 'boolean' ? (i.value ? 'yes' : 'no') : `${i.value}${i.unit ? ' ' + i.unit : ''}`;
      g.append(el('span', '', i.label), el('b', '', v), el('small', '', i.how + (i.flight ? ' · measurable in flight' : ' · not measurable in flight') + (i.rate === false ? ' · tracked, not rated: it is read against the personal baseline' : '') + (i.why ? '. Why: ' + i.why : '')));
    }
    card.append(g);
  }
  if (def.facts.length) { card.append(el('h3', '', 'What spaceflight does')); const ul = el('ul'); for (const f of def.facts) { const li = el('li', '', f.t); const m = el('span', 'meta'); const a = srcLink(f.s); if (a) m.append(a); li.append(m); ul.append(li); } card.append(ul); }
  if (def.helps.length) { card.append(el('h3', '', 'What helps')); const ul = el('ul'); for (const f of def.helps) { const li = el('li', '', f.t); const m = el('span', 'meta'); const a = srcLink(f.s); if (a) m.append(a); li.append(m); ul.append(li); } card.append(ul); }
  if (def.gap) card.append(el('div', 'gap', 'Gap: ' + def.gap));
  card.append(el('div', 'disc', 'Decision support, not a diagnosis. Contact the flight surgeon for anything that worries you.'));
  card.scrollTop = 0;
}

/* ---------- Selection ---------- */
const groupOf = pid => lobby.info[pid];
function selectPart(group, side) {
  if (group === 'body') { if (lobby) lobby.select(-1); state.sel = { group: 'body', side: null, pid: -1 }; renderCard(); return; }
  if (!lobby || !PARTS[group]) return;
  const need = lobby.layerOf[group];
  if (need && state.layer !== 'all' && state.layer !== need) setLayer(need);
  lobby.select(lobby.pidOf(group, side || 'left'), false);       // onPick updates the card
}
function deselect() { state.sel = null; if (lobby) lobby.select(-1); renderCard(); }
function onPick(i) {
  if (!i) { state.sel = null; renderCard(); return; }
  state.sel = { group: i.group, side: PAIRED.includes(i.group) ? i.side : null, pid: i.pid };
  if (i.name) Object.assign(state.sel, { name: i.name, named: i.named, layer: i.layer });
  $('hint').classList.add('gone'); renderCard();
}
const tip = $('tip');
function onHover(i, x, y) {
  if (!i) { tip.hidden = true; return; }
  const r = $('cam').getBoundingClientRect(), st = parts[i.group];
  tip.hidden = false; tip.style.left = (x - r.left) + 'px'; tip.style.top = (y - r.top) + 'px';
  tip.textContent = i.name ? singleName(i) : partName(i.group, i.side);
  const s = document.createElement('small'); s.textContent = (i.name ? PARTS[i.group].label + ' · ' : '') + st.statusLabel; tip.append(s);
}

/* ---------- Layer and look ---------- */
function setLayer(l) {
  state.layer = l; if (lobby) lobby.setLayer(l);
  document.querySelectorAll('#seg button').forEach(b => b.classList.toggle('on', b.dataset.layer === l));
  if (state.sel && state.sel.group !== 'body' && lobby && l !== 'all' && lobby.layerOf[state.sel.group] !== l) deselect();
}
function setLook(x) {
  state.look = x === 'xray' ? 'xray' : 'solid'; if (lobby) lobby.setLook(state.look);
  document.querySelectorAll('#segLook button').forEach(b => b.classList.toggle('on', b.dataset.look === state.look));
}

/* ---------- Data setters ---------- */
function sampleSeries(seed, base, spread, n) { let s = seed; const out = []; for (let i = 0; i < n; i++) { s = (s * 1664525 + 1013904223) % 4294967296; out.push(Math.round((base + (s / 4294967296 - .5) * 2 * spread) * 10) / 10); } return out; }
const TXT = lv => (lv < 0 ? 'No data' : LEVEL_LABEL[lv]);
function syncTiles(withHistory) {
  for (const d of VITALS) {
    const key = d.live && num(M[d.live]) ? d.live : d.key;
    const value = d.val ? d.val(M) : M[key]; if (value === undefined || value === null) continue;
    const lv = keyLevel(key), s = vitals[d.id], base = d.base ? d.base(M) : value, rated = !INDICATORS[key] || INDICATORS[key].rate !== false;
    s.value = value; s.status = levelToUi(lv);
    s.text = d.id === 'rt' && num(M['pvt.lapses']) ? `${M['pvt.lapses']} lapses · ${TXT(lv)}` : !rated ? 'Not rated' : TXT(lv);
    if (withHistory && num(Number(base))) s.history = sampleSeries(d.id.length * 7 + d.unit.length, Number(base), Math.max(Math.abs(Number(base)) * 0.04, 0.6), 14).map(v => (d.id === 'pain' ? Math.max(0, Math.min(10, Math.round(v))) : v));
  }
  renderTiles(); renderPast();
}
function setMeasurements(obj, opts = {}) {
  if (obj['body.heightCm'] !== undefined || obj['body.massKg'] !== undefined || obj.sex) setBody({ heightCm: obj['body.heightCm'], massKg: obj['body.massKg'], sex: obj.sex }, false, true);
  for (const k in obj) {
    if (k === 'mission.month' || k === 'sex' || k === 'activity' || k === 'pvt.confirmed' || k === 'pvt.meanRtMs' || INDICATORS[k] || SCORE_KEYS.includes(k)) M[k] = obj[k];
  }
  recompute(); syncTiles(!!opts.history); return true;
}
/** Loads one of the invented test scenarios (testdata.mjs): 'nominal', 'mixed' or 'critical'. */
function loadSample(id = 'mixed') {
  const sc = SCENARIOS[id] || SCENARIOS.mixed; id = SCENARIOS[id] ? id : 'mixed';
  stopLive(); M = {}; resetVitals(); state.sample = id; setBody(sc.body, false, true); setMeasurements(sc.data, { history: true });
  envItems = sc.environment.map(text => ({ text, note: 'Test data' })); predItems = sc.predictions.map(text => ({ text, note: 'Test data' }));
  renderUpcoming(); $('sampleChip').hidden = false; $('sampleChip').textContent = 'Test data · ' + sc.label; $('sampleBtn').textContent = 'Test data · ' + sc.label;
  if (lobby) lobby.setHeartRate(M['hr.rest']);
  startLive();
  return true;
}
function clearSample() {
  stopLive(); M = {}; state.sample = false; resetVitals(); envItems = []; predItems = []; setBody(storedBody(), false, true);
  $('sampleChip').hidden = true; $('sampleBtn').textContent = 'Test data';
  recompute(); renderTiles(); renderPast(); renderUpcoming(); renderActivity();
}
/* Test-data menu above the button */
function testMenu(open) {
  const m = $('testMenu'); m.hidden = !open; $('sampleBtn').setAttribute('aria-expanded', String(open)); if (!open) return;
  m.innerHTML = '';
  for (const id of SCENARIO_IDS) { const sc = SCENARIOS[id], b = el('button', 'tm ' + id + (state.sample === id ? ' on' : '')); b.type = 'button'; b.setAttribute('role', 'menuitem');
    b.append(el('i'), el('b', '', sc.label), el('small', '', sc.note)); b.onclick = () => { testMenu(false); loadSample(id); }; m.append(b); }
  const rp = el('button', 'tm plainrow'); rp.type = 'button'; rp.append(el('b', '', 'Paste as a report'), el('small', '', 'Puts the borderline data into the message box as text'));
  rp.onclick = () => { testMenu(false); const t = $('chatIn'); t.value = reportText('mixed'); fitIn(); t.focus(); }; m.append(rp);
  if (state.sample) { const c = el('button', 'tm plainrow'); c.type = 'button'; c.append(el('b', '', 'Clear test data')); c.onclick = () => { testMenu(false); clearSample(); }; m.append(c); }
}
addEventListener('pointerdown', e => { if (!$('testMenu').hidden && !e.target.closest('#testMenu,#sampleBtn')) testMenu(false); if (!$('bodyPop').hidden && !e.target.closest('#bodyPop,#bodyBtn')) $('bodyPop').hidden = true; if (!$('actMenu').hidden && !e.target.closest('#actMenu,#actBtn')) actMenu(false); });

/* ---------- Body size: height and mass stretch the model (approximate, the anatomy is not re-shaped) ---------- */
// The BodyParts3D skeleton spans 164 cm from sole to skull top; with scalp and heel pad that is taken as a stature of 166 cm.
// Breadth follows the body-mass index relative to 22.5 kg/m², damped, because a frame does not widen as fast as mass grows.
const REF_BODY = { heightCm: 166, massKg: 62 }, BODY_MAX = { heightCm: [150, 205], massKg: [45, 130] };
function storedBody() { try { const b = JSON.parse(localStorage.getItem('medvital.body') || 'null'); return b && typeof b === 'object' ? b : null; } catch (e) { return null; } }
function bodyScale(h, m) {
  const sy = h / REF_BODY.heightCm, bmi = m / (h / 100) ** 2, f = Math.max(.9, Math.min(1.22, Math.pow(bmi / 22.5, .4)));
  return { sx: sy * f, sy, bmi };
}
/** setBody({heightCm, massKg, sex}) changes what is given; setBody(null) clears everything. `quiet` skips the re-rating (the caller does it). */
function setBody(b, save, quiet) {
  const cl = (v, r) => Math.max(r[0], Math.min(r[1], Math.round(v)));
  if (!b) { body.heightCm = body.massKg = body.sex = null; }
  else { if (num(b.heightCm)) body.heightCm = cl(b.heightCm, BODY_MAX.heightCm); if (num(b.massKg)) body.massKg = cl(b.massKg, BODY_MAX.massKg); if (b.sex === 'f' || b.sex === 'm') body.sex = b.sex; else if (b.sex === null) body.sex = null; }
  const h = body.heightCm || REF_BODY.heightCm, m = body.massKg || REF_BODY.massKg, sc = bodyScale(h, m), sized = body.heightCm || body.massKg;
  if (lobby) { lobby.setBody(sc.sx, sc.sy); lobby.setFemale(body.sex === 'f'); }
  if (body.sex) M.sex = body.sex; else delete M.sex;
  $('rH').value = h; $('rW').value = m; $('vH').textContent = h + ' cm'; $('vW').textContent = `${m} kg · BMI ${sc.bmi.toFixed(1)}`;
  document.querySelectorAll('#segSex button').forEach(x => x.classList.toggle('on', x.dataset.sex === body.sex));
  $('bodyBtn').textContent = [body.sex ? (body.sex === 'f' ? 'Female' : 'Male') : '', sized ? `${h} cm · ${m} kg` : ''].filter(Boolean).join(' · ') || 'Body';
  if (save) { try { sized || body.sex ? localStorage.setItem('medvital.body', JSON.stringify(body)) : localStorage.removeItem('medvital.body'); } catch (e) {} }
  if (!quiet) { recompute(); syncTiles(false); }
  return { ...body, ...sc };
}
$('bodyBtn').onclick = () => { actMenu(false); $('bodyPop').hidden = !$('bodyPop').hidden; };
$('rH').oninput = () => setBody({ heightCm: +$('rH').value, massKg: +$('rW').value }, true, true);
$('rW').oninput = $('rH').oninput;
document.querySelectorAll('#segSex button').forEach(x => x.onclick = () => setBody({ sex: body.sex === x.dataset.sex ? null : x.dataset.sex }, true));
$('bodyReset').onclick = () => setBody(null, true);

/* ---------- Current activity and the live test stream (live.mjs) ----------
   The activity (resting, sleeping, working, exercising, spacewalk) is part of the rating: heart and breathing rate are only
   rated at rest. With test data loaded, a simulated wearable stream updates the continuous values once per second and
   follows a compressed day; the activity can also be set by hand. Nothing in the stream is measured. */
const live = { on: false, sim: null, t: 0, mode: 'auto', timer: null, lastActive: -1e9 };
const RECOVERY_S = 30;                       // after exercise the heart and breathing rate need time to settle and are not rated
function renderActivity() {
  const a = M.activity, btn = $('actBtn');
  btn.className = 'actpill' + (a ? ' a-' + a : '') + (live.on ? ' live' : '');
  $('actTxt').textContent = a ? (M.recovering ? 'Recovering' : ACTIVITIES[a].label) + (live.on ? ' · live' : '') : 'Activity';
}
function setActivity(a) {
  if (a === 'auto') live.mode = 'auto';
  else if (ACTIVITIES[a]) { live.mode = a; M.activity = a; }
  else { live.mode = 'auto'; delete M.activity; }
  if (live.on) liveTick(); else { recompute(); syncTiles(false); }
  renderActivity(); return M.activity || null;
}
function liveTick() {
  const a = live.mode === 'auto' ? live.sim.activityAt(live.t) : live.mode, v = live.sim.step(1, a); live.t++;
  Object.assign(M, v); M.activity = a;
  if (a === 'exercise' || a === 'eva') live.lastActive = live.t; M.recovering = live.t - live.lastActive <= RECOVERY_S && live.t !== live.lastActive;
  for (const d of VITALS) if (d.live && num(v[d.live])) { const s = vitals[d.id]; s.history = [...s.history.slice(-59), v[d.live]]; }
  recompute(true); syncTiles(false); renderActivity();
  if (lobby) { lobby.setHeartRate(v['hr.now']); lobby.setBreathRate(v['resp.rate']); }
}
function startLive() {
  stopLive(true); live.sim = createLive({ base: { ...M }, seed: 7 }); live.on = true; live.t = 0; live.mode = 'auto'; live.lastActive = -1e9;
  for (const d of VITALS) if (d.live) vitals[d.id].history = [];
  live.timer = setInterval(liveTick, 1000); liveTick(); return true;
}
function stopLive(quiet) {
  clearInterval(live.timer); live.timer = null; const was = live.on; live.on = false; delete M.recovering;
  if (was && !quiet) { renderTiles(); renderActivity(); }
  if (lobby) lobby.setBreathRate(13.3);
  return was;
}
function actMenu(open) {
  const m = $('actMenu'); m.hidden = !open; if (!open) return; $('bodyPop').hidden = true; m.innerHTML = '';
  const row = (cls, title, note, fn, on) => { const b = el('button', 'tm ' + cls + (on ? ' on' : '')); b.type = 'button'; b.setAttribute('role', 'menuitem'); b.append(el('i'), el('b', '', title)); if (note) b.append(el('small', '', note)); b.onclick = () => { actMenu(false); fn(); }; m.append(b); };
  if (live.on) row('auto', 'Follow the test stream', 'A compressed day: rest, work, exercise, sleep', () => setActivity('auto'), live.mode === 'auto');
  for (const id of ACTIVITY_IDS) row('a-' + id, ACTIVITIES[id].label, ACTIVITIES[id].note, () => setActivity(id), live.mode === id || (!live.on && M.activity === id));
  if (live.on) row('plainrow', 'Stop the live test stream', '', () => { stopLive(); });
  else if (state.sample) row('plainrow', 'Start the live test stream', 'Simulated wearable values, once per second', () => startLive());
  else row('plainrow', 'Clear the activity', '', () => setActivity(null));
}
$('actBtn').onclick = () => actMenu($('actMenu').hidden);

/** Tile values from health.mjs and other callers. */
function setVital(id, d) {
  const v = VITALS.find(x => x.id === id); if (!v) return false;
  const s = vitals[id]; if ('value' in d) s.value = d.value; if ('status' in d) s.status = d.status || null; if ('text' in d) s.text = d.text || 'No data'; if (d.history) s.history = d.history.slice();
  if (id === 'hr' && typeof s.value === 'number' && lobby) lobby.setHeartRate(s.value);
  renderTiles(); renderPast(); queueMicrotask(recompute); return true;
}
const setEnvironment = items => { envItems = items.slice(); renderUpcoming(); };
const setPredictions = items => { predItems = items.slice(); renderUpcoming(); queueMicrotask(recompute); };
const SYSTEM_GROUPS = { skeleton: Object.keys(PARTS).filter(g => PARTS[g].system === 'skeleton'), cardio: ['heart', 'artery', 'vein'], lung: ['lung', 'airway'], digest: ['liver', 'stomach', 'intestine', 'kidney', 'spleen'], brain: ['brain', 'eye'], muscle: Object.keys(PARTS).filter(g => PARTS[g].system === 'muscle') };
function setGroupStatus(group, status) { if (!PARTS[group]) return false; if (status && LEVEL[status] !== undefined) manual[group] = status; else delete manual[group]; recompute(); return true; }
function setSystemStatus(id, status) { const g = SYSTEM_GROUPS[id]; if (!g) return false; for (const x of g) { if (status && LEVEL[status] !== undefined) manual[x] = status; else delete manual[x]; } recompute(); return true; }

/* ---------- Controls ---------- */
document.querySelectorAll('#seg button').forEach(b => b.onclick = () => setLayer(b.dataset.layer));
document.querySelectorAll('#segLook button').forEach(b => b.onclick = () => setLook(b.dataset.look));
document.querySelectorAll('#segRot button').forEach(b => b.onclick = () => { document.querySelectorAll('#segRot button').forEach(x => x.classList.toggle('on', x === b)); if (lobby) lobby.setAutoRotate(b.dataset.rot === '1'); });
$('sampleBtn').onclick = () => testMenu($('testMenu').hidden);
$('bBody').onclick = () => selectPart('body');
$('bReset').onclick = () => { deselect(); if (lobby) lobby.resetView(); };
const openSheet = o => { $('ov').hidden = !o; }; $('setBtn').onclick = () => openSheet(true); $('setDone').onclick = () => openSheet(false);
$('ov').onclick = e => { if (e.target === $('ov')) openSheet(false); };
const opf = () => { $('vOp').textContent = $('rOp').value + ' %'; if (lobby) lobby.setOpacity(+$('rOp').value / 100); }; $('rOp').oninput = opf; opf();
addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
  const m = { '1': 'bone', '2': 'organ', '3': 'muscle', '4': 'all' }[e.key]; if (m) setLayer(m);
  if (e.key === 'x') setLook(state.look === 'xray' ? 'solid' : 'xray');
  if (e.key === 'Escape') { deselect(); testMenu(false); actMenu(false); $('bodyPop').hidden = true; }
  if (e.key === 'r') { deselect(); if (lobby) lobby.resetView(); }
});


/* ---------- Rotation helpers (buttons and arrow keys) ---------- */
function holdRotate(btn, dir) {
  let t = null; const stop = () => { clearInterval(t); t = null; };
  btn.addEventListener('pointerdown', e => { e.preventDefault(); if (lobby) lobby.nudge(dir); t = setInterval(() => lobby && lobby.nudge(dir), 120); });
  for (const ev of ['pointerup', 'pointerleave', 'pointercancel']) btn.addEventListener(ev, stop);
}
holdRotate($('bRotL'), -1); holdRotate($('bRotR'), 1);
addEventListener('keydown', e => { if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return; if (e.key === 'ArrowLeft') lobby && lobby.nudge(-1); if (e.key === 'ArrowRight') lobby && lobby.nudge(1); });

/* ---------- Feedback (saved by server.mjs into ./feedback/) ---------- */
function feedbackState() {
  const L = lobby; const c = L ? L.camera : {};
  return { build: BUILD, t: new Date().toISOString(), ua: navigator.userAgent, viewport: `${innerWidth}x${innerHeight}@${devicePixelRatio}`, url: location.href,
    layer: state.layer, look: state.look, selected: state.sel, camera: L ? { yaw: +c.yaw.toFixed(2), pitch: +c.pitch.toFixed(2), dist: Math.round(c.dist) } : null,
    pointer: L ? L.stats : null, errors: errLog, measurements: M, body: { ...body }, live: live.on ? live.mode : false, counts: summarize(parts).counts, sample: state.sample,
    health: Object.keys((window.AstroHealth && window.AstroHealth.findings) || {}) };
}
function openFeedback(o) { $('fbOv').hidden = !o; if (o) { $('fbT').value = ''; $('fbMsg').textContent = ''; setTimeout(() => $('fbT').focus(), 50); } }
$('fbBtn').onclick = () => openFeedback(true); $('fbCancel').onclick = () => openFeedback(false);
$('fbOv').onclick = e => { if (e.target === $('fbOv')) openFeedback(false); };
$('fbForm').onsubmit = async e => {
  e.preventDefault(); const text = $('fbT').value.trim(); if (!text) return;
  const btn = $('fbSend'); btn.disabled = true; $('fbMsg').textContent = 'Sending …';
  let st = {}, shot = ''; try { st = feedbackState(); st.view = activeView; st.scores = Object.fromEntries(DOMAIN_IDS.map(id => [id, lastScores[id] ? lastScores[id].score : null])); shot = lobby ? lobby.snapshot() : ''; } catch (e2) { logErr('feedback state: ' + e2.message); }
  const body = { id: Math.random().toString(36).slice(2, 10) + Date.now().toString(36), t: Date.now(), text, state: st, shot };
  try {
    const r = await fetch('/api/feedback', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    $('fbMsg').textContent = 'Thanks, saved.'; setTimeout(() => openFeedback(false), 900);
  } catch (err) {
    // No feedback server (plain static hosting): hand the report over as a file instead
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([JSON.stringify(body, null, 2)], { type: 'application/json' })); a.download = `medvital-feedback-${body.id}.json`; document.body.appendChild(a); a.click(); a.remove();
    $('fbMsg').textContent = 'Could not reach the feedback server (start the app with MEDvital.command). The report was downloaded as a file.';
  }
  btn.disabled = false;
};

/* ---------- Assistant and data input in one conversation (right) ----------
   A question goes to the rule-based assistant; a pasted report or a dropped file goes to the reader (intake.mjs), which
   shows what it found and changes nothing until "Apply" is pressed. */
const asst = { rec: null };
const log = $('alog');
const START_CHIPS = ['How am I doing?', 'What needs attention?', 'Sleep score', 'Load test data'];
function hello() {
  log.innerHTML = ''; const h = el('div', 'hello');
  h.append(el('b', '', 'How can I help?'), el('span', '', 'Ask about your health data, or paste a medical report, lab results or a device export. I show what I found before anything changes.'));
  log.append(h); chips(START_CHIPS);
}
function push(who, node) {
  const h = log.querySelector('.hello'); if (h) h.remove();
  const d = el('div', 'msg ' + who); d.append(node); log.append(d); log.scrollTop = log.scrollHeight; return d;
}
function say(who, text) {
  const f = document.createDocumentFragment(); for (const [i, line] of String(text).split('\n').entries()) { if (i) f.append(document.createElement('br')); f.append(document.createTextNode(line)); }
  push(who, f);
}
const inMsg = (who, node) => push(who, typeof node === 'string' ? document.createTextNode(node) : node);
function chips(list) { const c = $('achips'); c.innerHTML = ''; for (const t of list || []) { const b = el('button', '', t); b.type = 'button'; b.onclick = () => ask(t); c.append(b); } }
function assistantStatus() {
  const { counts, attention } = summarize(parts), total = Object.keys(parts).length;
  $('asSub').textContent = counts.nodata === total ? 'No data yet' : attention.length ? `${attention.length} need attention` : 'All in range';
}
function ask(q) {
  q = String(q || '').trim(); if (!q) return; say('me', q);
  if (/^load test data$/i.test(q)) { loadSample('mixed'); say('bot', 'Loaded the "Borderline" test data: invented values for mission month 4 with a few findings to watch. The button under the body switches between the three test sets.'); chips(['What needs attention?', 'How am I doing?', 'Exercise score']); return; }
  if (/\bscores?\b/i.test(q)) {
    const all = scoreAll(currentInput()), want = DOMAIN_IDS.filter(id => q.toLowerCase().includes(id)), ids = want.length ? want : DOMAIN_IDS;
    const lines = ids.map(id => { const sc = all[id]; if (sc.score === null) return `${sc.label}: no data yet.`;
      const low = sc.items.filter(i => i.score !== null).sort((a, b) => a.score - b.score)[0], miss = sc.items.filter(i => i.score === null).map(i => i.label.toLowerCase());
      return `${sc.label}: ${sc.score} of 100 (${scoreWord(sc.score).toLowerCase()}), from ${sc.coverage.have} of ${sc.coverage.total} inputs.` + (low && low.score < 85 ? ` Lowest: ${low.label.toLowerCase()} (${low.value} ${low.unit}).` : '') + (miss.length ? ` Missing: ${miss.join(', ')}.` : ''); });
    say('bot', lines.join('\n') + '\nThe score is a MEDvital model anchored to NASA figures, not a NASA scale.'); chips(['Sleep score', 'Exercise score', 'Nutrition score']);
    if (want.length === 1) setView(want[0]); return;
  }
  const r = assistantAnswer(q, { parts, M: currentInput() });
  if (r.set) {
    setMeasurements(r.set);
    const extra = []; for (const k of Object.keys(r.set)) { for (const id in parts) { const x = [...parts[id].warnings, ...parts[id].notes].find(w => w.key === k); if (x) { extra.push(x.text); break; } } }
    r.text += (extra.length ? '\n' + extra.map(t => '• ' + t).join('\n') : '') + '\nYou can ask what it means or what helps.';
  }
  say('bot', r.text); chips(r.chips || SUGGESTIONS.slice(0, 3));
  if (r.focus && PARTS[r.focus]) selectPart(r.focus);
}
/** Kept for callers of the old two-tab dock: both tabs are one conversation now. */
function showDock() { setTimeout(() => $('chatIn').focus(), 30); }

const KEY_LABEL = { sex: ['Biological sex', ''], 'mission.month': ['Mission month', ''], 'pvt.meanRtMs': ['Mean reaction time', 'ms'], 'body.heightCm': ['Height', 'cm'], 'body.massKg': ['Body mass', 'kg'] };
const keyInfo = k => KEY_LABEL[k] || (INDICATORS[k] ? [INDICATORS[k].label, INDICATORS[k].unit] : SCORE_INPUTS[k] ? [SCORE_INPUTS[k].label, SCORE_INPUTS[k].unit] : [k, '']);
const fmtVal = (k, v) => (k === 'sex' ? (v === 'f' ? 'female' : 'male') : typeof v === 'boolean' ? (v ? 'yes' : 'no') : `${v}${keyInfo(k)[1] ? ' ' + keyInfo(k)[1] : ''}`);
function readSource(text, name) {
  const me = el('div'); if (name) me.append(el('b', 'file', name)); const prev = text.trim().replace(/\s+/g, ' '); if (!name || prev) me.append(el('span', 'prev', prev.length > 140 ? prev.slice(0, 140) + ' …' : prev));
  inMsg('me', me);
  const r = extract(text, name || ''), box = el('div', 'found');
  if (!r.found.length) {
    box.append(el('p', '', 'I found no health values I can read here.' + (r.unread.length ? ` Unread lines: ${r.unread.length}.` : '') + ' Write them as "label value unit", for example "hemoglobin 12.9 g/dL".'));
    inMsg('bot', box); return;
  }
  box.append(el('p', '', `Found ${r.found.length} value${r.found.length > 1 ? 's' : ''}. Untick anything that is wrong, then apply.`));
  const list = el('div', 'vals');
  for (const f of r.found) {
    const row = el('label', 'val'), cb = el('input'); cb.type = 'checkbox'; cb.checked = true; cb.dataset.key = f.key;
    row.title = f.text; row.append(cb, el('span', '', keyInfo(f.key)[0]), el('b', '', fmtVal(f.key, f.value))); list.append(row);
  }
  box.append(list);
  if (r.rejected.length) box.append(el('p', 'note', 'Not plausible, ignored: ' + r.rejected.map(x => `${keyInfo(x.key)[0]} ${x.value}`).join(', ') + '.'));
  if (r.unread.length) box.append(el('p', 'note', `${r.unread.length} line${r.unread.length > 1 ? 's' : ''} with numbers not recognised: ` + r.unread.slice(0, 3).map(l => '“' + l.slice(0, 40) + '”').join(', ') + (r.unread.length > 3 ? ' …' : '')));
  const act = el('div', 'acts'), ok = el('button', 'apply', 'Apply'), no = el('button', 'discard', 'Discard'); ok.type = no.type = 'button';
  ok.onclick = () => {
    const set = {}; list.querySelectorAll('input:checked').forEach(c => { set[c.dataset.key] = r.values[c.dataset.key]; });
    const n = Object.keys(set).length; if (!n) return;
    setMeasurements(set); if (set['hr.rest'] && lobby) lobby.setHeartRate(set['hr.rest']);
    if (set['body.heightCm'] !== undefined || set['body.massKg'] !== undefined || set.sex) setBody({}, true, true);
    list.querySelectorAll('input').forEach(c => { c.disabled = true; }); act.replaceWith(el('p', 'done', `Applied ${n} value${n > 1 ? 's' : ''} · ${new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}`));
    chips(['What needs attention?', 'How am I doing?', 'Sleep score']);
  };
  no.onclick = () => { list.querySelectorAll('input').forEach(c => { c.disabled = true; c.checked = false; }); act.replaceWith(el('p', 'done', 'Discarded')); };
  act.append(no, ok); box.append(act); inMsg('bot', box);
}
async function readFiles(files) {
  for (const f of files) {
    if (READABLE.test(f.name) || /^text\//.test(f.type) || /json/.test(f.type)) {
      if (f.size > 2e6) { inMsg('bot', `${f.name} is larger than 2 MB. Paste the relevant part instead.`); continue; }
      readSource(await f.text(), f.name);
    } else inMsg('bot', `${f.name}: PDFs and images cannot be read yet. Open the file, copy its text and paste it here.`);
  }
}
/** A message is a report when the reader finds values in it and it is not phrased as a question or a one-line statement. */
const QUESTION = /\?\s*$|^(what|how|why|is|are|am|should|can|could|do|does|which|when|where|show|tell|explain|help)\b/i;
function route(text) {
  const t = text.trim(); if (!t) return;
  const n = QUESTION.test(t) ? 0 : extract(t, '').found.length;
  if (n >= 2 || (n === 1 && (t.length > 60 || /\n/.test(t)))) readSource(t); else ask(t);
}
const fitIn = () => { const t = $('chatIn'); t.style.height = 'auto'; t.style.height = Math.min(t.scrollHeight, 150) + 'px'; $('chatSend').disabled = !t.value.trim(); };
$('chatForm').onsubmit = e => { e.preventDefault(); const t = $('chatIn').value; if (!t.trim()) return; $('chatIn').value = ''; fitIn(); route(t); };
$('chatIn').oninput = fitIn;
$('chatIn').onkeydown = e => { e.stopPropagation(); if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); $('chatForm').requestSubmit(); } };
$('chatFile').onchange = e => { readFiles([...e.target.files]); e.target.value = ''; };
{ const dock = $('dock'), drop = $('drop'); let depth = 0;
  dock.addEventListener('dragenter', e => { if (![...e.dataTransfer.types].includes('Files')) return; e.preventDefault(); depth++; drop.hidden = false; });
  dock.addEventListener('dragover', e => { if ([...e.dataTransfer.types].includes('Files')) e.preventDefault(); });
  dock.addEventListener('dragleave', () => { if (--depth <= 0) { depth = 0; drop.hidden = true; } });
  dock.addEventListener('drop', e => { e.preventDefault(); depth = 0; drop.hidden = true; readFiles([...e.dataTransfer.files]); }); }
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
if (!SR) $('chatMic').hidden = true;
$('chatMic').onclick = () => {
  if (asst.rec) { asst.rec.stop(); return; }
  const r = new SR(); asst.rec = r; r.lang = 'en-US'; r.interimResults = false; r.maxAlternatives = 1;
  $('chatMic').classList.add('rec');
  r.onresult = e => { ask(e.results[0][0].transcript); };
  r.onerror = e => { say('bot', e.error === 'not-allowed' ? 'Microphone access was denied. Allow it in the browser settings.' : 'Voice input failed (' + e.error + '). Browsers send speech to an online service, so it needs an internet connection.'); };
  r.onend = () => { asst.rec = null; $('chatMic').classList.remove('rec'); };
  try { r.start(); } catch (e) { asst.rec = null; $('chatMic').classList.remove('rec'); }
};
hello();

/* ---------- Start ---------- */
renderTiles(); renderPast(); renderUpcoming(); renderAttention();
try {
  lobby = await createLobby($('gl'), { paired: PAIRED, onPick, onHover });
  lobby.setLook(state.look); lobby.setLayer(state.layer); lobby.setOpacity(+$('rOp').value / 100); setBody(storedBody() || {}, false, true); renderActivity();
  $('camMsg').classList.add('hide'); setSub(BUILD); setDot('ok');
  recompute();
  setTimeout(() => $('hint').classList.add('gone'), 9000);
  { const m = /^#sample(?:=(\w+))?$/.exec(location.hash); if (m) loadSample(m[1] || 'mixed'); }
} catch (e) {
  console.error(e); setDot('bad'); setSub('Error'); $('camTxt').textContent = 'Anatomy or 3D could not be loaded. Serve the page from a local server (see README) and use a browser with WebGL.';
}

/* ---------- API for connecting health data ---------- */
window.AstroBody = {
  build: BUILD, ask,
  groups: lobby ? lobby.groups : [], systems: Object.keys(SYSTEM_GROUPS), vitals: VITALS.map(v => v.id), indicators: Object.keys(INDICATORS),
  setLayer, setLook,
  /** setVital('hr',{value:96,status:'warn',text:'Elevated',history:[...]}) status: 'ok' | 'watch' | 'warn' | 'alert' | null */
  setVital, setEnvironment, setPredictions,
  /** setMeasurements({'hr.rest':71,'urine.volumeL':1.4,'bmd.hipPct':-6,'mission.month':4}) — keys: see AstroBody.indicators. Re-rates every part. */
  setMeasurements,
  /** Tints one anatomy group or a whole system manually. */
  setGroupStatus, setSystemStatus,
  select: selectPart, deselect,
  /** Evaluated state for every part: {status, level, warnings, notes, indicators} */
  getParts: () => parts,
  /** loadSample('nominal' | 'mixed' | 'critical') loads invented test data; AstroBody.scenarios lists them. */
  loadSample, clearSample, scenarios: SCENARIO_IDS,
  /** setBody({sex: 'f', heightCm: 178, massKg: 74}): sex 'f' | 'm', 150 to 205 cm, 45 to 130 kg; setBody(null) resets it. */
  setBody,
  /** setActivity('rest' | 'sleep' | 'work' | 'exercise' | 'eva' | 'auto' | null); startLive() and stopLive() control the simulated wearable stream. */
  setActivity, startLive, stopLive, activities: ACTIVITY_IDS,
  /** Sleep / Exercise / Nutrition scores: {sleep:{score,coverage,items}, ...}. Inputs: AstroBody.scoreInputs */
  getScores: () => scoreAll(currentInput()), scoreInputs: SCORE_KEYS, setView,
  _state: state, _lobby: () => lobby
};

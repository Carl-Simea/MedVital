import { createLobby } from './lobby.js';
import { PARTS, PAIRED, SRC, BASIS, LEVEL, LEVEL_NAME, LEVEL_LABEL, INDICATORS, SAMPLE, evaluate, bodyColors, summarize } from './parts.mjs';
import { answer as assistantAnswer, SUGGESTIONS } from './assistant.mjs';
import { DOMAIN_IDS, SCORE_KEYS, SCORE_SRC, SCORE_SAMPLE, SCORE_INPUTS, scoreAll, scoreColor, scoreWord } from './scores.mjs';
import { extract, READABLE } from './intake.mjs';
const ALL_SRC = { ...SRC, ...SCORE_SRC };

const BUILD = 'v3.5 · 14 Nov 2026';
const errLog = [];
const logErr = m => { errLog.push(new Date().toISOString().slice(11, 19) + ' ' + String(m).slice(0, 200)); if (errLog.length > 20) errLog.shift(); };
addEventListener('error', e => logErr(e.message + ' @' + (e.filename || '').split('/').pop() + ':' + e.lineno));
addEventListener('unhandledrejection', e => logErr('promise: ' + (e.reason && e.reason.message || e.reason)));

const $ = id => document.getElementById(id);
const state = { vital: 'hr', look: 'solid', layer: 'bone', sample: false, sel: null };
let M = {};                                  // current measurements (keys of INDICATORS)
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
  if (In['pvt.lapses'] === undefined && F.pvt && F.pvt.score && typeof F.pvt.score.lapses === 'number') In['pvt.lapses'] = F.pvt.score.lapses;
  if (In['mission.month'] === undefined && F.bone && F.bone.detail) In['mission.month'] = F.bone.detail.avg[0];
  return In;
}
const manual = {};                           // legacy overrides from setGroupStatus / setSystemStatus
function recompute() {
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
  renderAttention(); renderTiles(); renderScores(); if (state.sel) renderCard(); if (typeof assistantStatus === 'function') assistantStatus();
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
  { id: 'hr', label: 'Heart rate', unit: 'bpm', key: 'hr.rest', group: 'heart', layer: 'organ' },
  { id: 'bp', label: 'Blood pressure', unit: 'mmHg', key: 'bp.sys', group: 'artery', layer: 'organ', val: M => (num(M['bp.sys']) && num(M['bp.dia']) ? `${M['bp.sys']}/${M['bp.dia']}` : undefined), base: M => M['bp.sys'] },
  { id: 'spo2', label: 'Blood oxygen', unit: '%', key: 'spo2.pct', group: 'lung', layer: 'organ' },
  { id: 'resp', label: 'Breathing', unit: '/min', key: 'resp.rate', group: 'lung', layer: 'organ' },
  { id: 'temp', label: 'Temperature', unit: '°C', key: 'temp.c', group: 'body' },
  { id: 'glucose', label: 'Blood glucose', unit: 'mg/dL', key: 'glucose.mgdl', group: 'liver', layer: 'organ' },
  { id: 'rt', label: 'Reaction time', unit: 'ms', key: 'pvt.lapses', group: 'brain', layer: 'organ', val: M => M['pvt.meanRtMs'] },
  { id: 'sleep', label: 'Sleep', unit: 'h', key: 'sleep.hours', group: 'brain', layer: 'organ' },
  { id: 'pain', label: 'Back pain', unit: '/10', key: 'back.pain', group: 'spineL', layer: 'bone' },
  { id: 'hgb', label: 'Hemoglobin', unit: 'g/dL', key: 'hemoglobin.gdl', group: 'spleen', layer: 'organ' },
  { id: 'urine', label: 'Urine volume', unit: 'L/day', key: 'urine.volumeL', group: 'kidney', layer: 'organ' },
  { id: 'mass', label: 'Body mass', unit: '% vs. pre', key: 'mass.changePct', group: 'body' },
  { id: 'rad', label: 'Radiation', unit: 'mSv', key: 'radiation.careerMsv', group: 'body' },
  { id: 'hip', label: 'Hip bone', unit: '% vs. pre', key: 'bmd.hipPct', group: 'femur', layer: 'bone' },
  { id: 'str', label: 'Strength', unit: '% vs. pre', key: 'strength.changePct', group: 'mThigh', layer: 'muscle' },
  { id: 'vitd', label: 'Vitamin D', unit: 'ng/mL', key: 'vitd.ngml', group: 'body' }
];
const vitals = {}; const resetVitals = () => { for (const v of VITALS) vitals[v.id] = { value: null, status: null, text: 'No data', history: [] }; }; resetVitals();
let activeView = 'overview';
const viewGroups = {sleep:['sleep','rt'],exercise:['str','hr','hip','pain'],nutrition:['mass','glucose','vitd','hgb']};
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
  const box = $('tiles'); box.innerHTML = '';
  for (const v of VITALS.filter(v => !viewGroups[activeView] || viewGroups[activeView].includes(v.id))) {
    const s = vitals[v.id], b = document.createElement('button'); b.className = 'tile' + (state.vital === v.id ? ' sel' : '');
    b.innerHTML = '<span class="tl"></span><span class="td"></span><span class="tv"></span><span class="ts"></span>';
    b.querySelector('.tl').textContent = v.label; b.querySelector('.ts').textContent = s.text;
    b.querySelector('.td').className = 'td ' + (s.status || '');
    const tv = b.querySelector('.tv'); tv.textContent = s.value === null ? '–' : s.value;
    if (s.value !== null) { const u = document.createElement('small'); u.textContent = v.unit; tv.appendChild(u); }
    if (s.history.length > 2 && v.unit.length < 6) {
      const h = s.history, mn = Math.min(...h), mx = Math.max(...h), sp = (mx - mn) || 1;
      const pts = h.map((x, i) => `${(i / (h.length - 1) * 60).toFixed(1)},${(18 - (x - mn) / sp * 16).toFixed(1)}`).join(' ');
      b.insertAdjacentHTML('beforeend', `<svg class="spark" viewBox="0 0 60 20" aria-hidden="true"><polyline points="${pts}"/></svg>`);
    }
    b.onclick = () => selectVital(v.id);
    box.appendChild(b);
  }
}
function selectVital(id) {
  state.vital = id; const v = VITALS.find(x => x.id === id);
  if (v.layer) setLayer(v.layer); selectPart(v.group); renderPast();
}

/* ---------- Past data + upcoming (right) ---------- */
function renderPast() {
  const v = VITALS.find(x => x.id === state.vital), h = vitals[v.id].history;
  $('pastSub').textContent = h.length ? `${v.label} · last ${h.length} days` : v.label;
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
  const box = $('attn'); box.innerHTML = '';
  const { counts, attention } = summarize(parts);
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
  top.append(back, el('h2', '', partName(sel.group, sel.side)), pill); card.append(top);
  card.append(el('p', 'does', def.does));
  if (st.warnings.length) {
    card.append(el('h3', '', 'Warnings'));
    for (const w of st.warnings) {
      const li = el('div', 'warnli lv' + w.level, w.text); const m = el('span', 'meta', BASIS[w.basis] || ''); if (w.src) { m.append(document.createTextNode(' · ')); const a = srcLink(w.src); if (a) m.append(a); } li.append(m); card.append(li);
    }
  } else if (st.level === LEVEL.nodata) {
    card.append(el('div', 'gap', def.ind.length ? 'No data for this part yet. It is rated from: ' + def.ind.map(k => INDICATORS[k].label.toLowerCase()).join(', ') + '.' : 'No indicator is connected to this part, so it cannot be rated.'));
  } else card.append(el('div', 'gap', 'No warning in the data entered.'));
  if (st.level >= 2) card.append(el('div', 'gap', st.level >= 3 ? 'Contact the flight surgeon now.' : 'Re-measure, then tell the flight surgeon at the next contact.'));
  if (st.notes.length) { card.append(el('h3', '', 'In range')); const ul = el('ul'); for (const n of st.notes) { const li = el('li', '', n.text); ul.append(li); } card.append(ul); }
  if (def.ind.length) {
    card.append(el('h3', '', 'Indicators NASA tracks'));
    const g = el('div', 'ind');
    for (const i of st.indicators) {
      const v = i.value === null ? '–' : typeof i.value === 'boolean' ? (i.value ? 'yes' : 'no') : `${i.value}${i.unit ? ' ' + i.unit : ''}`;
      g.append(el('span', '', i.label), el('b', '', v), el('small', '', i.how + (i.flight ? ' · measurable in flight' : ' · not measurable in flight') + (i.why ? '. Why: ' + i.why : '')));
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
  state.sel = { group: i.group, side: PAIRED.includes(i.group) ? i.side : null, pid: i.pid }; $('hint').classList.add('gone'); renderCard();
}
const tip = $('tip');
function onHover(i, x, y) {
  if (!i) { tip.hidden = true; return; }
  const r = $('cam').getBoundingClientRect(), st = parts[i.group];
  tip.hidden = false; tip.style.left = (x - r.left) + 'px'; tip.style.top = (y - r.top) + 'px';
  tip.textContent = partName(i.group, i.side);
  const s = document.createElement('small'); s.textContent = st.statusLabel; tip.append(s);
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
    const value = d.val ? d.val(M) : M[d.key]; if (value === undefined || value === null) continue;
    const lv = keyLevel(d.key), s = vitals[d.id], base = d.base ? d.base(M) : value;
    s.value = value; s.status = levelToUi(lv);
    s.text = d.id === 'rt' && num(M['pvt.lapses']) ? `${M['pvt.lapses']} lapses · ${TXT(lv)}` : TXT(lv);
    if (withHistory && num(Number(base))) s.history = sampleSeries(d.id.length * 7 + d.unit.length, Number(base), Math.max(Math.abs(Number(base)) * 0.04, 0.6), 14).map(v => (d.id === 'pain' ? Math.max(0, Math.min(10, Math.round(v))) : v));
  }
  renderTiles(); renderPast();
}
function setMeasurements(obj, opts = {}) {
  for (const k in obj) {
    if (k === 'mission.month' || k === 'sex' || k === 'pvt.confirmed' || k === 'pvt.meanRtMs' || INDICATORS[k] || SCORE_KEYS.includes(k)) M[k] = obj[k];
  }
  recompute(); syncTiles(!!opts.history); return true;
}
function loadSample() {
  M = {}; state.sample = true; setMeasurements({ ...SAMPLE, ...SCORE_SAMPLE }, { history: true });
  envItems = [{ text: 'Radiation background nominal', note: 'Sample' }, { text: 'Cabin CO₂ within limits', note: 'Sample' }, { text: 'Space weather quiet', note: 'Sample' }];
  predItems = [{ text: 'Hip and lumbar bone density on track for month 4 (model)', note: 'Sample' }, { text: 'Watch urine volume: stone risk', note: 'Sample' }];
  renderUpcoming(); $('sampleChip').hidden = false; $('sampleBtn').textContent = 'Clear sample data';
  if (lobby) lobby.setHeartRate(M['hr.rest']);
}
function clearSample() {
  M = {}; state.sample = false; resetVitals(); envItems = []; predItems = [];
  $('sampleChip').hidden = true; $('sampleBtn').textContent = 'Load sample data';
  recompute(); renderTiles(); renderPast(); renderUpcoming();
}
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
$('sampleBtn').onclick = () => (state.sample ? clearSample() : loadSample());
$('bBody').onclick = () => selectPart('body');
$('bReset').onclick = () => { deselect(); if (lobby) lobby.resetView(); };
const openSheet = o => { $('ov').hidden = !o; }; $('setBtn').onclick = () => openSheet(true); $('setDone').onclick = () => openSheet(false);
$('ov').onclick = e => { if (e.target === $('ov')) openSheet(false); };
const opf = () => { $('vOp').textContent = $('rOp').value + ' %'; if (lobby) lobby.setOpacity(+$('rOp').value / 100); }; $('rOp').oninput = opf; opf();
addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
  const m = { '1': 'bone', '2': 'organ', '3': 'muscle', '4': 'all' }[e.key]; if (m) setLayer(m);
  if (e.key === 'x') setLook(state.look === 'xray' ? 'solid' : 'xray');
  if (e.key === 'Escape') deselect();
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
    pointer: L ? L.stats : null, errors: errLog, measurements: M, counts: summarize(parts).counts, sample: state.sample,
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

/* ---------- Assistant (rule-based, reads the crew member's own data) ---------- */
const asst = { greeted: false, rec: null };
const log = $('alog');
function say(who, text) {
  const d = el('div', 'msg ' + who); for (const [i, line] of String(text).split('\n').entries()) { if (i) d.append(document.createElement('br')); d.append(document.createTextNode(line)); }
  log.append(d); log.scrollTop = log.scrollHeight;
}
function chips(list) { const c = $('achips'); c.innerHTML = ''; for (const t of list || []) { const b = el('button', '', t); b.type = 'button'; b.onclick = () => ask(t); c.append(b); } }
function assistantStatus() {
  const { counts, attention } = summarize(parts), total = Object.keys(parts).length;
  $('asSub').textContent = counts.nodata === total ? 'No data yet' : attention.length ? `${attention.length} need attention` : 'All in range';
  $('asBtn').classList.toggle('dotted', attention.some(a => a.level >= 2));
}
function ask(q) {
  q = String(q || '').trim(); if (!q) return; showDock('assistant'); say('me', q); $('asIn').value = '';
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
/* ---------- Right dock: data input and assistant ---------- */
function showDock(tab) {
  document.querySelectorAll('[data-dock]').forEach(b => b.setAttribute('aria-selected', String(b.dataset.dock === tab)));
  $('inPane').hidden = tab !== 'input'; $('asPane').hidden = tab !== 'assistant';
  if (tab === 'assistant') {
    if (!asst.greeted) { asst.greeted = true; say('bot', 'I read your own health data and explain it with sources. Type, or tap the microphone.'); const r = assistantAnswer('how am i doing', { parts, M: currentInput() }); say('bot', r.text); chips(r.chips); }
    setTimeout(() => $('asIn').focus(), 30);
  } else setTimeout(() => $('inText').focus(), 30);
}
document.querySelectorAll('[data-dock]').forEach(b => b.onclick = () => showDock(b.dataset.dock));
$('asBtn').onclick = () => showDock('assistant');

const KEY_LABEL = { 'mission.month': ['Mission month', ''], 'pvt.meanRtMs': ['Mean reaction time', 'ms'] };
const keyInfo = k => KEY_LABEL[k] || (INDICATORS[k] ? [INDICATORS[k].label, INDICATORS[k].unit] : SCORE_INPUTS[k] ? [SCORE_INPUTS[k].label, SCORE_INPUTS[k].unit] : [k, '']);
const fmtVal = (k, v) => (typeof v === 'boolean' ? (v ? 'yes' : 'no') : `${v}${keyInfo(k)[1] ? ' ' + keyInfo(k)[1] : ''}`);
const inLog = $('inLog');
function inMsg(who, node) { const d = el('div', 'msg ' + who); if (typeof node === 'string') d.textContent = node; else d.append(node); inLog.append(d); inLog.scrollTop = inLog.scrollHeight; return d; }
inMsg('bot', 'Paste a medical report, lab results or a device export (text, CSV or JSON), or drop the file here. I show what I found before anything changes.');
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
    list.querySelectorAll('input').forEach(c => { c.disabled = true; }); act.replaceWith(el('p', 'done', `Applied ${n} value${n > 1 ? 's' : ''} · ${new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}`));
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
$('inForm').onsubmit = e => { e.preventDefault(); const t = $('inText').value; if (!t.trim()) return; $('inText').value = ''; fitIn(); readSource(t); };
const fitIn = () => { const t = $('inText'); t.style.height = 'auto'; t.style.height = Math.min(t.scrollHeight, 140) + 'px'; };
$('inText').oninput = fitIn;
$('inText').onkeydown = e => { e.stopPropagation(); if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); $('inForm').requestSubmit(); } };
$('inFile').onchange = e => { readFiles([...e.target.files]); e.target.value = ''; };
{ const dock = $('dock'), drop = $('drop'); let depth = 0;
  dock.addEventListener('dragenter', e => { if (![...e.dataTransfer.types].includes('Files')) return; e.preventDefault(); depth++; drop.hidden = false; showDock('input'); });
  dock.addEventListener('dragover', e => { if ([...e.dataTransfer.types].includes('Files')) e.preventDefault(); });
  dock.addEventListener('dragleave', () => { if (--depth <= 0) { depth = 0; drop.hidden = true; } });
  dock.addEventListener('drop', e => { e.preventDefault(); depth = 0; drop.hidden = true; readFiles([...e.dataTransfer.files]); }); }
$('asForm').onsubmit = e => { e.preventDefault(); ask($('asIn').value); };
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
if (!SR) $('asMic').hidden = true;
$('asMic').onclick = () => {
  if (asst.rec) { asst.rec.stop(); return; }
  const r = new SR(); asst.rec = r; r.lang = 'en-US'; r.interimResults = false; r.maxAlternatives = 1;
  $('asMic').classList.add('rec');
  r.onresult = e => { const t = e.results[0][0].transcript; $('asIn').value = t; ask(t); };
  r.onerror = e => { say('bot', e.error === 'not-allowed' ? 'Microphone access was denied. Allow it in the browser settings.' : 'Voice input failed (' + e.error + '). Browsers send speech to an online service, so it needs an internet connection.'); };
  r.onend = () => { asst.rec = null; $('asMic').classList.remove('rec'); };
  try { r.start(); } catch (e) { asst.rec = null; $('asMic').classList.remove('rec'); }
};

/* ---------- Start ---------- */
renderTiles(); renderPast(); renderUpcoming(); renderAttention();
try {
  lobby = await createLobby($('gl'), { paired: PAIRED, onPick, onHover });
  lobby.setLook(state.look); lobby.setLayer(state.layer); lobby.setOpacity(+$('rOp').value / 100);
  $('camMsg').classList.add('hide'); setSub(BUILD); setDot('ok');
  recompute();
  setTimeout(() => $('hint').classList.add('gone'), 9000);
  if (location.hash === '#sample') loadSample();
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
  loadSample, clearSample,
  /** Sleep / Exercise / Nutrition scores: {sleep:{score,coverage,items}, ...}. Inputs: AstroBody.scoreInputs */
  getScores: () => scoreAll(currentInput()), scoreInputs: SCORE_KEYS, setView,
  _state: state, _lobby: () => lobby
};

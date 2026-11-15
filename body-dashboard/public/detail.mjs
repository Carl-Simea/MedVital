/* detail.mjs — the detailed sections under the tiles of each left-column view:
     Overview   every measurement, grouped into panels (blood count, chemistry, … cognition), with range bars
     Sleep      hypnogram (stages over the night), stage shares, sleep continuity values
     Exercise   week by device, heart-rate zones, fitness and sensorimotor tests
     Nutrition  energy, macronutrient split, micronutrient intake, nutrition markers in blood and urine
   Only DOM building; all ratings come from parts.mjs (the same findings that colour the body). */
import { INDICATORS } from './parts.mjs';
import { PANELS, CATALOG, CATALOG_BY_KEY, refRange, farRange, hypnogram } from './panels.mjs';

const num = v => typeof v === 'number' && Number.isFinite(v);
const LV = ['ok', 'watch', 'warn', 'alert'];
const h = (tag, cls, txt) => { const e = document.createElement(tag); if (cls) e.className = cls; if (txt !== undefined) e.textContent = txt; return e; };
const fmt = v => (typeof v === 'boolean' ? (v ? 'Yes' : 'No') : typeof v === 'number' ? (Math.abs(v) >= 100 ? Math.round(v) : Math.round(v * 100) / 100).toLocaleString('en-US') : String(v));

/* The core indicators (parts.mjs) placed into the same panels as the catalogue */
const CORE_PANEL = {
  'hemoglobin.gdl': 'blood', 'hematocrit.pct': 'blood', 'wbc.k': 'blood', 'platelets.k': 'blood',
  'sodium.mmol': 'chem', 'potassium.mmol': 'chem', 'creatinine.mgdl': 'chem', 'calcium.mgdl': 'chem',
  'glucose.mgdl': 'lipid', 'ferritin.ngml': 'iron', 'cortisol.ugdl': 'endo', 'crp.mgl': 'immune', 'virus.shedding': 'immune', 'zoster.symptoms': 'immune',
  'vitd.ngml': 'vit', 'urine.volumeL': 'urine', 'urine.calciumMgDay': 'urine', 'urine.citrateMgDay': 'urine', 'urine.ph': 'urine', 'kidney.stone': 'stone',
  'hr.rest': 'cardio', 'bp.sys': 'cardio', 'bp.dia': 'cardio', 'cimt.mm': 'cardio', 'orthostatic.presyncope': 'cardio', 'jugular.flow': 'cardio', 'hrv.rmssdMs': 'cardio',
  'spo2.pct': 'lungF', 'resp.rate': 'lungF', 'temp.c': 'fluidP', 'skin.tempC': 'fluidP', 'mass.changePct': 'fluidP',
  'sans.hyperopicShiftD': 'eyeP', 'sans.discEdema': 'eyeP', 'sans.choroidalFolds': 'eyeP', 'sans.trtChangeUm': 'eyeP',
  'bmd.hipPct': 'musc', 'bmd.lumbarPct': 'musc', 'bmd.wholeBodyPct': 'musc', 'back.pain': 'musc', 'strength.changePct': 'musc', 'aerobic.changePct': 'exTest',
  'balance.changePct': 'sensori', 'motion.sickness': 'sensori', 'cognition.scorePct': 'cog', 'pvt.lapses': 'cog',
  'stress.score': 'behav', 'mood.score': 'behav', 'eda.uS': 'behav', 'radiation.careerMsv': 'behav', 'radiation.eventMsv': 'behav', 'radiation.rateUsvH': 'behav',
  'sleep.hours': 'sleepArch', 'sleep.efficiencyPct': 'sleepArch'
};
const panelOf = k => (CATALOG_BY_KEY[k] ? CATALOG_BY_KEY[k].panel : CORE_PANEL[k]);
const GROUP_OF = Object.fromEntries(CATALOG.map(x => [x.key, x.groups[0]]));

/** Worst finding level for one indicator key, across all body parts (-1 = no finding / not rated). */
function levelOf(parts, key) {
  let lv = -1, text = '';
  for (const g in parts) for (const x of [...parts[g].warnings, ...parts[g].notes]) if (x.key === key && x.level > lv) { lv = x.level; text = x.text; }
  return { lv, text };
}
const groupOf = (parts, key) => GROUP_OF[key] || Object.keys(parts).find(g => parts[g].indicators.some(i => i.key === key)) || null;

/** One measurement row: name, value, status dot, range bar (if there is a usual range). */
function row(key, M, parts, onPick, labelOverride) {
  const ind = INDICATORS[key] || {}, x = CATALOG_BY_KEY[key], v = M[key], st = levelOf(parts, key);
  const r = h('button', 'mrow' + (v === undefined ? ' empty' : '')); r.type = 'button';
  const dot = h('i', 'mdot ' + (st.lv >= 0 ? LV[st.lv] : ind.rate === false ? 'track' : 'none'));
  const name = h('span', 'mname', labelOverride || ind.label || key);
  const val = h('span', 'mval'); val.append(h('b', '', v === undefined ? '–' : fmt(v)), h('small', '', v === undefined ? '' : ind.unit || ''));
  r.append(dot, name, val);
  const rr = x ? refRange(x, M) : null;
  if (rr && num(v)) {
    const fr = (x && farRange(x, M)) || [rr[0] - (rr[1] - rr[0]) * 0.5, rr[1] + (rr[1] - rr[0]) * 0.5];
    let lo = Math.min(fr[0], rr[0]), hi = Math.max(fr[1], rr[1]);
    if (!Number.isFinite(lo)) lo = rr[0] - (rr[1] - rr[0]); if (!Number.isFinite(hi)) hi = rr[1] + (rr[1] - rr[0]);
    const pos = t => Math.max(0, Math.min(100, (t - lo) / (hi - lo) * 100));
    const bar = h('span', 'mbar'), zone = h('i', 'mzone'), mk = h('i', 'mmark ' + (st.lv >= 0 ? LV[st.lv] : 'ok'));
    zone.style.left = pos(rr[0]) + '%'; zone.style.width = Math.max(2, pos(rr[1]) - pos(rr[0])) + '%'; mk.style.left = pos(v) + '%';
    bar.append(zone, mk); r.append(bar);
    r.title = `Usual ${rr[0]} to ${rr[1]} ${ind.unit || ''}${st.text ? ' · ' + st.text : ''}`;
  } else {
    r.append(h('span', 'mnote', ind.rate === false ? 'not rated' : ''));
    r.title = st.text || (ind.rate === false ? 'Shown and tracked; no verified threshold, so it is not rated.' : '');
  }
  const g = groupOf(parts, key); if (g && onPick) r.onclick = () => onPick(g);
  return r;
}

/* ---------- Overview: all panels ---------- */
const openPanels = new Set(['blood']);
function renderOverview(box, M, parts, onPick) {
  const keys = Object.keys(INDICATORS), byPanel = {};
  for (const k of keys) { const p = panelOf(k); if (p) (byPanel[p] = byPanel[p] || []).push(k); }
  const total = keys.filter(k => M[k] !== undefined).length;
  const head = h('div', 'dhead'); head.append(h('span', 'dkicker', 'ALL MEASUREMENTS'), h('b', '', `${total} of ${keys.length} values`));
  box.append(head);
  for (const p of PANELS) {
    const ks = byPanel[p.id]; if (!ks) continue;
    const lv = Math.max(-1, ...ks.map(k => levelOf(parts, k).lv)), have = ks.filter(k => M[k] !== undefined).length;
    const flagged = ks.filter(k => levelOf(parts, k).lv >= 1).length;
    const d = h('details', 'mpanel'); if (openPanels.has(p.id)) d.open = true;
    d.ontoggle = () => (d.open ? openPanels.add(p.id) : openPanels.delete(p.id));
    const s = h('summary'); s.append(h('i', 'mdot ' + (lv >= 0 ? LV[lv] : 'none')), h('span', 'pname', p.label), h('small', '', flagged ? `${flagged} to check · ${have}/${ks.length}` : `${have}/${ks.length}`));
    d.append(s); const list = h('div', 'plist2'); for (const k of ks) list.append(row(k, M, parts, onPick)); d.append(list); box.append(d);
  }
}

/* ---------- Sleep ---------- */
const STAGE = { W: { y: 0, c: '#e8eef2', n: 'Awake' }, R: { y: 1, c: '#b48cff', n: 'REM' }, 1: { y: 2, c: '#7fd3ff', n: 'N1' }, 2: { y: 3, c: '#3f8cff', n: 'N2' }, 3: { y: 4, c: '#2547b8', n: 'N3 deep' } };
function hypnoSvg(hy, M) {
  const ep = hy.epochs, W = 320, H = 118, L = 40, T = 8, rowH = 19, n = ep.length, dx = (W - L - 4) / n;
  const onset = num(M['sleep.onsetClock']) ? M['sleep.onsetClock'] : 23;
  let s = `<svg class="hypno" viewBox="0 0 ${W} ${H + 16}" role="img" aria-label="Sleep stages over the night">`;
  for (const k of ['W', 'R', '1', '2', '3']) { const y = T + STAGE[k].y * rowH; s += `<text x="0" y="${y + 13}" class="hyl">${STAGE[k].n}</text><line x1="${L}" x2="${W}" y1="${y + rowH / 2}" y2="${y + rowH / 2}" class="hyg"/>`; }
  // coloured blocks per run of the same stage, plus a step line
  let i = 0, path = '';
  while (i < n) {
    let j = i; while (j < n && ep[j] === ep[i]) j++;
    const st = STAGE[ep[i]], x = L + i * dx, w = (j - i) * dx, y = T + st.y * rowH;
    s += `<rect x="${x.toFixed(1)}" y="${(y + 3).toFixed(1)}" width="${Math.max(0.8, w).toFixed(1)}" height="${rowH - 6}" rx="2" fill="${st.c}" opacity="${ep[i] === 'W' ? .55 : .9}"/>`;
    path += `${i ? 'L' : 'M'}${x.toFixed(1)},${(y + rowH / 2).toFixed(1)} L${(x + w).toFixed(1)},${(y + rowH / 2).toFixed(1)} `;
    i = j;
  }
  s += `<path d="${path}" class="hyp"/>`;
  const hours = n / 12;
  for (let t = 0; t <= hours + 0.01; t += hours > 7 ? 2 : 1) {
    const x = L + t * 12 * dx, clock = ((onset + t) % 24 + 24) % 24;
    s += `<text x="${x.toFixed(1)}" y="${H + 12}" class="hyx">${String(Math.floor(clock)).padStart(2, '0')}:${String(Math.round((clock % 1) * 60)).padStart(2, '0')}</text>`;
  }
  return s + '</svg>';
}
function renderSleep(box, M, parts, onPick) {
  const head = h('div', 'dhead'); head.append(h('span', 'dkicker', 'LAST NIGHT'), h('b', '', 'Sleep stages')); box.append(head);
  const hy = hypnogram(M);
  if (hy) {
    const card = h('div', 'dcard'); card.innerHTML = hypnoSvg(hy, M);
    card.append(h('p', 'dnote', hy.real ? 'Stages per 5 minutes from the sleep recording.' : 'Night reconstructed from the summary values (stage shares, time to fall asleep, awakenings): the order follows typical adult sleep, deep sleep early and REM towards morning. Real epoch data replaces it.'));
    box.append(card);
  } else box.append(h('p', 'dnote', 'No sleep recording yet. Load test data or enter time in bed, sleep time and stage shares.'));
  // stage shares bar
  const tst = num(M['sleep.hours']) ? M['sleep.hours'] * 60 : null, sh = { R: M['sleep.remPct'], 1: M['sleep.n1Pct'], 2: M['sleep.n2Pct'], 3: M['sleep.n3Pct'] };
  if (Object.values(sh).every(num)) {
    const card = h('div', 'dcard'), bar = h('div', 'stbar'), leg = h('div', 'stleg');
    for (const k of ['3', '2', '1', 'R']) {
      const seg = h('i'); seg.style.flex = sh[k]; seg.style.background = STAGE[k].c; seg.title = `${STAGE[k].n} ${sh[k]} %`; bar.append(seg);
      const li = h('span'); li.innerHTML = `<i style="background:${STAGE[k].c}"></i>`; li.append(`${STAGE[k].n} ${sh[k]} %${tst ? ' · ' + Math.round(tst * sh[k] / 100) + ' min' : ''}`); leg.append(li);
    }
    card.append(h('b', 'dsub', 'Share of total sleep'), bar, leg); box.append(card);
  }
  const card = h('div', 'dcard'); card.append(h('b', 'dsub', 'Stages and continuity'));
  for (const k of ['sleep.remPct', 'sleep.n3Pct', 'sleep.n2Pct', 'sleep.n1Pct', 'sleep.latencyMin', 'sleep.wasoMin', 'sleep.awakenings', 'sleep.efficiencyPct', 'sleep.hours', 'sleep.inBedH', 'sleep.remLatencyMin', 'sleep.cycles', 'sleep.onsetClock', 'sleep.lightLux', 'pvt.lapses'])
    if (INDICATORS[k]) card.append(row(k, M, parts, onPick));
  box.append(card);
}

/* ---------- Exercise ---------- */
const DEV = [['ex.aredMin', 'ARED resistive', '#5fe3d0'], ['ex.cevisMin', 'CEVIS cycle', '#ffb547'], ['ex.t2Min', 'T2 treadmill', '#7aa2ff']];
const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const SPLIT = { 'ex.aredMin': [1, 0, 1, 0, 1, 1, 0], 'ex.cevisMin': [0, 1, 0, 1, 0, 1, 0], 'ex.t2Min': [1, 1, 0, 1, 1, 0, 0] };
function renderExercise(box, M, parts, onPick) {
  const head = h('div', 'dhead'); head.append(h('span', 'dkicker', 'THIS WEEK'), h('b', '', 'Training by device')); box.append(head);
  if (DEV.some(([k]) => num(M[k]))) {
    const card = h('div', 'dcard'), daysEl = h('div', 'wk'), per = DAYS.map(() => ({}));
    for (const [k] of DEV) { const tot = M[k] || 0, w = SPLIT[k], n = w.reduce((a, b) => a + b, 0); DAYS.forEach((_, d) => { per[d][k] = w[d] ? tot / n : 0; }); }
    const mx = Math.max(...per.map(p => Object.values(p).reduce((a, b) => a + b, 0)), 1);
    per.forEach((p, d) => {
      const col = h('div', 'wkd'), st = h('div', 'wks');
      for (const [k, , c] of DEV) if (p[k]) { const seg = h('i'); seg.style.height = (p[k] / mx * 100) + '%'; seg.style.background = c; seg.title = `${Math.round(p[k])} min`; st.append(seg); }
      col.append(st, h('small', '', DAYS[d])); daysEl.append(col);
    });
    const leg = h('div', 'stleg');
    for (const [k, n, c] of DEV) { const li = h('span'); li.innerHTML = `<i style="background:${c}"></i>`; li.append(`${n} ${num(M[k]) ? M[k] : '–'} min`); leg.append(li); }
    card.append(daysEl, leg, h('p', 'dnote', 'Daily split estimated from the weekly device totals; a device log replaces it.')); box.append(card);
  }
  const zones = [['ex.z2Min', 'Moderate zone'], ['ex.z4Min', 'Hard zone']].filter(([k]) => num(M[k]));
  if (zones.length) {
    const card = h('div', 'dcard'); card.append(h('b', 'dsub', 'Heart-rate zones'));
    const mx = Math.max(...zones.map(([k]) => M[k]), 1);
    for (const [k, n] of zones) { const r = h('div', 'zrow'), b = h('span', 'zbar'), f = h('i'); f.style.width = (M[k] / mx * 100) + '%'; b.append(f); r.append(h('span', '', n), b, h('b', '', M[k] + ' min')); card.append(r); }
    box.append(card);
  }
  const groups = [['Fitness tests', ['ex.vo2peak', 'aerobic.changePct', 'ex.wattPeak', 'ex.hrPeak', 'ex.rpe', 'ex.squatKg', 'strength.changePct', 'exercise.minPerWeek', 'exercise.resistiveDays']],
    ['Muscle and bone', ['muscle.volThighPct', 'muscle.volCalfPct', 'bmd.femNeckPct', 'bmd.hipPct', 'bmd.lumbarPct', 'bone.tibiaStrengthPct', 'back.pain']],
    ['Balance and motor control', ['sts.sec', 'tandem.pct', 'prone.sec', 'finemotor.pct', 'balance.changePct', 'motion.sickness']]];
  for (const [t, ks] of groups) { const card = h('div', 'dcard'); card.append(h('b', 'dsub', t)); for (const k of ks) if (INDICATORS[k]) card.append(row(k, M, parts, onPick)); box.append(card); }
}

/* ---------- Nutrition ---------- */
function renderNutrition(box, M, parts, onPick) {
  const head = h('div', 'dhead'); head.append(h('span', 'dkicker', 'TODAY'), h('b', '', 'Energy and nutrients')); box.append(head);
  if (num(M['nut.kcal'])) {
    const card = h('div', 'dcard'), pct = M['nutrition.energyPct'];
    const big = h('div', 'kcal'); big.append(h('b', '', Math.round(M['nut.kcal']).toLocaleString('en-US')), h('small', '', 'kcal'), h('span', '', num(pct) ? `${pct} % of need` : ''));
    const g = h('span', 'zbar'), f = h('i'); f.style.width = Math.min(100, num(pct) ? pct / 1.5 : 0) + '%'; f.className = num(pct) && (pct < 90 || pct > 115) ? 'off' : ''; g.append(f);
    const tgt = h('i', 'ztgt'); tgt.style.left = (100 / 1.5) + '%'; g.append(tgt);
    card.append(big, g, h('p', 'dnote', 'The line marks 100 % of the energy requirement.'));
    box.append(card);
  }
  const mac = [['nut.carbPct', 'Carbohydrate', '#ffb547', [45, 65]], ['nut.fatPct', 'Fat', '#ff7aa8', [20, 35]], ['nut.proteinPct', 'Protein', '#5fe3d0', [10, 35]]];
  if (mac.every(([k]) => num(M[k]))) {
    const card = h('div', 'dcard'), bar = h('div', 'stbar'), leg = h('div', 'stleg');
    for (const [k, n, c, r] of mac) {
      const seg = h('i'); seg.style.flex = M[k]; seg.style.background = c; bar.append(seg);
      const li = h('span'); li.innerHTML = `<i style="background:${c}"></i>`; li.append(`${n} ${M[k]} % (range ${r[0]}–${r[1]})`); leg.append(li);
    }
    card.append(h('b', 'dsub', 'Macronutrient split of energy'), bar, leg); box.append(card);
  }
  const groups = [['Intake', ['nutrition.proteinGkg', 'nutrition.fluidL', 'nut.fiberG', 'nut.omega3G', 'nut.sodiumMg', 'nut.potassiumMg', 'nut.calciumMg', 'nut.vitdIU', 'nut.ironMg', 'nut.folateUg', 'nut.vitkUg', 'nut.caffeineMg']],
    ['Markers in blood and urine', ['vitd.ngml', 'ferritin.ngml', 'iron.ugdl', 'tsat.pct', 'folate.ngml', 'b12.pgml', 'vite.mgl', 'vitk.ngml', 'homocysteine.umol', 'albumin.gdl', 'ohdg.ngmg', 'pgf2a.ngmg', 'urine.sodiumMmol', 'mass.changePct']]];
  for (const [t, ks] of groups) { const card = h('div', 'dcard'); card.append(h('b', 'dsub', t)); for (const k of ks) if (INDICATORS[k]) card.append(row(k, M, parts, onPick)); box.append(card); }
}

let sig = '';
/** Draws the detail section of a view. Rebuilds only when the values or the view changed (live ticks do not flicker). */
export function renderDetail(box, view, M, parts, onPick) {
  if (!box) return;
  const s = view + '|' + JSON.stringify(M, (k, v) => (k === 'hr.now' || k === 'hrv.rmssdMs' || k === 'skin.tempC' || k === 'eda.uS' || k === 'radiation.rateUsvH' || k === 'resp.rate' ? undefined : v));
  if (s === sig) return; sig = s;
  const y = box.parentElement ? box.parentElement.scrollTop : 0;
  box.innerHTML = '';
  if (view === 'sleep') renderSleep(box, M, parts, onPick);
  else if (view === 'exercise') renderExercise(box, M, parts, onPick);
  else if (view === 'nutrition') renderNutrition(box, M, parts, onPick);
  else renderOverview(box, M, parts, onPick);
  if (box.parentElement) box.parentElement.scrollTop = y;
}
export const resetDetail = () => { sig = ''; };

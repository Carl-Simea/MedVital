/* scores.mjs — Sleep, Exercise and Nutrition scores (1–100) for MEDvital.
   Pure functions, no DOM: the same input always gives the same output. Runs in the browser and in Node.

   What the score is: a MEDvital model, not a NASA scale. Every component is rated 0–100 on a straight-line scale between
   anchor points; the anchors are NASA or peer-reviewed figures where one exists (`basis: 'reference'`, with `src`) and a
   general convention otherwise (`basis: 'convention'`). The domain score is the weighted mean of the components that have data.
   Components without data do not lower the score; they lower `coverage`, which is always shown next to the score. */

export const SCORE_SRC = Object.freeze({
  sleepBarger: { kind: 'primary', title: 'Barger et al., Lancet Neurology 2014: sleep deficiency in astronauts (8.5 h scheduled, about 6 h slept)', url: 'https://doi.org/10.1016/S1474-4422(14)70122-X' },
  exScott23:   { kind: 'primary', title: 'Scott et al., npj Microgravity 2023: ISS exercise countermeasures in 46 astronauts (about 600 min per week)', url: 'https://pmc.ncbi.nlm.nih.gov/articles/PMC9898566' },
  exSchedule:  { kind: 'primary', title: 'NASA JSC: ISS exercise schedule, 2.5 h per day on 6 days per week', url: 'https://ntrs.nasa.gov/api/citations/20090013286/downloads/20090013286.pdf' },
  nutReq:      { kind: 'primary', title: 'NASA JSC-67378: nutritional requirements for exploration missions', url: 'https://ntrs.nasa.gov/api/citations/20205008306/downloads/JSC67378%20Expl%20Nutr%20Reqs%20042020.pdf' }
});

const num = v => typeof v === 'number' && Number.isFinite(v);
/** Piecewise-linear scale through [value, score] anchor points (sorted by value); flat outside the ends. */
export function scale(points) {
  return v => {
    if (v <= points[0][0]) return points[0][1];
    for (let i = 1; i < points.length; i++) {
      const [x1, y1] = points[i], [x0, y0] = points[i - 1];
      if (v <= x1) return y0 + (y1 - y0) * (v - x0) / (x1 - x0);
    }
    return points[points.length - 1][1];
  };
}

/** Inputs that only the scores use (the other components reuse indicators from parts.mjs). */
export const SCORE_INPUTS = Object.freeze({
  'sleep.quality':          { label: 'Sleep quality', unit: '/5', min: 1, max: 5, step: 1 },
  'exercise.minPerWeek':    { label: 'Exercise time', unit: 'min/wk', min: 0, max: 1500, step: 10 },
  'exercise.resistiveDays': { label: 'Resistance days', unit: '/wk', min: 0, max: 7, step: 1 },
  'nutrition.energyPct':    { label: 'Energy intake', unit: '% of need', min: 0, max: 200, step: 1 },
  'nutrition.proteinGkg':   { label: 'Protein', unit: 'g/kg', min: 0, max: 4, step: 0.1 },
  'nutrition.fluidL':       { label: 'Fluid intake', unit: 'L/day', min: 0, max: 8, step: 0.1 }
});

const c = (key, label, unit, weight, target, fn, basis, src, edit) => ({ key, label, unit, weight, target, fn, basis, src, edit });
export const DOMAINS = Object.freeze({
  sleep: { label: 'Sleep', components: [
    c('sleep.hours', 'Sleep duration', 'h', 50, 'Target 8 h or more · 8.5 h are scheduled, crews average about 6 h',
      scale([[4, 0], [6, 50], [7, 80], [8, 100]]), 'reference', 'sleepBarger', { min: 0, max: 14, step: 0.1 }),
    c('pvt.lapses', 'Alertness test lapses', '', 30, 'Target 0 · 11 or more separated medium from high performance',
      scale([[0, 100], [11, 40], [20, 0]]), 'reference', 'pvtB', { min: 0, max: 60, step: 1 }),
    c('sleep.quality', 'Sleep quality', '/5', 20, 'Self-rated, 5 is best',
      scale([[1, 0], [5, 100]]), 'convention', null, SCORE_INPUTS['sleep.quality'])
  ] },
  exercise: { label: 'Exercise', components: [
    c('exercise.minPerWeek', 'Exercise time', 'min/wk', 30, 'Target about 600 min per week · ISS crews range 450 to 720',
      scale([[0, 0], [450, 75], [600, 100]]), 'reference', 'exScott23', SCORE_INPUTS['exercise.minPerWeek']),
    c('exercise.resistiveDays', 'Resistance days', '/wk', 20, 'Target 6 days per week',
      scale([[0, 0], [6, 100]]), 'reference', 'exSchedule', SCORE_INPUTS['exercise.resistiveDays']),
    c('strength.changePct', 'Strength vs. preflight', '%', 25, 'Target 0 % · ISS average loss is 10 to 12 %',
      scale([[-20, 0], [-10, 50], [0, 100]]), 'reference', 'fitnessRisk', { min: -60, max: 30, step: 1 }),
    c('aerobic.changePct', 'Aerobic fitness vs. preflight', '%', 25, 'Target 0 % · ISS average loss is 10 to 12 %',
      scale([[-20, 0], [-10, 50], [0, 100]]), 'reference', 'fitnessRisk', { min: -60, max: 30, step: 1 })
  ] },
  nutrition: { label: 'Nutrition', components: [
    c('nutrition.energyPct', 'Energy intake', '% of need', 30, 'Target 95 to 110 % of the requirement',
      scale([[50, 0], [95, 100], [110, 100], [150, 40]]), 'reference', 'nutrition', SCORE_INPUTS['nutrition.energyPct']),
    c('nutrition.proteinGkg', 'Protein', 'g/kg', 20, 'Target 1.2 to 1.8 g per kg body mass per day',
      scale([[0.4, 0], [1.2, 100], [1.8, 100], [2.6, 50]]), 'reference', 'nutReq', SCORE_INPUTS['nutrition.proteinGkg']),
    c('nutrition.fluidL', 'Fluid intake', 'L/day', 20, 'Target 2.5 L per day for men, 2.1 L for women',
      null, 'reference', 'nutReq', SCORE_INPUTS['nutrition.fluidL']),
    c('vitd.ngml', 'Vitamin D', 'ng/mL', 15, 'Target 30 ng/mL or more · below 20 is low',
      scale([[12, 0], [20, 50], [30, 100]]), 'convention', 'nutBone', { min: 0, max: 150, step: 1 }),
    c('mass.changePct', 'Body mass vs. preflight', '%', 15, 'Target stable body mass',
      scale([[-10, 0], [-5, 50], [-1, 100], [3, 100], [10, 40]]), 'convention', 'nutrition', { min: -30, max: 30, step: 0.1 })
  ] }
});
export const DOMAIN_IDS = Object.freeze(Object.keys(DOMAINS));
export const SCORE_KEYS = Object.freeze([...new Set(DOMAIN_IDS.flatMap(d => DOMAINS[d].components.map(x => x.key)))]);

function rate(comp, v, M) {
  if (comp.key === 'nutrition.fluidL') { const need = M.sex === 'f' ? 2.1 : 2.5; return scale([[1, 0], [need, 100]])(v); }
  return comp.fn(v);
}

/** → { id, label, score (1–100 or null), coverage: {have, total}, items: [{key,label,unit,value,score,weight,target,basis,src,edit}] } */
export function scoreDomain(id, M = {}) {
  const d = DOMAINS[id]; if (!d) return null;
  let sum = 0, w = 0, have = 0;
  const items = d.components.map(comp => {
    const v = M[comp.key], ok = num(v), s = ok ? Math.max(0, Math.min(100, rate(comp, v, M))) : null;
    if (ok) { sum += s * comp.weight; w += comp.weight; have++; }
    return { key: comp.key, label: comp.label, unit: comp.unit, value: ok ? v : null, score: ok ? Math.round(s) : null, weight: comp.weight, target: comp.target, basis: comp.basis, src: comp.src, edit: comp.edit };
  });
  return { id, label: d.label, score: w ? Math.max(1, Math.round(sum / w)) : null, coverage: { have, total: items.length }, items };
}
export const scoreAll = M => Object.fromEntries(DOMAIN_IDS.map(id => [id, scoreDomain(id, M)]));

/** Ring colour: red at 1, amber around 50, green at 100. */
export const scoreColor = s => (s === null || s === undefined ? '#5d6b73' : `hsl(${Math.round(Math.max(0, Math.min(100, s)) * 1.3)} 72% 52%)`);
export const scoreWord = s => (s === null ? 'No data' : s >= 85 ? 'On target' : s >= 65 ? 'Close to target' : s >= 40 ? 'Below target' : 'Far below target');

export const SCORE_SAMPLE = Object.freeze({
  'sleep.quality': 3, 'exercise.minPerWeek': 540, 'exercise.resistiveDays': 5,
  'nutrition.energyPct': 82, 'nutrition.proteinGkg': 1.3, 'nutrition.fluidL': 1.9
});

/* intake.mjs — reads health values out of pasted text, CSV, TSV or JSON (lab reports, medical summaries, device exports).
   Pure function, no DOM, no network. It only takes a value when a known label sits next to a number, converts common units,
   and rejects anything outside a plausible range. Nothing is guessed: unknown lines are reported as unread. */

const N = '([-+−]?\\d+(?:[.,]\\d+)?)';
const UNIT = '\\s*(mmol\\s*/\\s*l|mg\\s*/\\s*dl|nmol\\s*/\\s*l|ng\\s*/\\s*ml|g\\s*/\\s*dl|g\\s*/\\s*l|g\\s*/\\s*kg|kg|cm|°\\s*[cf]|deg\\s*[cf]|msv|ms|ml|l\\b|%|bpm|/min|h\\b|hours?|hrs?|min(?:utes)?|days?|d\\b|kcal)?';

/** [key, label regex (most specific first), plausible range, unit converter] */
const conv = {
  temp: (v, u) => (/f/.test(u) || v > 45 ? Math.round((v - 32) / 1.8 * 10) / 10 : v),
  glucose: (v, u) => (/mmol/.test(u) || (!u && v < 35) ? Math.round(v * 18) : v),
  vitd: (v, u) => (/nmol/.test(u) ? Math.round(v / 2.5) : v),
  hgb: (v, u) => (/g\s*\/\s*l/.test(u) && !/dl/.test(u) || v > 30 ? Math.round(v / 10 * 10) / 10 : v),
  urineL: (v, u) => (/ml/.test(u) || v > 20 ? Math.round(v) / 1000 : v),
  height: v => (v < 3 ? Math.round(v * 100) : v),
  hours: (v, u) => (/min/.test(u) ? Math.round(v / 60 * 10) / 10 : v)
};
const NUMERIC = [
  ['bmd.hipPct',            /(?:hip|femoral neck|total hip)\s*(?:bmd|bone (?:mineral )?density)(?:\s*change)?/],
  ['bmd.lumbarPct',         /(?:lumbar(?: spine)?|spine)\s*(?:bmd|bone (?:mineral )?density)(?:\s*change)?/],
  ['bmd.wholeBodyPct',      /(?:whole[- ]body|total body)\s*(?:bmd|bone (?:mineral )?density)(?:\s*change)?/],
  ['radiation.eventMsv',    /(?:solar particle event|spe|event)\s*dose/],
  ['radiation.careerMsv',   /(?:career|cumulative|total)?\s*(?:radiation\s*)?(?:effective\s*)?dose|radiation/],
  ['urine.calciumMgDay',    /(?:urinary|urine|24[- ]?h(?:our)?\s*urine)\s*calcium/],
  ['urine.volumeL',         /(?:24[- ]?h(?:our)?\s*)?urine(?:\s*(?:volume|output))?/],
  ['sleep.quality',         /sleep quality/],
  ['sleep.hours',           /sleep(?:\s*(?:duration|time|hours))?|slept|total sleep/],
  ['pvt.lapses',            /(?:pvt\s*)?lapses/],
  ['pvt.meanRtMs',          /(?:mean\s*)?(?:reaction|response)\s*time|mean\s*rt|pvt\s*(?:mean\s*)?rt/],
  ['bp',                    /blood pressure|\bbp\b|\bnibp\b/],
  ['hr.rest',               /(?:resting\s*)?(?:heart rate|pulse)|\bhr\b/],
  ['spo2.pct',              /spo2|sp\s*o2|oxygen saturation|o2\s*sat(?:uration)?|blood oxygen/],
  ['resp.rate',             /respiratory rate|respiration(?:\s*rate)?|breathing rate|\brr\b/],
  ['temp.c',                /(?:body\s*)?temperature|\btemp\b/],
  ['glucose.mgdl',          /(?:blood\s*)?glucose|blood sugar/],
  ['hemoglobin.gdl',        /ha?emoglobin|\bhgb\b|\bhb\b/],
  ['vitd.ngml',             /(?:25[- ]?(?:\(oh\)|oh|hydroxy)\s*)?vitamin\s*d(?:3)?|25[- ]?oh[- ]?d/],
  ['mass.changePct',        /(?:body\s*)?(?:mass|weight)\s*change/],
  ['body.massKg',           /body\s*(?:mass|weight)|\bweight\b/],
  ['body.heightCm',         /(?:body\s*)?height|stature/],
  ['strength.changePct',    /(?:muscle\s*)?strength(?:\s*change)?/],
  ['aerobic.changePct',     /vo2\s*(?:peak|max)(?:\s*change)?|aerobic(?:\s*(?:capacity|fitness))?(?:\s*change)?/],
  ['sans.hyperopicShiftD',  /hyperopic shift|refractive shift/],
  ['back.pain',             /back pain(?:\s*score)?/],
  ['exercise.minPerWeek',   /exercise(?:\s*time)?(?:\s*per\s*week)?|training time/],
  ['exercise.resistiveDays',/resistance(?:\s*training)?\s*days|resistive(?:\s*exercise)?\s*days|ared\s*days/],
  ['nutrition.energyPct',   /energy intake|calorie intake/],
  ['nutrition.proteinGkg',  /protein(?:\s*intake)?/],
  ['nutrition.fluidL',      /fluid(?:\s*intake)?|water intake/],
  ['mission.month',         /mission month|month of (?:the )?mission|flight month/]
];
export const RANGES = Object.freeze({
  'hr.rest': [20, 220], 'spo2.pct': [50, 100], 'resp.rate': [4, 60], 'temp.c': [30, 43], 'glucose.mgdl': [20, 600], 'hemoglobin.gdl': [3, 20],
  'sleep.hours': [0, 16], 'sleep.quality': [1, 5], 'pvt.lapses': [0, 100], 'pvt.meanRtMs': [100, 2000], 'back.pain': [0, 10],
  'urine.volumeL': [0, 8], 'urine.calciumMgDay': [0, 1000], 'mass.changePct': [-40, 40], 'vitd.ngml': [1, 200],
  'radiation.careerMsv': [0, 2000], 'radiation.eventMsv': [0, 2000], 'bmd.hipPct': [-40, 20], 'bmd.lumbarPct': [-40, 20], 'bmd.wholeBodyPct': [-40, 20],
  'strength.changePct': [-80, 50], 'aerobic.changePct': [-80, 50], 'sans.hyperopicShiftD': [-5, 5],
  'exercise.minPerWeek': [0, 1500], 'exercise.resistiveDays': [0, 7], 'nutrition.energyPct': [0, 200], 'nutrition.proteinGkg': [0, 4], 'nutrition.fluidL': [0, 8],
  'mission.month': [0, 36], 'body.heightCm': [140, 210], 'body.massKg': [35, 160], 'bp.sys': [50, 260], 'bp.dia': [30, 160]
});
const CONVERT = { 'temp.c': conv.temp, 'glucose.mgdl': conv.glucose, 'vitd.ngml': conv.vitd, 'hemoglobin.gdl': conv.hgb, 'urine.volumeL': conv.urineL, 'sleep.hours': conv.hours, 'nutrition.fluidL': conv.urineL, 'body.heightCm': conv.height };

/** Yes/no and categorical findings. */
const YES = /\b(yes|present|positive|detected|reported|true)\b/, NO = /\b(no|none|absent|negative|not detected|normal|false)\b/;
const FLAGS = [
  ['orthostatic.presyncope', /(?:dizziness on standing|orthostatic(?: intolerance)?|presyncope|light-?headed(?:ness)?)/],
  ['sans.discEdema',         /(?:optic\s*)?disc (?:edema|oedema|swelling)|papilledema/],
  ['sans.choroidalFolds',    /choroidal folds/],
  ['virus.shedding',         /(?:viral|virus)\s*shedding|(?:ebv|vzv|cmv)\s*(?:dna\s*)?(?:in\s*saliva)?/],
  ['zoster.symptoms',        /shingles|zoster/]
];

const toNum = s => Number(String(s).replace('−', '-').replace(',', '.'));
const blank = (str, i, len) => str.slice(0, i) + ' '.repeat(len) + str.slice(i + len);

/** Turns JSON and CSV/TSV into "label: value unit" lines so one text parser handles every format. */
export function normalize(raw, name = '') {
  let text = String(raw || '');
  const t = text.trim();
  if (/\.json$/i.test(name) || /^[[{]/.test(t)) {
    try {
      const lines = [];
      const walk = (v, k) => {
        if (v && typeof v === 'object' && !Array.isArray(v)) {
          if ('value' in v && (v.name || v.key || v.label || k)) { lines.push(`${v.name || v.key || v.label || k}: ${v.value} ${v.unit || ''}`); return; }
          for (const [kk, vv] of Object.entries(v)) walk(vv, kk);
        } else if (Array.isArray(v)) v.forEach(x => walk(x, k));
        else if (k) lines.push(`${k}: ${v}`);
      };
      walk(JSON.parse(t), ''); return lines.join('\n');
    } catch (e) { /* not JSON after all: fall through to text */ }
  }
  if (/\.(csv|tsv)$/i.test(name) || /^[^\n]*[,;\t][^\n]*\n[^\n]*[,;\t]/.test(t)) {
    text = text.split(/\r?\n/).map(l => l.split(/\t|;|,(?!\d)/).map(c => c.trim().replace(/^"|"$/g, '')).filter(Boolean).join(': ')).join('\n');
  }
  // JSON-style keys such as "hr.rest" or "bmd_hipPct" read like labels
  return text.replace(/\b([a-z0-9]+)_([a-z0-9]+)\b/gi, (m, a, b) => (/^\d+$/.test(a) && /^\d+$/.test(b) ? m : `${a} ${b.replace(/([a-z])([A-Z])/g, '$1 $2')}`));
}

/** → { values: {key: number|boolean|string}, found: [{key, value, text}], rejected: [{key, value, text}], unread: [line] } */
export function extract(raw, name = '') {
  let text = normalize(raw, name).toLowerCase();
  const values = {}, found = [], rejected = [];
  const take = (key, value, snippet) => {
    const r = RANGES[key];
    if (typeof value === 'number' && (!Number.isFinite(value) || (r && (value < r[0] || value > r[1])))) { rejected.push({ key, value, text: snippet.trim() }); return; }
    if (key in values) return;                                       // the first mention wins
    values[key] = value; found.push({ key, value, text: snippet.trim() });
  };
  // exact app keys first ("hr.rest: 64", "sans.discEdema: false"), as written by AstroBody exports and JSON files
  const KEYS = Object.fromEntries([...Object.keys(RANGES), 'jugular.flow', ...FLAGS.map(f => f[0])].map(k => [k.toLowerCase(), k]));
  text = text.replace(/^\s*([a-z0-9]+\.[a-z0-9]+)\s*[:=]\s*(\S+)[^\n]*$/gm, (line, k, v) => {
    const key = KEYS[k]; if (!key) return line;
    if (/^(true|yes)$/.test(v)) take(key, true, line); else if (/^(false|no)$/.test(v)) take(key, false, line);
    else if (key === 'jugular.flow') take(key, v, line); else take(key, toNum(v), line);
    return ' '.repeat(line.length);
  });
  // jugular vein flow (categorical)
  const jug = /jugular[^\n]{0,40}?\b(thrombus|clot|occlusi\w*|reversed|retrograde|stagnant|normal|antegrade)\b/.exec(text);
  if (jug) { const w = jug[1]; take('jugular.flow', /thromb|clot|occlu/.test(w) ? 'thrombus' : /rever|retro/.test(w) ? 'reversed' : w === 'stagnant' ? 'stagnant' : 'normal', jug[0]); text = blank(text, jug.index, jug[0].length); }
  for (const [key, re] of FLAGS) {
    const m = new RegExp(`(?:${re.source})[^\\n]{0,24}`, 'g').exec(text); if (!m) continue;
    const tail = m[0], neg = /\bno\b|\bnot\b|\bnone\b|\babsent\b|\bnegative\b|\bdenies\b/.test(text.slice(Math.max(0, m.index - 12), m.index) + tail);
    if (neg || YES.test(tail) || NO.test(tail) || /:\s*$|:/.test(tail)) take(key, neg ? false : NO.test(tail) && !YES.test(tail) ? false : true, tail);
    text = blank(text, m.index, m[0].length);
  }
  for (const [key, re] of NUMERIC) {
    const rx = key === 'bp'
      ? new RegExp(`(?:${re.source})[^\\d\\n]{0,24}?(\\d{2,3})\\s*(?:/|over)\\s*(\\d{2,3})`, 'g')
      : new RegExp(`(?:${re.source})\\b[^\\d\\n+−-]{0,28}?${N}${UNIT}`, 'g');
    let m;
    while ((m = rx.exec(text))) {
      const snippet = m[0];
      if (key === 'bp') { const s = +m[1], d = +m[2]; if (s > d) { take('bp.sys', s, snippet); take('bp.dia', d, snippet); } else rejected.push({ key: 'bp.sys', value: `${s}/${d}`, text: snippet }); }
      else { let v = toNum(m[1]); const u = (m[2] || '').replace(/\s+/g, ''); if (CONVERT[key]) v = CONVERT[key](v, u); take(key, v, snippet); }
      text = blank(text, m.index, m[0].length); rx.lastIndex = m.index + m[0].length;
    }
  }
  const unread = text.split('\n').map(l => l.replace(/^[^a-z0-9]+/, '').replace(/[\s,;:]{2,}/g, ' ').trim()).filter(l => /[a-z]{3}/.test(l) && /\d/.test(l));
  return { values, found, rejected, unread };
}

/** Files the browser can read as text. PDFs and images need their text pasted instead. */
export const READABLE = /\.(txt|csv|tsv|json|md|log|xml|html?)$/i;

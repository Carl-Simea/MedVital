/* assistant.mjs — rule-based crew assistant. Not a language model: it reads the crew member's own data (the evaluated part model)
   and answers from the catalogue in parts.mjs, with sources. Pure functions, no DOM; runs in the browser and in Node.
   It understands English input. It never invents a value, a threshold or a source. */
import { PARTS, INDICATORS, SRC, WHY, LEVEL, LEVEL_LABEL, LEVEL_NAME, summarize } from './parts.mjs';

const num = s => parseFloat(String(s).replace(',', '.'));
const rng = (v, a, b) => v >= a && v <= b;
/** Values the user can tell the assistant. [indicator key, regex, plausible range] */
const PATTERNS = [
  ['hr.rest', /(?:heart ?rate|pulse|\bhr\b)\D{0,14}(\d{2,3})/i, [20, 220]],
  ['spo2.pct', /(?:spo2|oxygen)\D{0,14}(\d{2,3})/i, [50, 100]],
  ['resp.rate', /(?:breathing|respiration|resp(?:iratory)? rate)\D{0,14}(\d{1,2})/i, [4, 60]],
  ['temp.c', /(?:temperature|temp\b|fever)\D{0,14}(\d{2}(?:[.,]\d)?)/i, [30, 43]],
  ['glucose.mgdl', /(?:glucose|blood sugar)\D{0,14}(\d{2,3})/i, [20, 600]],
  ['sleep.hours', /(?:sleep|slept)\D{0,16}(\d{1,2}(?:[.,]\d)?)/i, [0, 16]],
  ['hemoglobin.gdl', /(?:h(?:a)?emoglobin|\bhb\b)\D{0,14}(\d{1,2}(?:[.,]\d)?)/i, [3, 20]],
  ['back.pain', /(?:back pain)\D{0,14}(\d{1,2})/i, [0, 10]],
  ['urine.volumeL', /(?:urine)\D{0,14}(\d(?:[.,]\d+)?)\s*(?:l\b|liter|litre)/i, [0, 8]],
  ['mass.changePct', /(?:body mass|weight)\D{0,14}(-?\d{1,2}(?:[.,]\d)?)\s*%/i, [-40, 40]],
  ['vitd.ngml', /(?:vitamin d)\D{0,14}(\d{1,3})/i, [1, 200]],
  ['radiation.careerMsv', /(?:radiation|dose)\D{0,14}(\d{1,4})\s*msv/i, [0, 2000]]
];
export function parseMeasurements(text) {
  const set = {}, rejected = [];
  const bp = /(?:blood pressure|\bbp\b)\D{0,10}(\d{2,3})\s*(?:\/|over)\s*(\d{2,3})/i.exec(text);
  if (bp) { const a = num(bp[1]), b = num(bp[2]); if (rng(a, 50, 260) && rng(b, 30, 160) && a > b) { set['bp.sys'] = a; set['bp.dia'] = b; } else rejected.push('blood pressure'); }
  for (const [key, re, [lo, hi]] of PATTERNS) {
    const m = re.exec(text); if (!m) continue; const v = num(m[1]);
    if (rng(v, lo, hi)) set[key] = v; else rejected.push(INDICATORS[key].label.toLowerCase());
  }
  return { set, rejected };
}

const TOPICS = [
  { name: 'heart and circulation', groups: ['heart', 'artery', 'vein'], words: ['heart', 'cardio', 'blood pressure', 'circulation', 'artery', 'arteries', 'vein', 'pulse', 'dizzy', 'orthostatic'] },
  { name: 'lungs and breathing', groups: ['lung', 'airway'], words: ['lung', 'breath', 'oxygen', 'dust', 'airway'] },
  { name: 'back and spine', groups: ['spineL', 'spineT', 'spineC'], words: ['back', 'spine', 'disc'] },
  { name: 'hip and thigh bone', groups: ['pelvis', 'femur'], words: ['hip', 'pelvis', 'femur', 'thigh bone'] },
  { name: 'bones', groups: PARTS && Object.keys(PARTS).filter(g => PARTS[g].system === 'skeleton'), words: ['bone', 'skeleton', 'osteopor', 'density', 'fracture'] },
  { name: 'muscles', groups: Object.keys(PARTS).filter(g => PARTS[g].system === 'muscle' && g !== 'tendon'), words: ['muscle', 'strength', 'atrophy', 'exercise'] },
  { name: 'kidneys and urine', groups: ['kidney'], words: ['kidney', 'urine', 'stone'] },
  { name: 'blood', groups: ['spleen'], words: ['blood health', 'anemia', 'anaemia', 'hemoglobin', 'haemoglobin', 'spleen', 'red blood'] },
  { name: 'brain and alertness', groups: ['brain'], words: ['brain', 'sleep', 'alert', 'cognitive', 'fatigue', 'tired', 'reaction', 'pvt', 'focus'] },
  { name: 'eyes', groups: ['eye'], words: ['eye', 'vision', 'sans'] },
  { name: 'digestion and nutrition', groups: ['stomach', 'intestine', 'liver'], words: ['stomach', 'intestin', 'liver', 'digest', 'gut', 'nutrition', 'weight', 'appetite', 'food'] },
  { name: 'whole body (radiation, immune, temperature, glucose, vitamin D)', groups: ['body'], words: ['radiation', 'dose', 'immune', 'virus', 'shingles', 'temperature', 'fever', 'glucose', 'blood sugar', 'vitamin', 'whole body'] }
];
const has = (q, words) => words.some(w => q.includes(w));
const srcTitles = list => [...new Set(list.filter(Boolean).map(k => SRC[k] && SRC[k].title))].filter(Boolean);
const bullets = a => a.map(x => '• ' + x).join('\n');
const CHIPS = ['How am I doing?', 'What needs attention?', 'When should I call the flight surgeon?', 'What helps my back?', 'My heart rate is 72'];
const DISC = 'Decision support, not a diagnosis.';

function overall(ctx) {
  const { counts, attention } = summarize(ctx.parts), total = Object.keys(ctx.parts).length;
  if (counts.nodata === total) return { text: 'I have no health data yet. Load the sample data, run the check-in, or tell me a value, for example "my heart rate is 72", "blood pressure 120/80", "I slept 6 hours".', chips: CHIPS };
  const rated = total - counts.nodata;
  if (!attention.length) return { text: `${rated} of ${total} parts have data and none needs attention. ${DISC}`, chips: CHIPS };
  const top = attention.slice(0, 4);
  return { text: `${attention.length} of ${rated} rated parts need attention. Most important:\n${bullets(top.map(a => `${a.label} (${LEVEL_LABEL[a.level]}): ${a.text}`))}\nAsk me about any of them, for example "what helps my ${top[0].label.toLowerCase()}?". ${DISC}`, focus: top[0].id, chips: CHIPS };
}
function escalation(ctx) {
  const { attention } = summarize(ctx.parts), hi = attention.filter(a => a.level >= 2);
  if (!attention.length) return { text: 'Nothing in your data needs the flight surgeon right now. Contact them anyway for anything that worries you.' };
  const crit = hi.filter(a => a.level >= 3);
  const lines = [];
  if (crit.length) lines.push('Contact the flight surgeon now:\n' + bullets(crit.map(a => `${a.label}: ${a.text}`)));
  const warn = hi.filter(a => a.level === 2);
  if (warn.length) lines.push('Tell the flight surgeon at the next contact, re-measure first:\n' + bullets(warn.map(a => `${a.label}: ${a.text}`)));
  if (!hi.length) lines.push('No part is above "Watch". Keep tracking; re-measure the watched items.');
  lines.push('On a long mission with a delayed link, follow the Check-in advice for autonomous action.');
  return { text: lines.join('\n'), focus: (crit[0] || warn[0] || attention[0]).id };
}
function topicAnswer(t, q, ctx) {
  const states = t.groups.map(g => ctx.parts[g]).filter(Boolean);
  const rated = states.filter(s => s.level >= 0).sort((a, b) => b.level - a.level);
  const wantHelp = /help|prevent|treat|what (can|should) i do|countermeasure|tun|hilft|improve|fix|better/.test(q);
  const wantMeasure = /measure|measured|why|how (do|is|are)|in flight|test|exam/.test(q) && !wantHelp;
  const defs = t.groups.map(g => PARTS[g]).filter(Boolean);
  const out = [];
  if (wantMeasure) {
    const keys = [...new Set(defs.flatMap(d => d.ind))];
    out.push(`What NASA tracks for ${t.name}:`);
    out.push(bullets(keys.map(k => `${INDICATORS[k].label}: ${INDICATORS[k].how}${INDICATORS[k].flight ? '' : ' (not measurable in flight)'}. ${WHY[k] || ''}`)));
    return { text: out.join('\n'), focus: t.groups[0], srcs: [] };
  }
  if (!rated.length) {
    const keys = [...new Set(defs.flatMap(d => d.ind))];
    out.push(`No data for ${t.name} yet.` + (keys.length ? ` It is rated from: ${keys.map(k => INDICATORS[k].label.toLowerCase()).join(', ')}. Tell me a value or load the sample data.` : ' No indicator is connected to it, so it cannot be rated.'));
  } else {
    const worst = rated[0];
    out.push(`${t.name[0].toUpperCase() + t.name.slice(1)}: ${LEVEL_LABEL[worst.level]}${rated.length > 1 ? ` (worst of ${rated.length} rated parts: ${worst.label})` : ''}.`);
    const warns = [...new Set(rated.flatMap(s => s.warnings.map(w => w.text)))].slice(0, 3);
    out.push(warns.length ? bullets(warns) : 'No warning in the data entered.');
  }
  const helps = [...new Map(defs.flatMap(d => d.helps).map(h => [h.t, h])).values()];
  const facts = [...new Map(defs.flatMap(d => d.facts).map(h => [h.t, h])).values()];
  const flagged = rated.length && rated[0].level >= 1;
  if (helps.length && (wantHelp || flagged)) out.push('What helps:\n' + bullets(helps.slice(0, 3).map(h => h.t)));
  else if (wantHelp) out.push('I have no verified countermeasure for this on file. Ask the flight surgeon.');
  if (!wantHelp && !flagged && facts.length) out.push('Spaceflight effect: ' + facts[0].t);
  const srcs = [...(rated[0] ? rated[0].warnings.map(w => w.src) : []), ...helps.slice(0, 3).map(h => h.s), facts[0] && facts[0].s];
  const titles = srcTitles(srcs).slice(0, 3);
  if (titles.length) out.push('Sources: ' + titles.join('; '));
  out.push(DISC);
  return { text: out.join('\n'), focus: (rated[0] || { id: t.groups[0] }).id || t.groups[0], srcs };
}

/** ctx: {parts, M}. Returns {text, focus?, set?, chips?}. */
export function answer(question, ctx) {
  const q = String(question || '').toLowerCase().trim();
  if (!q) return { text: 'Ask me about your health data.', chips: CHIPS };
  const { set, rejected } = parseMeasurements(question);
  if (Object.keys(set).length) {
    const lines = Object.entries(set).map(([k, v]) => `${INDICATORS[k].label} ${v}${INDICATORS[k].unit ? ' ' + INDICATORS[k].unit : ''}`);
    return { text: `Noted: ${lines.join(', ')}.` + (rejected.length ? ` I ignored implausible: ${rejected.join(', ')}.` : ''), set, afterUpdate: true };
  }
  if (rejected.length) return { text: `That value for ${rejected.join(', ')} is outside the plausible range, so I did not save it. Please check it.` };
  if (/^(hi|hello|hey|hallo|help|hilfe)\b|what can you|was kannst du/.test(q)) return { text: 'I can explain your health data part by part, tell you what needs attention, what helps, when to contact the flight surgeon, and how each value is measured. You can also tell me values: "my heart rate is 72", "blood pressure 120/80", "I slept 6 hours", "SpO2 96", "hemoglobin 12.5". I am a rule-based assistant, not a doctor, and I only use your data and the sourced catalogue.', chips: CHIPS };
  if (/call|contact|inform|ground|flight surgeon|doctor|arzt|emergency|notfall|urgent|dringend/.test(q)) return escalation(ctx);
  const t = TOPICS.find(x => has(q, x.words));
  if (t) return topicAnswer(t, q, ctx);
  if (/how am i|overall|summary|status|attention|alert|warning|zusammenfassung|wie geht|everything|alles|problem|wrong|worry/.test(q)) return overall(ctx);
  return { text: 'I can only answer from your health data and the sourced catalogue, and I did not recognise a topic in that. Try: how am I doing, what needs attention, what helps my back, how is blood pressure measured, or tell me a value.', chips: CHIPS };
}
export const SUGGESTIONS = CHIPS;

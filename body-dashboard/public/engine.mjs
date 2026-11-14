/* engine.mjs — deterministic decision logic for AstroBody.
   No DOM, no network, no AI: same input → same output. Runs in the browser and in Node.
   DEMONSTRATOR, not medically approved. Every rule carries its origin:
   'verified'   = Zahl stammt aus einer in docs/SOURCES.md genannten Quelle
   'convention' = general convention / placeholder, not verified in this work */

export const SEV = Object.freeze({ ok: 0, watch: 1, warn: 2, alert: 3 });
export const SEV_NAME = ['ok', 'watch', 'warn', 'alert'];
/** AstroBody.setSystemStatus only knows ok | warn | alert. */
export const uiStatus = sev => (sev >= 3 ? 'alert' : sev >= 2 ? 'warn' : 'ok');

/* ---------- Radio delay ---------- */
export const CONTEXTS = Object.freeze({
  leo:  { id: 'leo',  label: 'ISS (LEO)', oneWaySec: 1 },                                        // assumption, depends on the relay
  moon: { id: 'moon', label: 'Mond',      oneWaySec: 1.3 },                                      // Lichtlaufzeit ~1,3 s
  mars: { id: 'mars', label: 'Mars',      oneWaySec: 750, minOneWaySec: 182, maxOneWaySec: 1337 } // 3–22 min einfach
});
export const roundTripSec = c => 2 * c.oneWaySec;
export function latencyClass(c) {
  const rt = roundTripSec(c);
  return rt <= 10 ? 'live' : rt <= 300 ? 'delayed' : 'autonomous';
}
export const withOneWay = (base, sec) => ({ ...base, oneWaySec: Math.max(0, sec) });
export function fmtDuration(sec) {
  if (sec < 10) return `${sec.toFixed(1)} s`;
  if (sec < 120) return `${Math.round(sec)} s`;
  return `${Math.round(sec / 60)} min`;
}

/* ---------- Befunde ---------- */
/** Rating cap per data source: trend signals and models may never trigger "alert" on their own. */
export const SOURCE_CAP = Object.freeze({ measured: 3, manual: 3, camera: 2, model: 1, simulated: 2 });

export function finding(id, system, source, severity, text, rules = [], extra = {}) {
  const f = { id, system, source, severity, text, rules: [...rules], ...extra };
  const cap = SOURCE_CAP[source] ?? 2;
  if (f.severity > cap) { f.rules.push(`cap.${source}`); f.severity = cap; }
  return f;
}

/* ---------- Personal baseline ---------- */
export class Baseline {
  constructor(data = {}, { max = 60, minN = 3 } = {}) { this.d = data; this.max = max; this.minN = minN; }
  add(metric, value) {
    if (!Number.isFinite(value)) return;
    const a = (this.d[metric] ||= []); a.push(value); if (a.length > this.max) a.shift();
  }
  stats(metric) {
    const a = this.d[metric] || []; const n = a.length;
    if (!n) return { n: 0, mean: null, sd: null };
    const mean = a.reduce((s, x) => s + x, 0) / n;
    const sd = n > 1 ? Math.sqrt(a.reduce((s, x) => s + (x - mean) ** 2, 0) / (n - 1)) : 0;
    return { n, mean, sd: Math.max(sd, 0.05 * Math.abs(mean), 1e-9) }; // floor against inflated z-scores
  }
  z(metric, value) {
    const s = this.stats(metric);
    return s.n < this.minN || !Number.isFinite(value) ? null : (value - s.mean) / s.sd;
  }
  toJSON() { return this.d; }
  static from(json, opts) { return new Baseline(json && typeof json === 'object' ? json : {}, opts); }
}

/* ---------- PVT-Auswertung ---------- */
/** trials: [{rt:ms|null}] (null = no response before timeout). Responses < falseStartMs count as false starts. */
export function scorePvt(trials, { lapseMs = 355, falseStartMs = 100, timeoutMs = 5000, premature = 0 } = {}) {
  const early = trials.filter(t => t.rt !== null && t.rt < falseStartMs).length;
  const rts = trials.filter(t => t.rt === null || t.rt >= falseStartMs).map(t => (t.rt === null ? timeoutMs : t.rt));
  const responses = trials.filter(t => t.rt !== null && t.rt >= falseStartMs).map(t => t.rt);
  const inv = rts.map(r => 1000 / r);
  const mean = a => (a.length ? a.reduce((s, x) => s + x, 0) / a.length : NaN);
  const sorted = [...rts].sort((a, b) => a - b);
  const k = Math.max(1, Math.round(sorted.length * 0.1));
  const med = sorted.length ? (sorted.length % 2 ? sorted[(sorted.length - 1) / 2] : (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2) : NaN;
  const invSorted = [...inv].sort((a, b) => a - b);
  return {
    lapseMs, trials: trials.length, responses: responses.length,
    lapses: rts.filter(r => r >= lapseMs).length,
    falseStarts: early + premature,
    meanRt: mean(rts), medianRt: med, meanInvRt: mean(inv),
    fastest10: mean(sorted.slice(0, k)), slowest10Inv: mean(invSorted.slice(0, k))
  };
}

/* ---------- Bewerter ---------- */
export function evalPvt(score, { baseline = null, confirmed = false } = {}) {
  if (score.responses < 10)
    return finding('pvt', 'brain', 'measured', 1, 'Too few valid responses, repeat the test', ['pvt.invalid'], { score });
  const rules = []; let sev = 0;
  if (score.lapseMs === 355) {                                   // verified: Basner & Rubinstein 2011 (3-min-PVT)
    if (score.lapses >= 20) { sev = 3; rules.push('pvt.lapses>=20@355ms'); }
    else if (score.lapses >= 11) { sev = 2; rules.push('pvt.lapses>=11@355ms'); }
  }
  const z = baseline ? baseline.z('pvt.invRt', score.meanInvRt) : null;   // convention: z-Grenzen
  if (z !== null) {
    if (z <= -2.5 && sev < 2) { sev = 2; rules.push('pvt.z<=-2.5'); }
    else if (z <= -1.5 && sev < 1) { sev = 1; rules.push('pvt.z<=-1.5'); }
  }
  if (sev === 3 && !confirmed) { sev = 2; rules.push('pvt.needs-confirmation'); } // a device without latency calibration
  const text = `${score.lapses} lapses (≥${score.lapseMs} ms), mean ${Math.round(score.meanRt)} ms` + (z !== null ? `, ${z.toFixed(1)} σ vs. own baseline` : '');
  return finding('pvt', 'brain', 'measured', sev, text, rules, { score, z });
}

export function evalHeartRate({ bpm, source = 'manual', context = 'rest' }, baseline = null) {
  if (context !== 'rest') return finding('hr', 'cardio', source, 0, `Heart rate ${bpm} bpm (only resting values are rated)`, ['hr.not-rest']);
  const rules = []; let sev = 0;
  if (bpm > 120) { sev = 3; rules.push('hr.rest>120'); }          // convention
  else if (bpm > 100) { sev = 2; rules.push('hr.rest>100'); }
  else if (bpm < 40) { sev = 2; rules.push('hr.rest<40'); }
  else if (bpm < 50) { sev = 1; rules.push('hr.rest<50'); }
  const z = baseline ? baseline.z('hr.rest', bpm) : null;
  if (z !== null) {
    if (z >= 3 && sev < 2) { sev = 2; rules.push('hr.z>=3'); }
    else if (z >= 2 && sev < 1) { sev = 1; rules.push('hr.z>=2'); }
  }
  const text = `Resting heart rate ${bpm} bpm` + (z !== null ? `, ${z.toFixed(1)} σ vs. baseline` : '');
  return finding('hr', 'cardio', source, sev, text, rules, { z });
}

/** Bone model, not a measurement. Rates: mean 1–1.5 %/month aBMD (NASA Evidence Report 2017);
    hip 1.5 / lumbar spine 1 / whole body 0.3 %/month (Sibonga 2015, after LeBlanc 2000). */
export function evalBoneModel(months) {
  const m = Math.max(0, months);
  const f1 = x => x.toFixed(1);
  const detail = { avg: [m * 1, m * 1.5], hip: m * 1.5, lumbar: m * 1, wholeBody: m * 0.3 };
  const sev = m >= 1 ? 1 : 0;
  return finding('bone', 'skeleton', 'model', sev,
    `Model, not a measurement: after ${f1(m)} months about ${f1(detail.avg[0])}–${f1(detail.avg[1])} % average aBMD loss`,
    sev ? ['bone.model-reminder'] : [], { detail });
}

/* ---------- Triage ---------- */
const CAVEAT = {
  camera: 'Camera values are trend signals, not a measuring device.',
  model: 'Modeled value, not measured.',
  simulated: 'Simulated value.'
};

export function triage(findings, ctx) {
  const cls = latencyClass(ctx), rt = roundTripSec(ctx);
  const rulesFired = [];
  const eff = findings.map(f => {
    let s = f.severity;
    if (f.consecutive >= 2 && s === 2) {                                   // persistent finding → one level higher
      const up = Math.min(3, SOURCE_CAP[f.source] ?? 2);
      if (up > s) { s = up; rulesFired.push(`persist.${f.id}`); }
    }
    return { ...f, eff: s };
  });
  const top = eff.reduce((m, f) => Math.max(m, f.eff), 0);
  const drivers = top > 0 ? eff.filter(f => f.eff === top) : [];
  const reasons = drivers.map(f => `${f.text} [${f.source}]`);
  const caveats = [...new Set(drivers.map(f => CAVEAT[f.source]).filter(Boolean))];
  const base = { top, latency: { class: cls, roundTripSec: rt }, reasons, caveats, rulesFired, drivers: drivers.map(f => f.id),
    disclaimer: 'Decision support, not a diagnosis.' };
  const wait = fmtDuration(rt);

  if (top === 0) return { ...base, action: 'none', urgency: 'none', waitForReply: false, steps: [] };
  if (top === 1) return { ...base, action: 'remeasure', urgency: 'routine', waitForReply: false,
    steps: ['Repeat the measurement under the same conditions (later today or tomorrow).', 'Watch the trend in the log.'] };
  if (top === 2) {
    if (cls !== 'autonomous') return { ...base, action: 'contact_ground', urgency: 'soon', waitForReply: true, expectedReplySec: rt,
      steps: ['Send finding and readings to the flight surgeon / ground.', 'Re-measure in parallel after about 10 min.'] };
    return { ...base, action: 'self_treat', urgency: 'soon', waitForReply: false, expectedReplySec: rt,
      steps: ['Re-measure after a short rest (about 10 min).', 'Start the onboard countermeasure or protocol.',
        `Send a report to the ground now, asynchronously. A reply takes ${wait} at the earliest.`,
        'If the finding persists, it escalates automatically.'] };
  }
  const steps = ['Contact the ground immediately.', 'Do not postpone the onboard emergency protocol.'];
  if (cls === 'autonomous') steps.push(`A reply takes ${wait} at the earliest. Do not wait for it.`);
  return { ...base, action: 'contact_ground_now', urgency: 'immediate', waitForReply: cls !== 'autonomous', expectedReplySec: rt, steps };
}

/** Worst finding per body system → { skeleton:{status,text}, … } for AstroBody.setSystemStatus. */
export function summarizeBySystem(findings) {
  const out = {};
  for (const f of findings) {
    const cur = out[f.system];
    if (!cur || f.severity > cur.sev) out[f.system] = { sev: f.severity, status: uiStatus(f.severity), text: f.text, source: f.source };
  }
  return out;
}

/* live.mjs — a test stream of continuously measured values (heart rate, breathing, blood oxygen, skin temperature,
   heart rate variability, skin conductance, radiation dose rate) for demos. It stands in for a wearable such as a smart
   shirt or a wristband: nothing here is measured. The stream follows the crew member's current activity, so a heart rate
   of 130 bpm during exercise reads differently from 130 bpm at rest. Pure and deterministic: same seed, same stream. */

export const ACTIVITIES = Object.freeze({
  rest:     { label: 'Resting',        note: 'Awake and at rest' },
  sleep:    { label: 'Sleeping',       note: 'Sleep period' },
  work:     { label: 'Working',        note: 'Light physical and mental work' },
  exercise: { label: 'Exercising',     note: 'Treadmill, cycle or resistance training' },
  eva:      { label: 'Spacewalk',      note: 'Work in the suit outside the vehicle' }
});
export const ACTIVITY_IDS = Object.freeze(Object.keys(ACTIVITIES));
/** Demo timeline in seconds of real time: a day compressed so every state shows up within two and a half minutes. */
export const TIMELINE = Object.freeze([['rest', 20], ['work', 25], ['exercise', 35], ['rest', 25], ['sleep', 30], ['rest', 15]]);
export const LIVE_KEYS = Object.freeze(['hr.now', 'resp.rate', 'spo2.pct', 'skin.tempC', 'hrv.rmssdMs', 'eda.uS', 'radiation.rateUsvH']);

const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const r1 = v => Math.round(v * 10) / 10;

/** Where each value settles for an activity, starting from the person's resting values (`base`). General physiology, not NASA figures. */
export function targets(base, activity) {
  const hr0 = base['hr.rest'] ?? 62, rr0 = base['resp.rate'] ?? 14, sp0 = base['spo2.pct'] ?? 98, sk0 = base['skin.tempC'] ?? 33.5,
        hv0 = base['hrv.rmssdMs'] ?? 50, ed0 = base['eda.uS'] ?? 2.5, rad = base['radiation.rateUsvH'] ?? 15;
  const reserve = Math.max(20, 182 - hr0);                      // room up to a nominal maximum heart rate
  const k = { rest:     { hr: hr0,                  rr: rr0,      sp: sp0,     sk: sk0,       hv: hv0,        ed: ed0 },
              sleep:    { hr: hr0 * 0.86,           rr: rr0 - 2,  sp: sp0 - .5, sk: sk0 + .8, hv: hv0 * 1.35, ed: ed0 * 0.6 },
              work:     { hr: hr0 + reserve * 0.14, rr: rr0 + 3,  sp: sp0,     sk: sk0 + .2,  hv: hv0 * 0.8,  ed: ed0 * 1.5 },
              exercise: { hr: hr0 + reserve * 0.62, rr: rr0 + 15, sp: sp0 - 1, sk: sk0 + 1.1, hv: hv0 * 0.25, ed: ed0 * 3.2 },
              eva:      { hr: hr0 + reserve * 0.38, rr: rr0 + 8,  sp: sp0,     sk: sk0 + .7,  hv: hv0 * 0.45, ed: ed0 * 2.4 } }[activity] || null;
  if (!k) return targets(base, 'rest');
  return { 'hr.now': k.hr, 'resp.rate': k.rr, 'spo2.pct': clamp(k.sp, 70, 100), 'skin.tempC': k.sk, 'hrv.rmssdMs': k.hv, 'eda.uS': k.ed, 'radiation.rateUsvH': rad };
}

/** createLive({base, seed}) → { step(dt, activity) → values, activityAt(t) → activity of the demo timeline }.
    Values move towards their target with a time constant of a few seconds and carry a little noise. */
export function createLive({ base = {}, seed = 1 } = {}) {
  let s = (seed >>> 0) || 1;
  const rnd = () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296) - 0.5;
  const tau = { 'hr.now': 7, 'resp.rate': 5, 'spo2.pct': 6, 'skin.tempC': 18, 'hrv.rmssdMs': 8, 'eda.uS': 6, 'radiation.rateUsvH': 2 };
  const noise = { 'hr.now': 2.2, 'resp.rate': 0.9, 'spo2.pct': 0.5, 'skin.tempC': 0.06, 'hrv.rmssdMs': 3.5, 'eda.uS': 0.25, 'radiation.rateUsvH': 0 };
  const x = targets(base, 'rest');
  const total = TIMELINE.reduce((a, b) => a + b[1], 0);
  return {
    step(dt = 1, activity = 'rest') {
      const tg = targets(base, activity), out = {};
      for (const key of LIVE_KEYS) {
        x[key] += (tg[key] - x[key]) * (1 - Math.exp(-dt / tau[key]));
        let v = x[key] + rnd() * 2 * noise[key];
        if (key === 'radiation.rateUsvH') v = x[key] * (1 + rnd() * 0.16);
        out[key] = key === 'hr.now' || key === 'resp.rate' || key === 'spo2.pct' || key === 'hrv.rmssdMs' ? Math.round(v) : r1(v);
      }
      out['spo2.pct'] = clamp(out['spo2.pct'], 60, 100); out['hrv.rmssdMs'] = Math.max(4, out['hrv.rmssdMs']); out['resp.rate'] = Math.max(6, out['resp.rate']);
      return out;
    },
    activityAt(t) { let u = ((t % total) + total) % total; for (const [a, d] of TIMELINE) { if (u < d) return a; u -= d; } return 'rest'; }
  };
}

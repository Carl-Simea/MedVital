/* testdata.mjs — invented crew data for demos and tests. Nothing here is a real person or a real measurement.
   Three scenarios cover every input the app knows: one with everything in range, one with a few borderline and raised values,
   and one with several critical findings. The UI marks loaded test data as "Test data". Pure data, no DOM. */

export const SCENARIOS = Object.freeze({
  nominal: {
    label: 'In range', note: 'Mission month 2 · everything on target',
    body: { heightCm: 181, massKg: 79 },
    data: {
      'mission.month': 2, sex: 'm',
      'hr.rest': 58, 'bp.sys': 118, 'bp.dia': 74, 'spo2.pct': 98, 'resp.rate': 14, 'temp.c': 36.6,
      'orthostatic.presyncope': false, 'jugular.flow': 'normal', 'aerobic.changePct': -4, 'strength.changePct': -6,
      'bmd.hipPct': -2.4, 'bmd.lumbarPct': -1.6, 'bmd.wholeBodyPct': -0.4, 'back.pain': 2,
      'sans.hyperopicShiftD': 0.25, 'sans.discEdema': false, 'sans.choroidalFolds': false,
      'sleep.hours': 7.8, 'sleep.quality': 5, 'pvt.lapses': 1, 'pvt.meanRtMs': 241,
      'hemoglobin.gdl': 14.6, 'glucose.mgdl': 88, 'vitd.ngml': 34, 'urine.volumeL': 2.4, 'urine.calciumMgDay': 180,
      'radiation.careerMsv': 62, 'radiation.eventMsv': 0, 'virus.shedding': false, 'zoster.symptoms': false,
      'mass.changePct': -1.2, 'exercise.minPerWeek': 610, 'exercise.resistiveDays': 6,
      'nutrition.energyPct': 98, 'nutrition.proteinGkg': 1.5, 'nutrition.fluidL': 2.6
    },
    environment: ['Radiation background nominal', 'Cabin CO₂ within limits', 'Space weather quiet'],
    predictions: ['Bone density on track for month 2 (model)', 'Next strength test in 9 days']
  },
  mixed: {
    label: 'Borderline', note: 'Mission month 4 · some values to watch',
    body: { heightCm: 168, massKg: 61 },
    data: {
      'mission.month': 4, sex: 'f',
      'hr.rest': 74, 'bp.sys': 138, 'bp.dia': 86, 'spo2.pct': 96, 'resp.rate': 16, 'temp.c': 36.9,
      'orthostatic.presyncope': false, 'jugular.flow': 'stagnant', 'aerobic.changePct': -9, 'strength.changePct': -9,
      'bmd.hipPct': -8.1, 'bmd.lumbarPct': -4.6, 'bmd.wholeBodyPct': -1.0, 'back.pain': 3,
      'sans.hyperopicShiftD': 0.75, 'sans.discEdema': false, 'sans.choroidalFolds': false,
      'sleep.hours': 5.7, 'sleep.quality': 2, 'pvt.lapses': 12, 'pvt.meanRtMs': 312,
      'hemoglobin.gdl': 11.7, 'glucose.mgdl': 97, 'vitd.ngml': 18, 'urine.volumeL': 1.6, 'urine.calciumMgDay': 262,
      'radiation.careerMsv': 148, 'radiation.eventMsv': 0, 'virus.shedding': true, 'zoster.symptoms': false,
      'mass.changePct': -5.5, 'exercise.minPerWeek': 470, 'exercise.resistiveDays': 4,
      'nutrition.energyPct': 84, 'nutrition.proteinGkg': 1.1, 'nutrition.fluidL': 1.7
    },
    environment: ['Radiation background nominal', 'Cabin CO₂ at the upper limit', 'Space weather quiet'],
    predictions: ['Hip bone density is falling faster than the mean (model)', 'Urine volume low: stone risk']
  },
  critical: {
    label: 'Critical', note: 'Mission month 6 · several findings need the flight surgeon',
    body: { heightCm: 188, massKg: 86 },
    data: {
      'mission.month': 6, sex: 'm', 'pvt.confirmed': true,
      'hr.rest': 118, 'bp.sys': 86, 'bp.dia': 54, 'spo2.pct': 90, 'resp.rate': 26, 'temp.c': 38.7,
      'orthostatic.presyncope': true, 'jugular.flow': 'thrombus', 'aerobic.changePct': -22, 'strength.changePct': -24,
      'bmd.hipPct': -19.5, 'bmd.lumbarPct': -7.0, 'bmd.wholeBodyPct': -2.1, 'back.pain': 8,
      'sans.hyperopicShiftD': 1.5, 'sans.discEdema': true, 'sans.choroidalFolds': true,
      'sleep.hours': 4.2, 'sleep.quality': 1, 'pvt.lapses': 23, 'pvt.meanRtMs': 418,
      'hemoglobin.gdl': 12.4, 'glucose.mgdl': 132, 'vitd.ngml': 11, 'urine.volumeL': 0.9, 'urine.calciumMgDay': 340,
      'radiation.careerMsv': 505, 'radiation.eventMsv': 40, 'virus.shedding': true, 'zoster.symptoms': true,
      'mass.changePct': -11, 'exercise.minPerWeek': 240, 'exercise.resistiveDays': 2,
      'nutrition.energyPct': 62, 'nutrition.proteinGkg': 0.8, 'nutrition.fluidL': 1.2
    },
    environment: ['Solar particle event in progress', 'Cabin CO₂ above the limit', 'Shelter advised'],
    predictions: ['Hip bone loss is more than twice the mean (model)', 'Dehydration and stone risk rising']
  }
});
export const SCENARIO_IDS = Object.freeze(Object.keys(SCENARIOS));

/** Report labels the reader (intake.mjs) understands. Used to write a scenario as a plain-text report. */
const LINES = [
  ['mission.month', 'Mission month', ''], ['body.heightCm', 'Height', 'cm'], ['body.massKg', 'Body mass', 'kg'],
  ['hr.rest', 'Resting heart rate', 'bpm'], ['bp', 'Blood pressure', 'mmHg'], ['spo2.pct', 'SpO2', '%'], ['resp.rate', 'Respiratory rate', '/min'], ['temp.c', 'Body temperature', '°C'],
  ['orthostatic.presyncope', 'Dizziness on standing', ''], ['jugular.flow', 'Jugular vein flow', ''],
  ['aerobic.changePct', 'VO2peak change', '%'], ['strength.changePct', 'Muscle strength change', '%'],
  ['bmd.hipPct', 'Hip BMD change', '%'], ['bmd.lumbarPct', 'Lumbar spine BMD change', '%'], ['bmd.wholeBodyPct', 'Whole-body BMD change', '%'], ['back.pain', 'Back pain score', '/10'],
  ['sans.hyperopicShiftD', 'Hyperopic shift', 'D'], ['sans.discEdema', 'Optic disc edema', ''], ['sans.choroidalFolds', 'Choroidal folds', ''],
  ['sleep.hours', 'Sleep duration', 'h'], ['sleep.quality', 'Sleep quality', '/5'], ['pvt.lapses', 'PVT lapses', ''], ['pvt.meanRtMs', 'Mean reaction time', 'ms'],
  ['hemoglobin.gdl', 'Hemoglobin', 'g/dL'], ['glucose.mgdl', 'Blood glucose', 'mg/dL'], ['vitd.ngml', '25-OH vitamin D', 'ng/mL'],
  ['urine.calciumMgDay', 'Urinary calcium', 'mg/day'], ['urine.volumeL', '24-h urine volume', 'L'],
  ['radiation.eventMsv', 'Solar particle event dose', 'mSv'], ['radiation.careerMsv', 'Career radiation dose', 'mSv'],
  ['virus.shedding', 'Viral shedding', ''], ['zoster.symptoms', 'Shingles symptoms', ''],
  ['mass.changePct', 'Body mass change', '%'], ['exercise.minPerWeek', 'Exercise time per week', 'min'], ['exercise.resistiveDays', 'Resistance training days', ''],
  ['nutrition.energyPct', 'Energy intake', '%'], ['nutrition.proteinGkg', 'Protein intake', 'g/kg'], ['nutrition.fluidL', 'Fluid intake', 'L']
];
/** A scenario written as the kind of text report a crew member could paste into the app. */
export function reportText(id) {
  const s = SCENARIOS[id]; if (!s) return '';
  const d = { ...s.data, 'body.heightCm': s.body.heightCm, 'body.massKg': s.body.massKg }, out = ['CREW HEALTH SUMMARY (test data, invented)', ''];
  for (const [key, label, unit] of LINES) {
    if (key === 'bp') { out.push(`${label}: ${d['bp.sys']}/${d['bp.dia']} ${unit}`); continue; }
    const v = d[key]; if (v === undefined) continue;
    out.push(`${label}: ${typeof v === 'boolean' ? (v ? 'yes' : 'no') : v}${unit ? ' ' + unit : ''}`);
  }
  return out.join('\n');
}

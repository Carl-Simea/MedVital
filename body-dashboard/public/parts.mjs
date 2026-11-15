/* parts.mjs — per-part health model for MEDvital.
   Pure data + rules, no DOM, no network: the same input always gives the same output. Runs in the browser and in Node.
   DECISION SUPPORT, NOT A DIAGNOSIS. Every rule carries a `basis`:
     verified   – the statement or number comes from the cited NASA / peer-reviewed source
     reference  – a verified NASA reference value (e.g. mean bone loss per month) used as the comparison point;
                  the cut-offs around it are a convention
     convention – general clinical convention, not NASA-specific, not verified in this work
     model      – model output, not a measurement
   Parts with no verified spaceflight fact say so (`gap`) instead of showing invented text. */
import { SOURCES as BASE_SOURCES } from './knowledge.mjs';
import { evalHeartRate } from './engine.mjs';
import { CATALOG, PANEL_SRC, refRange, farRange } from './panels.mjs';

export const SRC = Object.freeze({
  ...BASE_SOURCES,
  ...PANEL_SRC,
  renalE057:   { kind: 'primary',   title: 'NASA HRP: Renal Stone Risk During Spaceflight (E057), 2007', url: 'https://ntrs.nasa.gov/citations/20070008213' },
  renalKcit:   { kind: 'primary',   title: 'Whitson et al.: Potassium citrate to reduce renal stone risk in spaceflight (NASA, 2009)', url: 'https://ntrs.nasa.gov/api/citations/20090019087/downloads/20090019087.pdf' },
  renalFluid:  { kind: 'primary',   title: 'Renal stone risk assessment in astronauts (NASA Glenn / PMC)', url: 'https://pmc.ncbi.nlm.nih.gov/articles/8799707' },
  rbc:         { kind: 'secondary', title: 'Trudel et al., Nature Medicine 2022: hemolysis contributes to space anemia (press release)', url: 'https://www.eurekalert.org/news-releases/939794' },
  rbcDetail:   { kind: 'secondary', title: 'Ottawa Hospital: five of 13 astronauts anemic at landing, fluid shift', url: 'https://ohri.ca/en/newsroom/being-space-destroys-more-red-blood-cells' },
  radLimit:    { kind: 'primary',   title: 'NASA-STD-3001 technical brief: career limit 600 mSv, 250 mSv per solar particle event', url: 'https://www.nasa.gov/wp-content/uploads/2023/03/radiation-protection-technical-brief-ochmo.pdf' },
  spine:       { kind: 'primary',   title: 'Chang et al., Spine 2016: paraspinal muscle and disc changes after ISS missions', url: 'https://pmc.ncbi.nlm.nih.gov/articles/pmid/27779600' },
  immuneER:    { kind: 'primary',   title: 'NASA Evidence Report: Risk of Crew Adverse Health Event Due to Altered Immune Response', url: 'https://ntrs.nasa.gov/api/citations/20140002769/downloads/20140002769.pdf' },
  herpes:      { kind: 'primary',   title: 'Mehta & Bloom, Frontiers in Microbiology 2019: herpes virus reactivation in astronauts', url: 'https://pmc.ncbi.nlm.nih.gov/articles/PMC6374706' },
  dustER:      { kind: 'primary',   title: 'NASA Evidence Report: Risk of Adverse Health Effects of Celestial Dust Exposure (2015)', url: 'https://ntrs.nasa.gov/api/citations/20150016031/downloads/20150016031.pdf' },
  dustApollo:  { kind: 'secondary', title: 'AGU/Phys.org 2018: Apollo 17 "lunar hay fever" and lunar-dust toxicity', url: 'https://phys.org/news/2018-05-lunar-pose-health-future-astronauts.html' },
  dustUts:     { kind: 'secondary', title: 'UTS 2025: lunar dust less harmful to human lung cells than feared', url: 'https://www.eurekalert.org/news-releases/1087743' },
  lungPrisk:   { kind: 'secondary', title: 'Prisk review (MJA InSight+ 2019): lungs in partial and zero gravity', url: 'https://insightplus.mja.com.au/2019/36/lungs-in-space-danger-in-the-dust' },
  arteries:    { kind: 'primary',   title: 'NASA Cardio-Ox: carotid and brachial artery structure and function before, during and after ISS flight', url: 'https://ntrs.nasa.gov/api/citations/20200001714/downloads/20200001714.pdf' },
  rhythm:      { kind: 'primary',   title: 'NASA Evidence Report: Risk of Cardiac Rhythm Problems During Spaceflight', url: 'https://ntrs.nasa.gov/citations/20170005625' },
  nutrition:   { kind: 'primary',   title: 'Smith & Zwart (NASA JSC): Nutrition issues for space exploration', url: 'https://ntrs.nasa.gov/api/citations/20060049121/downloads/20060049121.pdf' },
  nutritionPg: { kind: 'primary',   title: 'NASA: Studying the role of nutrition in spaceflight', url: 'https://www.nasa.gov/?p=209742' },
  nutBone:     { kind: 'primary',   title: 'NASA HRP (2014): nutrition, vitamin D and exercise for bone', url: 'https://ntrs.nasa.gov/api/citations/20140009569/downloads/20140009569.pdf' },
  gutTransit:  { kind: 'secondary', title: 'Nature Communications 2026 (via Space.com): gut protein fermentation in 52 astronauts', url: 'https://space.com/space-exploration/human-spaceflight/its-harder-to-poop-in-space-scientists-may-finally-know-why' },
  stdMeasures: { kind: 'primary',   title: 'NASA: Spaceflight Standard Measures (actigraphy, cognition, blood, urine and saliva markers, carotid ultrasound, sensorimotor tests)', url: 'https://www.nasa.gov/humans-in-space/spaceflight-standard-measures-characterizing-how-humans-adapt-in-space' },
  artemis2:    { kind: 'primary',   title: 'NASA: Artemis II crew health research (ARCHeR wristbands, immune biomarkers, standard measures, radiation sensors)', url: 'https://www.nasa.gov/general/artemis-ii-crew-both-subjects-and-scientists-in-nasa-deep-space-research' },
  bioMonitor:  { kind: 'primary',   title: 'Canadian Space Agency: Bio-Monitor smart shirt (heart activity, blood pressure, breathing, skin temperature, blood oxygen, activity)', url: 'https://www.asc-csa.gc.ca/eng/sciences/bio-monitor.asp' },
  sansConsensus:{ kind: 'secondary', title: 'SANS expert consensus in Eye, 2026 (reported by The Ophthalmologist): 20 µm retinal thickening as earliest sign, 55 µm as concerning', url: 'https://theophthalmologist.com/issues/2026/articles/august/standardizing-sans-in-spaceflight/' },
  liverMouse:  { kind: 'primary',   title: 'Lipid accumulation in the livers of mice flown on the ISS (Scientific Reports 2019)', url: 'https://www.nature.com/articles/s41598-019-55869-2' }
});

export const LEVEL = Object.freeze({ nodata: -1, ok: 0, watch: 1, warn: 2, alert: 3 });
export const LEVEL_NAME = ['ok', 'watch', 'warn', 'alert'];
export const LEVEL_LABEL = Object.freeze({ '-1': 'No data', 0: 'Normal', 1: 'Watch', 2: 'Elevated', 3: 'Critical' });
export const BASIS = Object.freeze({
  verified: 'Verified against the cited source',
  reference: 'Compared with a verified NASA reference value; the cut-offs are a convention',
  convention: 'General clinical convention, not NASA-specific',
  model: 'Model, not a measurement'
});

/* ---------- Indicators: what NASA measures, and whether it can be measured in flight ---------- */
const BASE_INDICATORS = {
  'hr.rest':               { label: 'Resting heart rate', unit: 'bpm', how: 'Pulse or wearable at rest', flight: true },
  'orthostatic.presyncope':{ label: 'Dizziness on standing', unit: '', how: 'Symptom report, stand test', flight: true, type: 'bool' },
  'jugular.flow':          { label: 'Jugular vein flow', unit: '', how: 'Ultrasound of the internal jugular vein', flight: true, type: 'text' },
  'bmd.hipPct':            { label: 'Hip bone density change', unit: '%', how: 'DXA scan before and after flight only', flight: false },
  'bmd.lumbarPct':         { label: 'Lumbar spine bone density change', unit: '%', how: 'DXA scan before and after flight only', flight: false },
  'bmd.wholeBodyPct':      { label: 'Whole-body bone density change', unit: '%', how: 'DXA scan before and after flight only', flight: false },
  'back.pain':             { label: 'Back pain', unit: '/10', how: 'Self-report, 0 to 10', flight: true },
  'strength.changePct':    { label: 'Strength change vs. preflight', unit: '%', how: 'Strength testing', flight: true },
  'aerobic.changePct':     { label: 'Aerobic fitness change', unit: '%', how: 'Cycle ergometer test (VO2peak)', flight: true },
  'sans.hyperopicShiftD':  { label: 'Hyperopic (far-sighted) shift', unit: 'D', how: 'Refraction / near-vision test', flight: true },
  'sans.discEdema':        { label: 'Optic disc swelling', unit: '', how: 'OCT and fundus imaging', flight: true, type: 'bool' },
  'sans.choroidalFolds':   { label: 'Choroidal folds', unit: '', how: 'OCT and fundus imaging', flight: true, type: 'bool' },
  'sleep.hours':           { label: 'Sleep per night', unit: 'h', how: 'Sleep log or wearable', flight: true },
  'pvt.lapses':            { label: 'Alertness test lapses', unit: '', how: 'Reaction test (PVT), lapse = 355 ms or slower', flight: true },
  'hemoglobin.gdl':        { label: 'Hemoglobin', unit: 'g/dL', how: 'Blood test', flight: true },
  'urine.volumeL':         { label: 'Urine volume per 24 h', unit: 'L', how: '24-hour urine collection', flight: true },
  'urine.calciumMgDay':    { label: 'Urinary calcium per 24 h', unit: 'mg', how: '24-hour urine collection', flight: true },
  'radiation.careerMsv':   { label: 'Career radiation dose', unit: 'mSv', how: 'Personal dosimeter and models', flight: true },
  'radiation.eventMsv':    { label: 'Dose from the latest solar particle event', unit: 'mSv', how: 'Personal dosimeter and models', flight: true },
  'virus.shedding':        { label: 'Latent virus shedding (EBV, VZV, CMV)', unit: '', how: 'Saliva and urine samples', flight: true, type: 'bool' },
  'zoster.symptoms':       { label: 'Shingles-like skin symptoms', unit: '', how: 'Symptom report, exam', flight: true, type: 'bool' },
  'bp.sys':                { label: 'Blood pressure, systolic', unit: 'mmHg', how: 'Cuff or wearable', flight: true },
  'bp.dia':                { label: 'Blood pressure, diastolic', unit: 'mmHg', how: 'Cuff or wearable', flight: true },
  'spo2.pct':              { label: 'Blood oxygen (SpO2)', unit: '%', how: 'Pulse oximeter', flight: true },
  'resp.rate':             { label: 'Breathing rate', unit: '/min', how: 'Count or wearable', flight: true },
  'temp.c':                { label: 'Body temperature', unit: '°C', how: 'Thermometer', flight: true },
  'glucose.mgdl':          { label: 'Blood glucose', unit: 'mg/dL', how: 'Finger-prick or blood test', flight: true },
  'mass.changePct':        { label: 'Body mass change vs. preflight', unit: '%', how: 'Mass measurement device', flight: true },
  'vitd.ngml':             { label: 'Vitamin D (25-OH)', unit: 'ng/mL', how: 'Blood test', flight: true },
  // Continuous values from wearables (live). `rate: false` means the value is shown and tracked but not rated,
  // because no verified threshold exists or it only means something against the personal baseline.
  'hr.now':                { label: 'Heart rate now', unit: 'bpm', how: 'ECG shirt or wrist wearable, continuous', flight: true, live: true },
  'hrv.rmssdMs':           { label: 'Heart rate variability (RMSSD)', unit: 'ms', how: 'ECG shirt or wrist wearable', flight: true, live: true, rate: false },
  'skin.tempC':            { label: 'Skin temperature', unit: '°C', how: 'Smart shirt or wrist wearable', flight: true, live: true, rate: false },
  'eda.uS':                { label: 'Skin conductance (stress arousal)', unit: 'µS', how: 'Wrist wearable', flight: true, live: true, rate: false },
  'radiation.rateUsvH':    { label: 'Radiation dose rate', unit: 'µSv/h', how: 'Personal active dosimeter', flight: true, live: true, rate: false },
  // Behaviour and sensorimotor
  'sleep.efficiencyPct':   { label: 'Sleep efficiency', unit: '%', how: 'Wrist actigraphy', flight: true },
  'cognition.scorePct':    { label: 'Cognition tests vs. own baseline', unit: '%', how: 'Computer test battery (10 tests)', flight: true, rate: false },
  'stress.score':          { label: 'Stress, self-rated', unit: '/5', how: 'Pre-sleep questionnaire', flight: true, rate: false },
  'mood.score':            { label: 'Mood, self-rated', unit: '/5', how: 'Pre-sleep questionnaire', flight: true, rate: false },
  'motion.sickness':       { label: 'Motion sickness', unit: '/10', how: 'Symptom report, 0 to 10', flight: true },
  'balance.changePct':     { label: 'Balance test vs. preflight', unit: '%', how: 'Sensorimotor tests before and after flight', flight: false, rate: false },
  // Blood
  'wbc.k':                 { label: 'White blood cells', unit: 'k/µL', how: 'Blood count', flight: true },
  'platelets.k':           { label: 'Platelets', unit: 'k/µL', how: 'Blood count', flight: true },
  'hematocrit.pct':        { label: 'Hematocrit', unit: '%', how: 'Blood count', flight: true },
  'ferritin.ngml':         { label: 'Ferritin (iron stores)', unit: 'ng/mL', how: 'Blood test', flight: true },
  'sodium.mmol':           { label: 'Sodium', unit: 'mmol/L', how: 'Blood chemistry', flight: true },
  'potassium.mmol':        { label: 'Potassium', unit: 'mmol/L', how: 'Blood chemistry', flight: true },
  'creatinine.mgdl':       { label: 'Creatinine', unit: 'mg/dL', how: 'Blood chemistry', flight: true },
  'calcium.mgdl':          { label: 'Serum calcium', unit: 'mg/dL', how: 'Blood chemistry', flight: true },
  'crp.mgl':               { label: 'C-reactive protein (inflammation)', unit: 'mg/L', how: 'Blood test', flight: true },
  'cortisol.ugdl':         { label: 'Cortisol (stress hormone)', unit: 'µg/dL', how: 'Blood or saliva sample', flight: true, rate: false },
  // Imaging and urine
  'cimt.mm':               { label: 'Carotid wall thickness (CIMT)', unit: 'mm', how: 'Ultrasound of the carotid artery', flight: true, rate: false },
  'sans.trtChangeUm':      { label: 'Retinal thickness change at the optic disc', unit: 'µm', how: 'OCT, compared with preflight', flight: true },
  'urine.citrateMgDay':    { label: 'Urinary citrate per 24 h', unit: 'mg', how: '24-hour urine collection', flight: true },
  'urine.ph':              { label: 'Urine pH', unit: '', how: 'Urine test strip or 24-hour collection', flight: true },
  'kidney.stone':          { label: 'Kidney stone on ultrasound', unit: '', how: 'Ultrasound of the kidneys', flight: true, type: 'bool' }
};
/* The detailed catalogue (panels.mjs): lab panels, exams, sleep stages, exercise and nutrition detail. */
export const INDICATORS = Object.freeze({
  ...BASE_INDICATORS,
  ...Object.fromEntries(CATALOG.map(x => [x.key, { label: x.label, unit: x.unit, how: x.how, flight: x.flight !== false, panel: x.panel, msrc: x.msrc || null, ...(x.ref ? {} : { rate: false }) }]))
});
export const WHY = Object.freeze({
  'hr.rest': 'A resting heart rate that drifts above the personal baseline is an early sign of cardiovascular strain or dehydration.',
  'orthostatic.presyncope': 'Orthostatic intolerance is the main in-mission cardiovascular risk and matters most at landing and on a planetary surface.',
  'jugular.flow': 'Slow or reversed jugular flow was seen in flight; a clot needs fast action.',
  'bmd.hipPct': 'Weight-bearing bone is lost in flight; only a DXA scan before and after flight measures it.',
  'bmd.lumbarPct': 'Weight-bearing bone is lost in flight; only a DXA scan before and after flight measures it.',
  'bmd.wholeBodyPct': 'Whole-body bone loss is small but shows the overall skeletal trend.',
  'back.pain': 'Spine pain is common in flight and can point to disc or muscle problems.',
  'strength.changePct': 'Muscle loss reduces the ability to perform mission tasks and to land safely.',
  'aerobic.changePct': 'Aerobic fitness falls without exercise and limits work capacity.',
  'sans.hyperopicShiftD': 'Eye and optic-nerve changes can reduce vision during and after long missions.',
  'sans.discEdema': 'Optic disc swelling is a core sign of SANS.',
  'sans.choroidalFolds': 'Choroidal folds are a core sign of SANS.',
  'sleep.hours': 'Sleep loss impairs performance and mood.',
  'pvt.lapses': 'The reaction test measures alertness objectively; self-rated tiredness is unreliable.',
  'hemoglobin.gdl': 'Red blood cells are destroyed faster in flight; anemia shows most after landing.',
  'urine.volumeL': 'Low urine volume raises kidney-stone risk.',
  'urine.calciumMgDay': 'Bone loss puts extra calcium into the urine, which raises kidney-stone risk.',
  'radiation.careerMsv': 'Career dose limits protect against cancer and degenerative effects.',
  'radiation.eventMsv': 'A solar particle event can deliver a large dose in hours; the single-event limit is the shelter trigger.',
  'virus.shedding': 'Latent viruses reactivate in flight, a sign of altered immune function.',
  'zoster.symptoms': 'Shingles-like symptoms mean a latent virus is active.',
  'bp.sys': 'Blood pressure shows cardiovascular load; both very high and very low values matter.',
  'bp.dia': 'Blood pressure shows cardiovascular load; both very high and very low values matter.',
  'spo2.pct': 'Low blood oxygen can signal a breathing or cabin-air problem.',
  'resp.rate': 'A changed breathing rate is an early sign of lung, heart or air-quality problems.',
  'temp.c': 'Fever signals infection; in a closed habitat it can spread to the crew.',
  'glucose.mgdl': 'Blood glucose shows energy metabolism; stress, inactivity and diet change it.',
  'mass.changePct': 'Unplanned mass loss means energy intake is too low, which also costs bone and muscle.',
  'vitd.ngml': 'Without sunlight, vitamin D must be supplemented; it supports bone health.',
  'hr.now': 'The live heart rate shows load and recovery; only values at rest are rated.',
  'hrv.rmssdMs': 'Heart rate variability falls with stress, fatigue and illness; it is read against the personal baseline.',
  'skin.tempC': 'Skin temperature follows activity, sleep phase and cabin climate.',
  'eda.uS': 'Skin conductance rises with arousal and stress.',
  'radiation.rateUsvH': 'The dose rate shows a solar particle event as it happens.',
  'sleep.efficiencyPct': 'Time asleep as a share of time in bed, measured by movement.',
  'cognition.scorePct': 'Thinking speed and accuracy can drop with sleep loss, stress and CO2.',
  'stress.score': 'NASA asks crews about mood, team cohesion and workload before sleep.',
  'mood.score': 'NASA asks crews about mood, team cohesion and workload before sleep.',
  'motion.sickness': 'Space motion sickness is common in the first days and after landing.',
  'balance.changePct': 'Balance is disturbed after landing; it decides how soon a crew can work on a surface.',
  'wbc.k': 'White blood cells show infection and immune changes.',
  'platelets.k': 'Platelets matter for clotting.',
  'hematocrit.pct': 'Blood plasma falls early in flight, which changes the share of red cells.',
  'ferritin.ngml': 'Iron stores change in flight as red blood cell production changes.',
  'sodium.mmol': 'Sodium shows fluid balance.',
  'potassium.mmol': 'Potassium outside its range can disturb the heart rhythm.',
  'creatinine.mgdl': 'Creatinine shows kidney function and hydration.',
  'calcium.mgdl': 'Bone loss releases calcium.',
  'crp.mgl': 'A raised value points to inflammation or infection.',
  'cortisol.ugdl': 'Stress hormones are part of the NASA standard measures; the value depends on the time of day.',
  'cimt.mm': 'NASA scans the carotid wall to watch for early artery changes.',
  'sans.trtChangeUm': 'Thickening of the retina around the optic disc is the earliest measurable sign of disc swelling.',
  'urine.citrateMgDay': 'Citrate holds calcium in solution; it falls in flight.',
  'urine.ph': 'Acidic urine favours some kidney stones; pH falls in flight.',
  'kidney.stone': 'A stone could impair a crew member in flight.'
});

/* ---------- Parts: one entry per anatomy group ---------- */
const f = (t, s) => ({ t, s });
const SKEL_HELPS = [
  f('Resistive exercise (ARED), treadmill (T2) and cycle ergometer (CEVIS) are the ISS countermeasures; crew now average about two hours of exercise a day.', 'exerciseIss'),
  f('Resistance exercise with adequate energy intake and good vitamin D status can maintain bone in most regions during 4–6 month missions.', 'nutBone')
];
const BONE_NOTE = f('Bone loss is not measured in flight; the per-month rates come from pre- and postflight DXA scans.', 'boneSibonga13');
const MUSC_HELPS = [f('Exercise devices on the ISS: ARED, T2 treadmill, CEVIS cycle.', 'exerciseIss')];
const MUSC_FACTS = [
  f('ISS data show average losses of 10–12 % of pre-mission strength and aerobic fitness.', 'fitnessRisk'),
  f('12–38 % of ISS crew lose more than 20 % of pre-mission fitness, depending on the measure.', 'fitnessRisk')
];
const SPINE_FACTS = [
  f('Over half of US astronauts report spine pain during missions; 50 % of reports are low back, 11 % mid back, 11 % neck.', 'spine'),
  f('The torso lengthens 4–6 cm in flight.', 'spine'),
  f('NASA crew have a 4.3 times higher risk of herniated discs than the general and military aviator populations, highest in the first year after a mission.', 'spine'),
  f('MRI of six crew members showed shrinking of the paraspinal muscles after six months on the ISS.', 'spine')
];
const SPINE_HELPS = [f('Astronauts report that a lumbar-flexed "fetal tuck" position is the most effective way to ease back pain in flight.', 'spine')];

export const PARTS = Object.freeze({
  skull:   { label: 'Skull', system: 'skeleton', does: 'Protects the brain and anchors the face and jaw.', ind: ['bmd.wholeBodyPct'], facts: [f('Bone mineral density falls on average 1–1.5 % per month in weight-bearing skeletal sites; whole body about 0.3 % per month.', 'boneER2017'), BONE_NOTE], helps: SKEL_HELPS },
  spineC:  { label: 'Cervical spine (neck)', system: 'skeleton', does: 'Carries the head and protects the spinal cord in the neck.', ind: ['back.pain', 'bmd.wholeBodyPct'], facts: [...SPINE_FACTS, BONE_NOTE], helps: [...SPINE_HELPS, ...SKEL_HELPS] },
  spineT:  { label: 'Thoracic spine (mid back)', system: 'skeleton', does: 'Supports the rib cage and upper body.', ind: ['back.pain', 'bmd.wholeBodyPct'], facts: [...SPINE_FACTS, BONE_NOTE], helps: [...SPINE_HELPS, ...SKEL_HELPS] },
  spineL:  { label: 'Lumbar spine (low back)', system: 'skeleton', does: 'Carries most of the upper body weight on Earth.', ind: ['back.pain', 'bmd.lumbarPct', 'bmd.wholeBodyPct'], facts: [f('Lumbar spine bone density falls about 1 % per month (DXA).', 'boneSibonga15'), ...SPINE_FACTS, BONE_NOTE], helps: [...SPINE_HELPS, ...SKEL_HELPS] },
  ribs:    { label: 'Rib cage', system: 'skeleton', does: 'Protects heart and lungs and moves with breathing.', ind: ['bmd.wholeBodyPct'], facts: [BONE_NOTE], helps: SKEL_HELPS, gap: 'No site-specific spaceflight figure collected for the ribs; the whole-body skeleton figures apply.' },
  shoulder:{ label: 'Shoulder girdle', system: 'skeleton', does: 'Collarbone and shoulder blade connect the arm to the trunk.', ind: ['bmd.wholeBodyPct'], facts: [BONE_NOTE], helps: SKEL_HELPS, gap: 'No site-specific spaceflight figure collected for the shoulder girdle.' },
  arm:     { label: 'Arm bones', system: 'skeleton', does: 'Upper-arm and forearm bones.', ind: ['bmd.wholeBodyPct'], facts: [BONE_NOTE], helps: SKEL_HELPS, gap: 'No site-specific spaceflight figure collected for the arm bones.' },
  hand:    { label: 'Hand bones', system: 'skeleton', does: 'Wrist and finger bones.', ind: ['bmd.wholeBodyPct'], facts: [BONE_NOTE], helps: SKEL_HELPS, gap: 'No site-specific spaceflight figure collected for the hand bones.' },
  pelvis:  { label: 'Pelvis and hip', system: 'skeleton', does: 'Transfers body weight to the legs.', ind: ['bmd.hipPct', 'bmd.wholeBodyPct'], facts: [f('Hip bone density falls about 1.5 % per month (DXA), the largest site-specific rate.', 'boneSibonga15'), f('Average loss of 1–1.5 % per month in weight-bearing sites.', 'boneER2017'), BONE_NOTE], helps: SKEL_HELPS },
  femur:   { label: 'Thigh bone (femur)', system: 'skeleton', does: 'Longest and strongest bone; the hip joint sits at its top.', ind: ['bmd.hipPct', 'bmd.wholeBodyPct'], facts: [f('Hip bone density falls about 1.5 % per month (DXA).', 'boneSibonga15'), f('Average loss of 1–1.5 % per month in weight-bearing sites.', 'boneER2017'), BONE_NOTE], helps: SKEL_HELPS },
  shin:    { label: 'Lower-leg bones', system: 'skeleton', does: 'Tibia and fibula carry weight below the knee.', ind: ['bmd.wholeBodyPct'], facts: [f('Weight-bearing sites lose the most bone on average (1–1.5 % per month).', 'boneER2017'), BONE_NOTE], helps: SKEL_HELPS, gap: 'No site-specific figure collected for the lower leg.' },
  foot:    { label: 'Foot bones', system: 'skeleton', does: 'Ankle and foot bones.', ind: ['bmd.wholeBodyPct'], facts: [BONE_NOTE], helps: SKEL_HELPS, gap: 'No site-specific spaceflight figure collected for the foot bones.' },

  heart:   { label: 'Heart', system: 'cardio', does: 'Pumps blood through the body.', ind: ['hr.rest', 'orthostatic.presyncope', 'aerobic.changePct', 'bp.sys', 'bp.dia', 'hr.now', 'hrv.rmssdMs', 'potassium.mmol'],
    facts: [f('Orthostatic intolerance is the primary in-mission cardiovascular risk, particularly in low Earth orbit and on the lunar surface.', 'cvRisk'),
            f('Cardiovascular disease is a significant long-term risk, especially for missions beyond low Earth orbit.', 'cvRisk'),
            f('NASA found no definitive evidence that spaceflight increases the frequency of cardiac arrhythmias; a few cases, including one non-sustained ventricular tachycardia, are documented.', 'rhythm')],
    helps: [f('Exercise and a healthy diet help maintain cardiovascular fitness; compression garments and fluids before landing help prevent low blood pressure.', 'cvRiskPage')] },
  artery:  { label: 'Arteries', system: 'cardio', does: 'Carry oxygen-rich blood from the heart.', ind: ['orthostatic.presyncope', 'bp.sys', 'bp.dia', 'cimt.mm'],
    facts: [f('Carotid and brachial artery structure and stiffness did not change on average in 13 astronauts during ISS missions, although markers of oxidative stress and inflammation rose.', 'arteries')],
    helps: [f('Exercise and a healthy diet help maintain cardiovascular fitness.', 'cvRiskPage')] },
  vein:    { label: 'Veins', system: 'cardio', does: 'Return blood to the heart.', ind: ['jugular.flow', 'orthostatic.presyncope'],
    facts: [f('Stagnant or reverse flow in the internal jugular vein was seen in 6 of 11 crew members tested; one occlusive clot needed treatment in flight.', 'cvVte')],
    helps: [f('Report any one-sided neck swelling or pain to the flight surgeon; imaging by ultrasound is possible on the ISS.', 'cvVte')] },
  lung:    { label: 'Lungs', system: 'lung', does: 'Exchange oxygen and carbon dioxide.', ind: ['aerobic.changePct', 'spo2.pct', 'resp.rate'],
    facts: [f('Studies show the lung continues to function well in partial and zero gravity and returns quickly to Earth-normal function after flight.', 'lungPrisk'),
            f('Apollo astronauts described "lunar hay fever" (sneezing, watery eyes, sore throat) after lunar dust entered the cabin.', 'dustApollo'),
            f('Evidence on lunar-dust toxicity is mixed: animal and cell studies show inflammation, while a 2025 lab study found less harm to human lung cells than feared.', 'dustUts')],
    helps: [f('NASA collects the evidence on celestial dust exposure in a dedicated evidence report.', 'dustER')] },
  airway:  { label: 'Airways', system: 'lung', does: 'Windpipe and bronchi carry air to the lungs.', ind: ['resp.rate'],
    facts: [f('Apollo astronauts described "lunar hay fever" (sneezing, watery eyes, sore throat) after lunar dust entered the cabin.', 'dustApollo')], helps: [], gap: 'No airway measurement is connected; dust exposure matters mainly on the Moon.' },
  liver:   { label: 'Liver', system: 'digest', does: 'Processes nutrients, makes bile and clears toxins.', ind: ['glucose.mgdl'],
    facts: [f('In mice flown on the ISS, fat accumulated in the liver in every experiment, consistent with early signs of liver disease; human evidence is not established.', 'liverMouse')],
    helps: [], gap: 'Animal evidence only; no verified human measurement or threshold collected.' },
  stomach: { label: 'Stomach', system: 'digest', does: 'Starts the digestion of food.', ind: ['mass.changePct', 'motion.sickness'],
    facts: [f('It is thought that food settles differently in the stomach in weightlessness, which can make astronauts feel full before they eat enough.', 'nutritionPg')],
    helps: [], gap: 'Little verified data; energy intake is tracked through nutrition assessment.' },
  intestine:{ label: 'Intestines', system: 'digest', does: 'Absorb nutrients and water.', ind: ['mass.changePct'],
    facts: [f('Blood tests of 52 astronauts suggest gut bacteria ferment more protein in flight; this points to slower transit, but transit time was not measured.', 'gutTransit')],
    helps: [], gap: 'Constipation is common; no verified threshold collected.' },
  kidney:  { label: 'Kidneys', system: 'digest', does: 'Filter blood and make urine.', ind: ['urine.volumeL', 'urine.calciumMgDay', 'urine.citrateMgDay', 'urine.ph', 'kidney.stone', 'creatinine.mgdl', 'sodium.mmol', 'potassium.mmol'],
    facts: [f('In flight, urine volume, pH and citrate fall and urinary calcium rises, which raises the risk of kidney stones.', 'renalE057'),
            f('Urine changes appear as early as flight day 3–4 on short missions and the risk stays elevated on landing day.', 'renalE057'),
            f('A stone could impair a crew member in flight; bone loss adds calcium to the urine.', 'renalKcit')],
    helps: [f('Increasing fluid intake is recommended to all crew members.', 'renalE057'),
            f('Potassium citrate reduced urinary calcium and kept stone risk at preflight levels in treated crew.', 'renalKcit'),
            f('Lower protein, sodium and oxalate intake while keeping calcium at recommended levels.', 'renalKcit')] },
  spleen:  { label: 'Spleen (blood health)', system: 'digest', does: 'Filters the blood and removes worn-out red blood cells (general anatomy).', ind: ['hemoglobin.gdl', 'hematocrit.pct', 'wbc.k', 'platelets.k', 'ferritin.ngml'],
    facts: [f('Astronauts destroyed 54 % more red blood cells in flight (3 million per second instead of 2 million), measured in 14 astronauts over six months.', 'rbc'),
            f('Five of 13 astronauts were clinically anemic at landing; the effect resolved over 3–4 months, but red-cell destruction stayed 30 % above preflight levels one year later.', 'rbcDetail'),
            f('Past research suggests astronauts need less iron on long missions because red blood cell production changes.', 'nutritionPg')],
    helps: [f('Screening for existing blood conditions before flight and an adapted diet are suggested.', 'rbc')] },

  brain:   { label: 'Brain', system: 'brain', does: 'Controls thinking, movement and sleep.', ind: ['pvt.lapses', 'sleep.hours', 'sleep.efficiencyPct', 'cognition.scorePct', 'stress.score', 'mood.score', 'motion.sickness', 'balance.changePct'],
    facts: [f('Sleep loss is apparent during spaceflight, and ground evidence suggests it leads to performance impairment.', 'sleepER'),
            f('The 3-minute PVT with a 355 ms lapse threshold is as sensitive to sleep loss as the 10-minute PVT.', 'pvtB'),
            f('SANS (spaceflight associated neuro-ocular syndrome) combines eye and optic nerve changes.', 'sans')],
    helps: [] , gap: 'No verified countermeasure list collected for sleep in this work.' },
  eye:     { label: 'Eye', system: 'brain', does: 'Capture light and send images to the brain.', ind: ['sans.hyperopicShiftD', 'sans.discEdema', 'sans.choroidalFolds', 'sans.trtChangeUm'],
    facts: [f('SANS covers optic disc edema, globe flattening, choroidal and retinal folds and hyperopic shifts.', 'sans'),
            f('A reported symptom is reduced near vision: hyperopic shift of +0.50 to +1.75 D in six astronauts.', 'sans'),
            f('A prospective cohort of 11 astronauts showed optic disc edema and choroidal thickening on 6-month ISS missions, measured by imaging.', 'sansCohort')],
    helps: [], gap: 'No verified countermeasure collected; report vision changes to the flight surgeon.' },

  mHead:   { label: 'Head and neck muscles', system: 'muscle', does: 'Move the head, face and jaw.', ind: ['strength.changePct'], facts: MUSC_FACTS, helps: MUSC_HELPS },
  mChest:  { label: 'Chest, shoulder and back muscles', system: 'muscle', does: 'Move the shoulders and stabilise the trunk.', ind: ['strength.changePct', 'back.pain'], facts: [...MUSC_FACTS, SPINE_FACTS[3]], helps: MUSC_HELPS },
  mAbdomen:{ label: 'Abdominal and trunk muscles', system: 'muscle', does: 'Stabilise the trunk and support the spine.', ind: ['strength.changePct', 'back.pain'], facts: MUSC_FACTS, helps: MUSC_HELPS },
  mUpperArm:{ label: 'Upper-arm muscles', system: 'muscle', does: 'Bend and straighten the elbow.', ind: ['strength.changePct'], facts: MUSC_FACTS, helps: MUSC_HELPS },
  mForearm:{ label: 'Forearm muscles', system: 'muscle', does: 'Move the wrist and fingers.', ind: ['strength.changePct'], facts: MUSC_FACTS, helps: MUSC_HELPS },
  mThigh:  { label: 'Thigh muscles', system: 'muscle', does: 'Extend the knee and move the hip.', ind: ['strength.changePct'], facts: MUSC_FACTS, helps: MUSC_HELPS },
  mShin:   { label: 'Lower-leg muscles', system: 'muscle', does: 'Move the ankle and foot.', ind: ['strength.changePct'], facts: MUSC_FACTS, helps: MUSC_HELPS },
  tendon:  { label: 'Tendons', system: 'muscle', does: 'Connect muscles to bones.', ind: [], facts: [], helps: [], gap: 'No verified spaceflight data collected for tendons.' },

  body:    { label: 'Whole body', system: 'body', does: 'Effects that act on every organ.', ind: ['radiation.careerMsv', 'radiation.eventMsv', 'virus.shedding', 'zoster.symptoms', 'sleep.hours', 'temp.c', 'glucose.mgdl', 'mass.changePct', 'vitd.ngml', 'skin.tempC', 'eda.uS', 'radiation.rateUsvH', 'crp.mgl', 'cortisol.ugdl', 'calcium.mgdl'],
    facts: [f('NASA lists five human-spaceflight hazards: radiation, isolation and confinement, distance from Earth, gravity fields, and hostile/closed environments.', 'hrpHazards'),
            f('Career radiation dose must stay below 600 mSv; a single solar particle event is limited to 250 mSv.', 'radLimit'),
            f('Immune function is altered in and after flight; latent herpes viruses reactivate, but this has not been directly tied to disease.', 'immuneER'),
            f('Viral shedding (EBV, VZV, CMV) in saliva and urine is usually without symptoms.', 'herpes'),
            f('Astronauts lose about 10 % of the liquid in their blood vessels as fluids shift upward.', 'rbcDetail')],
    helps: [], gap: null }
});

for (const x of CATALOG) for (const g of x.groups) if (PARTS[g] && !PARTS[g].ind.includes(x.key)) PARTS[g].ind.push(x.key);
PARTS.brain.facts.push(f('Polysomnography on two Shuttle flights showed more wakefulness and less slow-wave sleep in the final third of the night, and markedly more REM sleep after landing.', 'dijk'));
export const GROUP_IDS = Object.freeze(Object.keys(PARTS));
/** Groups where the left/right side is meaningful and clickable. */
export const PAIRED = Object.freeze(['shoulder', 'arm', 'hand', 'femur', 'shin', 'foot', 'lung', 'kidney', 'eye', 'mUpperArm', 'mForearm', 'mThigh', 'mShin', 'tendon']);
export const SKELETON_GROUPS = GROUP_IDS.filter(g => PARTS[g].system === 'skeleton');
export const MUSCLE_GROUPS = GROUP_IDS.filter(g => PARTS[g].system === 'muscle');

/* ---------- Rules ---------- */
const num = v => typeof v === 'number' && Number.isFinite(v);
const RULES = [];
const rule = (id, groups, fn) => RULES.push({ id, groups, fn });
const r = (level, text, basis, src, key) => ({ level, text, basis, src: src || null, key: key || null });

rule('hr', ['heart'], M => {
  if (!num(M['hr.rest'])) return null;
  const fi = evalHeartRate({ bpm: M['hr.rest'], source: 'manual', context: 'rest' });
  return r(fi.severity, fi.text, 'convention', null, 'hr.rest');
});
rule('orthostatic', ['heart', 'artery', 'vein'], M => {
  if (typeof M['orthostatic.presyncope'] !== 'boolean') return null;
  return M['orthostatic.presyncope']
    ? r(2, 'Dizziness on standing reported. Orthostatic intolerance is the primary in-mission cardiovascular risk: sit or lie down, drink fluids and tell the flight surgeon.', 'verified', 'cvRisk', 'orthostatic.presyncope')
    : r(0, 'No dizziness on standing reported.', 'verified', 'cvRisk', 'orthostatic.presyncope');
});
rule('jugular', ['vein'], M => {
  const v = M['jugular.flow']; if (!v) return null;
  if (v === 'thrombus') return r(3, 'Clot seen in the jugular vein. One occlusive clot needed treatment in flight: contact the flight surgeon now.', 'verified', 'cvVte', 'jugular.flow');
  if (v === 'stagnant' || v === 'reversed') return r(1, `Jugular flow is ${v}. This was seen in 6 of 11 crew members tested; re-check by ultrasound and watch for neck swelling or pain.`, 'verified', 'cvVte', 'jugular.flow');
  return r(0, 'Jugular flow normal.', 'verified', 'cvVte', 'jugular.flow');
});

const BMD = {
  'bmd.hipPct':       { rate: 1.5, label: 'Hip', src: 'boneSibonga15', groups: ['pelvis', 'femur'] },
  'bmd.lumbarPct':    { rate: 1.0, label: 'Lumbar spine', src: 'boneSibonga15', groups: ['spineL'] },
  'bmd.wholeBodyPct': { rate: 0.3, label: 'Whole-body', src: 'boneSibonga15', groups: SKELETON_GROUPS }
};
for (const [key, d] of Object.entries(BMD)) {
  rule('bmd:' + key, d.groups, M => {
    const v = M[key]; if (!num(v)) return null;
    const loss = -v, m = M['mission.month'];
    if (loss <= 0) return r(0, `${d.label} bone density change ${v} %: no loss.`, 'reference', d.src, key);
    if (!num(m) || m <= 0) return r(0, `${d.label} bone density ${v} %. Enter the mission month to compare with NASA's reference rate.`, 'reference', d.src, key);
    const expected = m * d.rate, ratio = loss / expected;
    const base = `${d.label} bone density ${v} % after ${m} months; NASA mean rate gives about −${expected.toFixed(1)} %.`;
    return ratio <= 1 ? r(0, base + ' Within the mean.', 'reference', d.src, key)
         : ratio <= 2 ? r(1, base + ' Faster than the mean: review exercise, vitamin D and energy intake.', 'reference', d.src, key)
         : r(2, base + ' More than twice the mean: contact the flight surgeon.', 'reference', d.src, key);
  });
}
rule('backpain', ['spineC', 'spineT', 'spineL', 'mChest', 'mAbdomen'], M => {
  const v = M['back.pain']; if (!num(v)) return null;
  return v >= 7 ? r(2, `Back pain ${v}/10. Moderate to severe pain affects 14–28 % of US astronauts in flight; report it.`, 'convention', 'spine', 'back.pain')
       : v >= 4 ? r(1, `Back pain ${v}/10. Over half of astronauts report spine pain; try the fetal-tuck stretch and log it.`, 'convention', 'spine', 'back.pain')
       : r(0, `Back pain ${v}/10.`, 'convention', 'spine', 'back.pain');
});
rule('strength', MUSCLE_GROUPS.filter(g => g !== 'tendon'), M => {
  const v = M['strength.changePct']; if (!num(v)) return null;
  return v <= -20 ? r(2, `Strength ${v} % vs. preflight: in the group (12–38 % of crew) that loses more than 20 %. Review resistive exercise.`, 'reference', 'fitnessRisk', 'strength.changePct')
       : v <= -10 ? r(1, `Strength ${v} % vs. preflight: around the 10–12 % ISS average loss. Keep resistive training on schedule.`, 'reference', 'fitnessRisk', 'strength.changePct')
       : r(0, `Strength ${v} % vs. preflight: better than the ISS average loss.`, 'reference', 'fitnessRisk', 'strength.changePct');
});
rule('aerobic', ['heart', 'lung'], M => {
  const v = M['aerobic.changePct']; if (!num(v)) return null;
  return v <= -20 ? r(2, `Aerobic fitness ${v} % vs. preflight: beyond the 20 % loss that 12–38 % of crew reach.`, 'reference', 'fitnessRisk', 'aerobic.changePct')
       : v <= -10 ? r(1, `Aerobic fitness ${v} % vs. preflight: around the 10–12 % ISS average loss.`, 'reference', 'fitnessRisk', 'aerobic.changePct')
       : r(0, `Aerobic fitness ${v} % vs. preflight.`, 'reference', 'fitnessRisk', 'aerobic.changePct');
});
rule('sans', ['eye'], M => {
  const out = []; let lvl = 0;
  if (M['sans.discEdema'] === true) { lvl = 2; out.push('optic disc swelling'); }
  if (M['sans.choroidalFolds'] === true) { lvl = 2; out.push('choroidal folds'); }
  const h = M['sans.hyperopicShiftD'];
  if (num(h) && h >= 0.5) { lvl = Math.max(lvl, 1); out.push(`hyperopic shift +${h} D`); }
  const any = num(h) || typeof M['sans.discEdema'] === 'boolean' || typeof M['sans.choroidalFolds'] === 'boolean';
  if (!any) return null;
  return lvl ? r(lvl, `SANS signs: ${out.join(', ')}. Documented range of the shift is +0.50 to +1.75 D; image with OCT and tell the flight surgeon.`, lvl >= 2 ? 'convention' : 'verified', 'sans', 'sans.discEdema')
             : r(0, 'No SANS signs in the data entered.', 'verified', 'sans', 'sans.discEdema');
});
rule('sleep', ['brain', 'body'], M => {
  const v = M['sleep.hours']; if (!num(v)) return null;
  return v < 5 ? r(2, `Sleep ${v} h per night. Sleep loss in flight is linked to impaired performance.`, 'convention', 'sleepER', 'sleep.hours')
       : v < 6 ? r(1, `Sleep ${v} h per night. Sleep loss in flight is linked to impaired performance.`, 'convention', 'sleepER', 'sleep.hours')
       : r(0, `Sleep ${v} h per night.`, 'convention', 'sleepER', 'sleep.hours');
});
rule('pvt', ['brain'], M => {
  const n = M['pvt.lapses']; if (!num(n)) return null;
  return n >= 20 ? r(M['pvt.confirmed'] ? 3 : 2, `${n} lapses at 355 ms or slower. This level separated low from medium performance in a ground task; repeat the test to confirm.`, 'verified', 'pvtB', 'pvt.lapses')
       : n >= 11 ? r(2, `${n} lapses at 355 ms or slower. This level separated medium from high performance in a ground task.`, 'verified', 'pvtB', 'pvt.lapses')
       : r(0, `${n} lapses at 355 ms or slower.`, 'verified', 'pvtB', 'pvt.lapses');
});
rule('hemoglobin', ['spleen'], M => {
  const v = M['hemoglobin.gdl']; if (!num(v)) return null;
  const thr = M.sex === 'm' ? 13 : 12;
  const note = ' Red-cell destruction rises by 54 % in flight; the effect shows most after landing.';
  return v < 8 ? r(3, `Hemoglobin ${v} g/dL: severe anemia by WHO cut-off. Contact the flight surgeon now.`, 'convention', 'rbc', 'hemoglobin.gdl')
       : v < thr ? r(2, `Hemoglobin ${v} g/dL is below ${thr} g/dL (WHO anemia cut-off).${note}`, 'convention', 'rbc', 'hemoglobin.gdl')
       : r(0, `Hemoglobin ${v} g/dL.${note}`, 'convention', 'rbc', 'hemoglobin.gdl');
});
rule('urine', ['kidney'], M => {
  const v = M['urine.volumeL'], ca = M['urine.calciumMgDay'];
  if (!num(v) && !num(ca)) return null;
  const caHigh = num(ca) && ca > (M.sex === 'm' ? 300 : 250);
  let lvl = 0; const t = [];
  if (num(v)) { if (v < 1) { lvl = 2; t.push(`urine volume ${v} L/day is very low`); } else if (v < 2) { lvl = 1; t.push(`urine volume ${v} L/day is low`); } }
  if (caHigh) { lvl = Math.max(lvl, 1); t.push(`urinary calcium ${ca} mg/day is high`); }
  return lvl ? r(lvl, `Stone risk: ${t.join('; ')}. NASA recommends more fluid for all crew; potassium citrate is the studied countermeasure.`, 'convention', 'renalE057', 'urine.volumeL')
             : r(0, 'Urine volume and calcium in the usual range.', 'convention', 'renalE057', 'urine.volumeL');
});
rule('radiation', ['body'], M => {
  const c = M['radiation.careerMsv'], e = M['radiation.eventMsv'];
  if (!num(c) && !num(e)) return null;
  if ((num(c) && c >= 600) || (num(e) && e >= 250)) return r(3, `Radiation limit reached (career 600 mSv, single solar particle event 250 mSv). Shelter and contact ground.`, 'verified', 'radLimit', 'radiation.careerMsv');
  if (num(c) && c >= 480) return r(1, `Career dose ${c} mSv is above 80 % of the 600 mSv limit (80 % is a convention).`, 'convention', 'radLimit', 'radiation.careerMsv');
  return r(0, `Career dose ${num(c) ? c : '–'} mSv of the 600 mSv limit.`, 'verified', 'radLimit', 'radiation.careerMsv');
});
rule('immune', ['body'], M => {
  const s = M['virus.shedding'], z = M['zoster.symptoms'];
  if (typeof s !== 'boolean' && typeof z !== 'boolean') return null;
  if (z === true) return r(2, 'Shingles-like symptoms reported. Latent virus reactivation is documented in flight; tell the flight surgeon.', 'verified', 'herpes', 'zoster.symptoms');
  if (s === true) return r(1, 'Latent virus shedding detected. It is common in flight and usually without symptoms; watch for skin lesions.', 'verified', 'herpes', 'virus.shedding');
  return r(0, 'No virus shedding or shingles-like symptoms reported.', 'verified', 'herpes', 'virus.shedding');
});

rule('bp', ['heart', 'artery'], M => {
  const a = M['bp.sys'], b = M['bp.dia']; if (!num(a) && !num(b)) return null;
  const t = `${num(a) ? a : '–'}/${num(b) ? b : '–'} mmHg`;
  if ((num(a) && a >= 180) || (num(b) && b >= 120)) return r(3, `Blood pressure ${t} is in the hypertensive-crisis range. Contact the flight surgeon now.`, 'convention', 'cvRisk', 'bp.sys');
  if ((num(a) && a >= 160) || (num(b) && b >= 100)) return r(2, `Blood pressure ${t} is clearly high. Re-measure after rest and tell the flight surgeon.`, 'convention', 'cvRisk', 'bp.sys');
  if ((num(a) && a >= 140) || (num(b) && b >= 90)) return r(1, `Blood pressure ${t} is above 140/90. Re-measure after rest.`, 'convention', 'cvRisk', 'bp.sys');
  if (num(a) && a < 90) return r(M['orthostatic.presyncope'] ? 2 : 1, `Systolic pressure ${a} mmHg is low. Orthostatic intolerance is the main cardiovascular risk in flight; drink fluids and sit or lie down if dizzy.`, 'convention', 'cvRisk', 'bp.sys');
  return r(0, `Blood pressure ${t}.`, 'convention', 'cvRisk', 'bp.sys');
});
rule('spo2', ['lung'], M => {
  const v = M['spo2.pct']; if (!num(v)) return null;
  return v < 88 ? r(3, `Blood oxygen ${v} %: dangerously low. Check the cabin air and contact the flight surgeon now.`, 'convention', null, 'spo2.pct')
       : v < 92 ? r(2, `Blood oxygen ${v} % is low. Re-measure and check the cabin air.`, 'convention', null, 'spo2.pct')
       : v < 95 ? r(1, `Blood oxygen ${v} % is slightly low. Re-measure.`, 'convention', null, 'spo2.pct')
       : r(0, `Blood oxygen ${v} %.`, 'convention', null, 'spo2.pct');
});
rule('resp', ['lung', 'airway'], M => {
  const v = M['resp.rate']; if (!num(v)) return null;
  if ((ACTIVE(M.activity) || M.recovering) && v >= 12 && v <= 45) return r(0, `Breathing rate ${v}/min during ${M.activity === 'eva' ? 'a spacewalk' : 'exercise'} (only resting values are rated).`, 'convention', null, 'resp.rate');
  return v < 8 || v > 30 ? r(3, `Breathing rate ${v}/min is extreme. Contact the flight surgeon now.`, 'convention', null, 'resp.rate')
       : v < 10 || v > 24 ? r(2, `Breathing rate ${v}/min is clearly outside the usual 12–20 range.`, 'convention', null, 'resp.rate')
       : v < 12 || v > 20 ? r(1, `Breathing rate ${v}/min is slightly outside the usual 12–20 range.`, 'convention', null, 'resp.rate')
       : r(0, `Breathing rate ${v}/min.`, 'convention', null, 'resp.rate');
});
rule('temp', ['body'], M => {
  const v = M['temp.c']; if (!num(v)) return null;
  return v >= 39.5 || v < 34 ? r(3, `Body temperature ${v} °C is dangerous. Contact the flight surgeon now.`, 'convention', null, 'temp.c')
       : v >= 38.5 || v < 35 ? r(2, `Body temperature ${v} °C. Fever or chill: isolate from the crew and tell the flight surgeon.`, 'convention', null, 'temp.c')
       : v >= 37.8 ? r(1, `Body temperature ${v} °C is slightly raised. Re-measure.`, 'convention', null, 'temp.c')
       : r(0, `Body temperature ${v} °C.`, 'convention', null, 'temp.c');
});
rule('glucose', ['body', 'liver'], M => {
  const v = M['glucose.mgdl']; if (!num(v)) return null;
  return v < 54 || v >= 250 ? r(3, `Blood glucose ${v} mg/dL is dangerous. Contact the flight surgeon now.`, 'convention', null, 'glucose.mgdl')
       : v < 70 || v >= 126 ? r(2, `Blood glucose ${v} mg/dL is outside the usual range (fasting 70–99).`, 'convention', null, 'glucose.mgdl')
       : v >= 100 ? r(1, `Blood glucose ${v} mg/dL is slightly raised if fasting (usual 70–99).`, 'convention', null, 'glucose.mgdl')
       : r(0, `Blood glucose ${v} mg/dL.`, 'convention', null, 'glucose.mgdl');
});
rule('mass', ['body', 'stomach', 'intestine'], M => {
  const v = M['mass.changePct']; if (!num(v)) return null;
  const n = ' Low energy intake also costs bone and muscle.';
  return v <= -10 ? r(2, `Body mass ${v} % vs. preflight.${n}`, 'convention', 'nutrition', 'mass.changePct')
       : v <= -5 ? r(1, `Body mass ${v} % vs. preflight.${n}`, 'convention', 'nutrition', 'mass.changePct')
       : r(0, `Body mass ${v} % vs. preflight.`, 'convention', 'nutrition', 'mass.changePct');
});
rule('vitd', ['body'], M => {
  const v = M['vitd.ngml']; if (!num(v)) return null;
  return v < 12 ? r(2, `Vitamin D ${v} ng/mL is deficient. It supports bone health and must be supplemented without sunlight.`, 'convention', 'nutBone', 'vitd.ngml')
       : v < 20 ? r(1, `Vitamin D ${v} ng/mL is below 20. It supports bone health and must be supplemented without sunlight.`, 'convention', 'nutBone', 'vitd.ngml')
       : r(0, `Vitamin D ${v} ng/mL.`, 'convention', 'nutBone', 'vitd.ngml');
});

/* ---------- Rules for the wearable, blood, urine and imaging values added in v3.8 ----------
   Unless a source is named, the cut-offs are general clinical reference ranges (basis 'convention'), not NASA limits. */
const ACTIVE = a => a === 'exercise' || a === 'eva';
rule('hrnow', ['heart'], M => {
  const v = M['hr.now']; if (!num(v)) return null;
  if (ACTIVE(M.activity)) return r(0, `Heart rate ${v} bpm during ${M.activity === 'eva' ? 'a spacewalk' : 'exercise'} (only resting values are rated).`, 'convention', null, 'hr.now');
  if (M.recovering) return r(0, `Heart rate ${v} bpm while recovering from exercise (only resting values are rated).`, 'convention', null, 'hr.now');
  const fi = evalHeartRate({ bpm: v, source: 'device', context: 'rest' });
  return r(fi.severity, `Heart rate now ${v} bpm${M.activity === 'sleep' ? ' while asleep' : ''}.`, 'convention', null, 'hr.now');
});
rule('sleepEff', ['brain'], M => {
  const v = M['sleep.efficiencyPct']; if (!num(v)) return null;
  return v < 75 ? r(2, `Sleep efficiency ${v} %: a quarter or more of the time in bed was spent awake.`, 'convention', 'stdMeasures', 'sleep.efficiencyPct')
       : v < 85 ? r(1, `Sleep efficiency ${v} % is below the usual 85 %.`, 'convention', 'stdMeasures', 'sleep.efficiencyPct')
       : r(0, `Sleep efficiency ${v} %.`, 'convention', 'stdMeasures', 'sleep.efficiencyPct');
});
rule('motion', ['brain', 'stomach'], M => {
  const v = M['motion.sickness']; if (!num(v)) return null;
  return v >= 7 ? r(2, `Motion sickness ${v}/10. Avoid fast head movements, keep fluids up and tell the flight surgeon.`, 'convention', 'artemis2', 'motion.sickness')
       : v >= 4 ? r(1, `Motion sickness ${v}/10. Common in the first days of flight and after landing.`, 'convention', 'artemis2', 'motion.sickness')
       : r(0, `Motion sickness ${v}/10.`, 'convention', 'artemis2', 'motion.sickness');
});
rule('trt', ['eye'], M => {
  const v = M['sans.trtChangeUm']; if (!num(v)) return null;
  return v >= 55 ? r(2, `Retina around the optic disc is ${v} µm thicker than preflight: at or above the 55 µm level an expert consensus calls clinically concerning.`, 'verified', 'sansConsensus', 'sans.trtChangeUm')
       : v >= 20 ? r(1, `Retina around the optic disc is ${v} µm thicker than preflight: 20 µm is the earliest sign of optic disc swelling in an expert consensus.`, 'verified', 'sansConsensus', 'sans.trtChangeUm')
       : r(0, `Retinal thickness change ${v} µm, below the 20 µm early-sign level.`, 'verified', 'sansConsensus', 'sans.trtChangeUm');
});
/** Two-sided reference range: [low, high] is usual; beyond [farLow, farHigh] is rated one level higher. */
function band(id, groups, key, name, unit, range, far, farLevel = 2, basis = 'convention', src = null) {
  rule(id, groups, M => {
    const v = M[key]; if (!num(v)) return null;
    const [lo, hi] = typeof range === 'function' ? range(M) : range, [flo, fhi] = far ? (typeof far === 'function' ? far(M) : far) : [-Infinity, Infinity];
    const t = `${name} ${v}${unit ? ' ' + unit : ''}`;
    if (v < flo || v > fhi) return r(farLevel, `${t} is far outside the usual ${lo} to ${hi}. ${farLevel >= 3 ? 'Contact the flight surgeon now.' : 'Repeat the test and tell the flight surgeon.'}`, basis, src, key);
    if (v < lo || v > hi) return r(1, `${t} is ${v < lo ? 'below' : 'above'} the usual ${lo} to ${hi}.`, basis, src, key);
    return r(0, `${t}.`, basis, src, key);
  });
}
band('wbc', ['spleen'], 'wbc.k', 'White blood cells', 'k/µL', [4, 11], [2, 20]);
band('platelets', ['spleen'], 'platelets.k', 'Platelets', 'k/µL', [150, 450], [50, 1000]);
band('hematocrit', ['spleen'], 'hematocrit.pct', 'Hematocrit', '%', M => (M.sex === 'm' ? [41, 53] : [36, 46]), M => (M.sex === 'm' ? [30, 60] : [27, 55]));
band('ferritin', ['spleen'], 'ferritin.ngml', 'Ferritin', 'ng/mL', M => (M.sex === 'm' ? [30, 400] : [15, 150]), null);
band('sodium', ['kidney'], 'sodium.mmol', 'Sodium', 'mmol/L', [135, 145], [130, 150]);
band('potassium', ['kidney', 'heart'], 'potassium.mmol', 'Potassium', 'mmol/L', [3.5, 5], [3, 6], 3);
band('creatinine', ['kidney'], 'creatinine.mgdl', 'Creatinine', 'mg/dL', M => (M.sex === 'm' ? [0.7, 1.3] : [0.6, 1.1]), [0.3, 2]);
band('calcium', ['body'], 'calcium.mgdl', 'Serum calcium', 'mg/dL', [8.6, 10.2], [7.5, 12]);
band('crp', ['body'], 'crp.mgl', 'C-reactive protein', 'mg/L', [0, 10], [0, 50]);
// Catalogue entries with a usual range (panels.mjs) → one two-sided range rule each
for (const x of CATALOG) if (x.ref && x.ref !== 'custom')
  band('cat:' + x.key, x.groups, x.key, x.label, x.unit, M => refRange(x, M), x.far ? M => farRange(x, M) : null, 2, x.basis, x.tsrc || null);
// Sleep quality, adults: National Sleep Foundation consensus (Ohayon et al. 2017)
const nsf = (key, fn) => rule('nsf:' + key, ['brain'], M => { const v = M[key]; return num(v) ? fn(v) : null; });
nsf('sleep.latencyMin', v => v <= 30 ? r(0, `Fell asleep in ${v} min: 30 min or less counts as good sleep quality.`, 'verified', 'nsf', 'sleep.latencyMin')
  : r(1, `Fell asleep in ${v} min: ${v >= 45 ? '45 min or more indicates poor sleep quality' : 'above the 30 min of good sleep quality'}.`, 'verified', 'nsf', 'sleep.latencyMin'));
nsf('sleep.wasoMin', v => v <= 20 ? r(0, `Awake ${v} min after falling asleep: 20 min or less counts as good.`, 'verified', 'nsf', 'sleep.wasoMin')
  : r(1, `Awake ${v} min after falling asleep: ${v >= 41 ? '41 min or more indicates poor sleep quality' : 'above the 20 min of good sleep quality'}.`, 'verified', 'nsf', 'sleep.wasoMin'));
nsf('sleep.awakenings', v => v <= 1 ? r(0, `${v} awakening${v === 1 ? '' : 's'} longer than 5 min: one or fewer counts as good.`, 'verified', 'nsf', 'sleep.awakenings')
  : r(1, `${v} awakenings longer than 5 min: ${v >= 4 ? '4 or more indicate poor sleep quality' : 'more than the one of good sleep quality'}.`, 'verified', 'nsf', 'sleep.awakenings'));
nsf('sleep.n1Pct', v => v <= 10 ? r(0, `Light stage N1 ${v} % of sleep${v > 5 ? ' (good quality is 5 % or less)' : ''}.`, 'verified', 'nsf', 'sleep.n1Pct')
  : r(1, `Light stage N1 is ${v} % of sleep: well above the 5 % or less of good sleep quality, a sign of fragmented sleep.`, 'verified', 'nsf', 'sleep.n1Pct'));
nsf('sleep.n3Pct', v => v >= 16 ? r(0, `Deep sleep N3 ${v} % of sleep (good quality in adults: 16 to 20 %).`, 'verified', 'nsf', 'sleep.n3Pct')
  : r(1, `Deep sleep N3 is only ${v} % of sleep: below the 16 to 20 % of good sleep quality in adults. On Shuttle flights slow-wave sleep fell late in the night.`, 'verified', 'nsf', 'sleep.n3Pct'));
nsf('sleep.remPct', v => v >= 21 ? r(0, `REM sleep ${v} % of sleep (good quality in adults: 21 to 30 %).${v > 30 ? ' Above 30 % the consensus is uncertain.' : ''}`, 'verified', 'nsf', 'sleep.remPct')
  : r(1, `REM sleep is only ${v} % of sleep: below the 21 to 30 % of good sleep quality in adults.`, 'verified', 'nsf', 'sleep.remPct'));
rule('stoneRisk', ['kidney'], M => {
  const c = M['urine.citrateMgDay'], ph = M['urine.ph'], st = M['kidney.stone'];
  if (!num(c) && !num(ph) && typeof st !== 'boolean') return null;
  if (st === true) return r(2, 'A kidney stone was seen on ultrasound. A stone could impair a crew member in flight: increase fluids and tell the flight surgeon.', 'verified', 'renalKcit', 'kidney.stone');
  const t = [];
  if (num(c) && c < 320) t.push(`urinary citrate ${c} mg/day is low (below 320)`);
  if (num(ph) && ph < 5.5) t.push(`urine pH ${ph} is acidic (below 5.5)`);
  return t.length ? r(1, `Stone risk: ${t.join('; ')}. Citrate and pH fall in flight; potassium citrate is the studied countermeasure.`, 'convention', 'renalE057', num(c) && c < 320 ? 'urine.citrateMgDay' : 'urine.ph')
                  : r(0, 'Urinary citrate, pH and ultrasound without a stone-risk finding.', 'convention', 'renalE057', 'urine.citrateMgDay');
});

/* ---------- Evaluation ---------- */
/** M = measurement object (keys of INDICATORS plus 'mission.month', 'sex', 'pvt.confirmed', 'activity', 'recovering').
    ext = optional findings from the decision engine ({hr, pvt, bone}), used only where M has no value. */
export function evaluate(M = {}, ext = {}) {
  const out = {};
  for (const id of GROUP_IDS) {
    const def = PARTS[id];
    const results = [];
    for (const ru of RULES) if (ru.groups.includes(id)) { const x = ru.fn(M); if (x) results.push({ rule: ru.id, ...x }); }
    const E = (finding, key, basis) => { if (finding) results.push({ rule: 'engine:' + finding.id, level: finding.severity, text: finding.text, basis, src: null, key }); };
    if (id === 'heart' && !num(M['hr.rest'])) E(ext.hr, 'hr.rest', 'convention');
    if (id === 'brain' && !num(M['pvt.lapses'])) E(ext.pvt, 'pvt.lapses', 'verified');
    if (def.system === 'skeleton' && ext.bone) E(ext.bone, 'bmd.wholeBodyPct', 'model');
    const level = results.length ? Math.max(...results.map(x => x.level)) : LEVEL.nodata;
    out[id] = {
      id, label: def.label, system: def.system, level, status: level < 0 ? 'nodata' : LEVEL_NAME[level], statusLabel: LEVEL_LABEL[level],
      warnings: results.filter(x => x.level >= 1).sort((a, b) => b.level - a.level),
      notes: results.filter(x => x.level === 0),
      indicators: def.ind.map(k => ({ key: k, ...INDICATORS[k], why: WHY[k] || '', value: M[k] === undefined ? null : M[k] }))
    };
  }
  return out;
}

/** Worst status per anatomy group for colouring the body. */
export function bodyColors(state) {
  const c = {};
  for (const id of GROUP_IDS) if (id !== 'body' && state[id].level >= 1) c[id] = state[id].status;
  return c;
}

export function summarize(state) {
  const counts = { nodata: 0, ok: 0, watch: 0, warn: 0, alert: 0 };
  const attention = [];
  for (const id of GROUP_IDS) { const s = state[id]; counts[s.status]++; if (s.level >= 1) attention.push({ id, label: s.label, level: s.level, text: s.warnings[0].text }); }
  attention.sort((a, b) => b.level - a.level);
  return { counts, attention };
}

/** Sample crew data for the demo. Clearly invented; the UI labels it "Sample data". */
export const SAMPLE = Object.freeze({
  'mission.month': 4, sex: 'f',
  'hr.rest': 71, 'orthostatic.presyncope': false, 'jugular.flow': 'stagnant',
  'bmd.hipPct': -9.5, 'bmd.lumbarPct': -9.0, 'bmd.wholeBodyPct': -0.9,
  'back.pain': 5, 'strength.changePct': -14, 'aerobic.changePct': -8,
  'sans.hyperopicShiftD': 0.75, 'sans.discEdema': false, 'sans.choroidalFolds': false,
  'sleep.hours': 5.6, 'pvt.lapses': 9,
  'hemoglobin.gdl': 11.6, 'urine.volumeL': 1.7, 'urine.calciumMgDay': 210,
  'radiation.careerMsv': 145, 'radiation.eventMsv': 0,
  'virus.shedding': true, 'zoster.symptoms': false, 'pvt.meanRtMs': 268,
  'bp.sys': 126, 'bp.dia': 79, 'spo2.pct': 97, 'resp.rate': 15, 'temp.c': 36.7, 'glucose.mgdl': 92, 'mass.changePct': -4, 'vitd.ngml': 18
});

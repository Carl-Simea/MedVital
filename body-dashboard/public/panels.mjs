/* panels.mjs — the detailed measurement catalogue of MEDvital (lab panels, exams, sleep stages, exercise and nutrition detail).
   Pure data, no DOM. parts.mjs merges these entries into INDICATORS and builds one rule per rated entry;
   testdata.mjs takes the demo values; intake.mjs reads the labels.

   What each field means
     ref    usual range [low, high], or {m:[..], f:[..]} by biological sex; null = shown and tracked, not rated
            (no verified threshold, or only meaningful against the person's own preflight baseline)
     far    beyond this the finding is one level higher ("Elevated"); null = only "Watch"
     basis  'convention' for general adult clinical reference ranges (labs differ slightly; not NASA limits),
            'verified' where the cut-off itself comes from the cited source (sleep quality: NSF consensus)
     tsrc   source of the cut-off (only with basis 'verified'); msrc = source that NASA measures this at all
     demo   test-data values for the scenarios [nominal, mixed, critical] (invented, see testdata.mjs)
     plaus  plausible range for the report reader (values outside are rejected as typos)

   Sources for WHAT is measured (all checked on 15 Nov 2026 unless marked otherwise):
     mer    NASA Medical Examination Requirements: annual CBC, biochemistry (liver, kidney, thyroid, glucose, HbA1c, lipids,
            hs-CRP, Ca/Mg/phosphate, iron studies), urinalysis, DXA + bone markers every 3 years, eye exam incl. IOP and imaging, 12-lead ECG
     ocular NASA ocular health: IOP, OCT (RNFL, choroid), optic nerve sheath diameter by ultrasound, visual acuity, Amsler grid,
            contrast sensitivity, visual fields, cycloplegic refraction. It gives NO normal value for the sheath diameter.
     nsf    National Sleep Foundation sleep quality consensus (Ohayon et al., Sleep Health 2017)
     dijk   Dijk et al. 2001: polysomnography on two Shuttle flights (less slow-wave sleep late in the night, REM rebound after landing)
     params NASA Standard Measures parameter list (from the earlier research round, not re-read today) */

export const PANEL_SRC = Object.freeze({
  mer:    { kind: 'primary', title: 'NASA: Medical Examination Requirements (annual CBC, biochemistry, urinalysis, DXA every 3 years, eye exam, ECG)', url: 'https://www.nasa.gov/hhp/medical-examination-requirements' },
  ocular: { kind: 'primary', title: 'NASA JSC: Ocular health measures (IOP, OCT, optic nerve sheath ultrasound, acuity, Amsler grid, contrast, visual fields)', url: 'https://ntrs.nasa.gov/api/citations/20170000780/downloads/20170000780.pdf' },
  params: { kind: 'primary', title: 'NASA: Spaceflight Standard Measures parameter list', url: 'https://ntrs.nasa.gov/api/citations/20200001281/downloads/20200001281.pdf' },
  fluid:  { kind: 'primary', title: 'NASA Fluid Shifts study: body water, plasma volume, tissue thickness, vessel dimensions', url: 'https://ntrs.nasa.gov/citations/20150021479' },
  cardioOx:{ kind: 'primary', title: 'NASA Cardio Ox: arterial stiffness, carotid and brachial ultrasound, oxidative stress markers', url: 'https://www.nasa.gov/sites/default/files/files/Experiments_Summary_One-Pager_Cardio-ox.pdf' },
  nutStat:{ kind: 'primary', title: 'NASA JSC: Nutritional status assessment in spaceflight (vitamins, iron, oxidative damage markers)', url: 'https://ntrs.nasa.gov/citations/20040112382' },
  nsf:    { kind: 'primary', title: 'Ohayon et al., Sleep Health 2017: National Sleep Foundation sleep quality recommendations', url: 'https://doi.org/10.1016/j.sleh.2016.11.006' },
  dijk:   { kind: 'primary', title: 'Dijk et al. 2001: sleep and circadian rhythms on two Space Shuttle flights (polysomnography)', url: 'https://ntrs.nasa.gov/citations/20040088714' },
  amdr:   { kind: 'secondary', title: 'US Dietary Reference Intakes (general population, not spaceflight-specific)', url: 'https://www.ncbi.nlm.nih.gov/books/NBK545442/' }
});

export const PANELS = Object.freeze([
  ['sleepArch', 'Sleep architecture'], ['blood', 'Blood count'], ['chem', 'Chemistry and electrolytes'], ['liver', 'Liver'],
  ['lipid', 'Lipids and glucose'], ['iron', 'Iron status'], ['endo', 'Thyroid and hormones'], ['boneMk', 'Bone markers'],
  ['immune', 'Immune system'], ['vit', 'Vitamins and oxidative stress'], ['urine', 'Urine, 24 hours'], ['stone', 'Stone-forming salts'],
  ['cardio', 'Heart and vessels'], ['lungF', 'Lung function'], ['fluidP', 'Fluid distribution'], ['eyeP', 'Eyes'],
  ['musc', 'Bone and muscle imaging'], ['sensori', 'Balance and motor control'], ['cog', 'Cognition, 10 tests'], ['behav', 'Behaviour, team and environment'],
  ['exDev', 'Exercise devices'], ['exTest', 'Exercise tests'], ['nutMacro', 'Energy and macronutrients'], ['nutMicro', 'Micronutrient intake']
].map(([id, label]) => ({ id, label })));

/* e(key, label, unit, panel, groups, ref, far, demo, plaus, extra) */
const e = (key, label, unit, panel, groups, ref, far, demo, plaus, x = {}) =>
  ({ key, label, unit, panel, groups, ref, far, demo, plaus, basis: 'convention', how: '', flight: true, ...x });
const LAB = { how: 'Blood test', msrc: 'mer' }, CBC = { how: 'Complete blood count', msrc: 'mer' }, U24 = { how: '24-hour urine collection', msrc: 'params' };
const BASE = { how: 'Compared with own preflight baseline' };

export const CATALOG = Object.freeze([
  // ---- Sleep architecture (one night). Stages need EEG (polysomnography or EEG headband); wrist devices only estimate them.
  e('sleep.inBedH', 'Time in bed', 'h', 'sleepArch', ['brain'], null, null, [8.5, 7.1, 6.2], [0, 16], { how: 'Wearable or sleep log' }),
  e('sleep.latencyMin', 'Sleep latency', 'min', 'sleepArch', ['brain'], 'custom', null, [12, 34, 70], [0, 240], { how: 'EEG or wearable', basis: 'verified', tsrc: 'nsf' }),
  e('sleep.wasoMin', 'Wake after sleep onset', 'min', 'sleepArch', ['brain'], 'custom', null, [14, 31, 58], [0, 480], { how: 'EEG or wearable', basis: 'verified', tsrc: 'nsf' }),
  e('sleep.awakenings', 'Awakenings longer than 5 min', '', 'sleepArch', ['brain'], 'custom', null, [1, 3, 5], [0, 40], { how: 'EEG or wearable', basis: 'verified', tsrc: 'nsf' }),
  e('sleep.n1Pct', 'Stage N1 share', '%', 'sleepArch', ['brain'], 'custom', null, [5, 9, 16], [0, 100], { how: 'EEG sleep staging', basis: 'verified', tsrc: 'nsf' }),
  e('sleep.n2Pct', 'Stage N2 share', '%', 'sleepArch', ['brain'], null, null, [52, 56, 60], [0, 100], { how: 'EEG sleep staging', msrc: 'nsf' }),
  e('sleep.n3Pct', 'Deep sleep N3 share', '%', 'sleepArch', ['brain'], 'custom', null, [19, 15, 9], [0, 100], { how: 'EEG sleep staging', basis: 'verified', tsrc: 'nsf' }),
  e('sleep.remPct', 'REM sleep share', '%', 'sleepArch', ['brain'], 'custom', null, [24, 20, 15], [0, 100], { how: 'EEG sleep staging', basis: 'verified', tsrc: 'nsf' }),
  e('sleep.remLatencyMin', 'REM latency', 'min', 'sleepArch', ['brain'], null, null, [88, 72, 54], [0, 400], { how: 'EEG sleep staging', msrc: 'dijk' }),
  e('sleep.cycles', 'Sleep cycles', '', 'sleepArch', ['brain'], null, null, [5, 4, 3], [0, 10], { how: 'EEG sleep staging' }),
  e('sleep.onsetClock', 'Sleep onset clock time', 'h', 'sleepArch', ['brain'], null, null, [22.5, 23.4, 0.6], [0, 24], { how: 'Wearable, hours after midnight GMT (ISS time)' }),
  e('sleep.lightLux', 'Light before bedtime', 'lux', 'sleepArch', ['brain'], null, null, [40, 160, 320], [0, 100000], { how: 'Light sensor of the wrist actigraph', msrc: 'params' }),

  // ---- Blood count (MER1001)
  e('rbc.M', 'Red blood cells', 'M/µL', 'blood', ['spleen'], { m: [4.5, 5.9], f: [4.1, 5.1] }, { m: [3.0, 7.0], f: [2.8, 6.5] }, [5.0, 3.9, 4.3], [1, 9], CBC),
  e('retic.pct', 'Reticulocytes', '%', 'blood', ['spleen'], [0.5, 2.5], [0.1, 5], [1.1, 0.6, 0.3], [0, 20], CBC),
  e('neut.k', 'Neutrophils', 'k/µL', 'blood', ['spleen'], [1.8, 7.7], [0.5, 15], [3.6, 2.6, 11.2], [0, 60], CBC),
  e('lymph.k', 'Lymphocytes', 'k/µL', 'blood', ['spleen'], [1.0, 4.8], [0.5, 8], [2.0, 1.2, 0.7], [0, 50], CBC),
  e('mono.k', 'Monocytes', 'k/µL', 'blood', ['spleen'], [0.2, 1.0], null, [0.5, 0.5, 1.1], [0, 10], CBC),
  e('eos.k', 'Eosinophils', 'k/µL', 'blood', ['spleen'], [0, 0.5], null, [0.15, 0.3, 0.1], [0, 10], CBC),
  e('baso.k', 'Basophils', 'k/µL', 'blood', ['spleen'], [0, 0.2], null, [0.04, 0.05, 0.06], [0, 5], CBC),
  e('mcv.fl', 'Mean cell volume', 'fL', 'blood', ['spleen'], [80, 100], [70, 115], [89, 84, 95], [50, 140], CBC),
  e('mpv.fl', 'Mean platelet volume', 'fL', 'blood', ['spleen'], [7.5, 11.5], null, [9.4, 10.1, 12.2], [4, 20], CBC),
  e('pdw.pct', 'Platelet distribution width', '%', 'blood', ['spleen'], null, null, [12, 13, 16], [5, 30], CBC),

  // ---- Chemistry and electrolytes (MER1002)
  e('co2.mmol', 'Bicarbonate', 'mmol/L', 'chem', ['kidney', 'lung'], [22, 29], [15, 35], [25, 23, 19], [5, 50], LAB),
  e('chloride.mmol', 'Chloride', 'mmol/L', 'chem', ['kidney'], [98, 107], [90, 115], [102, 104, 111], [70, 140], LAB),
  e('bun.mgdl', 'Urea nitrogen', 'mg/dL', 'chem', ['kidney'], [7, 20], [3, 40], [14, 19, 34], [1, 200], LAB),
  e('uricacid.mgdl', 'Uric acid', 'mg/dL', 'chem', ['kidney'], { m: [3.4, 7.0], f: [2.4, 6.0] }, [1, 11], [5.2, 5.6, 8.4], [0.5, 20], LAB),
  e('magnesium.mgdl', 'Magnesium', 'mg/dL', 'chem', ['heart', 'kidney'], [1.7, 2.2], [1.2, 3], [2.0, 1.8, 1.5], [0.5, 6], LAB),
  e('phosphate.mgdl', 'Phosphate', 'mg/dL', 'chem', ['kidney'], [2.5, 4.5], [1.5, 6.5], [3.5, 4.1, 4.9], [0.5, 12], LAB),
  e('ica.mmol', 'Ionized calcium', 'mmol/L', 'chem', ['body'], [1.12, 1.32], [0.9, 1.5], [1.22, 1.26, 1.34], [0.5, 2.5], LAB),
  e('protein.gdl', 'Total protein', 'g/dL', 'chem', ['liver'], [6.3, 7.9], [5, 9.5], [7.1, 6.6, 6.0], [3, 12], LAB),
  e('albumin.gdl', 'Albumin', 'g/dL', 'chem', ['liver'], [3.5, 5.0], [2.5, 6], [4.4, 3.9, 3.2], [1, 7], LAB),

  // ---- Liver
  e('alt.ul', 'ALT', 'U/L', 'liver', ['liver'], [7, 55], [0, 200], [24, 41, 88], [1, 3000], LAB),
  e('ast.ul', 'AST', 'U/L', 'liver', ['liver'], [8, 48], [0, 200], [22, 36, 74], [1, 3000], LAB),
  e('alp.ul', 'Alkaline phosphatase', 'U/L', 'liver', ['liver', 'pelvis'], [40, 129], [20, 300], [72, 95, 148], [5, 2000], LAB),
  e('ggt.ul', 'GGT', 'U/L', 'liver', ['liver'], { m: [8, 61], f: [5, 36] }, [0, 200], [22, 30, 70], [1, 2000], LAB),
  e('bili.mgdl', 'Total bilirubin', 'mg/dL', 'liver', ['liver'], [0.1, 1.2], [0, 3], [0.6, 0.9, 1.6], [0, 30], LAB),
  e('ldh.ul', 'Lactate dehydrogenase', 'U/L', 'liver', ['liver', 'spleen'], [122, 222], [80, 500], [160, 205, 290], [20, 5000], LAB),

  // ---- Lipids and glucose
  e('chol.mgdl', 'Total cholesterol', 'mg/dL', 'lipid', ['artery'], [100, 200], [60, 240], [172, 196, 248], [40, 600], LAB),
  e('ldl.mgdl', 'LDL cholesterol', 'mg/dL', 'lipid', ['artery'], [40, 130], [20, 190], [98, 134, 172], [10, 400], LAB),
  e('hdl.mgdl', 'HDL cholesterol', 'mg/dL', 'lipid', ['artery'], { m: [40, 100], f: [50, 110] }, [25, 130], [56, 54, 34], [5, 200], LAB),
  e('nonhdl.mgdl', 'Non-HDL cholesterol', 'mg/dL', 'lipid', ['artery'], [60, 160], [30, 220], [116, 142, 214], [10, 500], LAB),
  e('trig.mgdl', 'Triglycerides', 'mg/dL', 'lipid', ['artery', 'liver'], [30, 150], [20, 500], [92, 148, 260], [10, 3000], LAB),
  e('hba1c.pct', 'HbA1c', '%', 'lipid', ['liver'], [4, 5.6], [3, 6.5], [5.2, 5.5, 6.1], [2, 18], LAB),

  // ---- Iron status (iron stores rise in flight; NASA tracks iron studies)
  e('iron.ugdl', 'Serum iron', 'µg/dL', 'iron', ['spleen'], [60, 170], [30, 250], [105, 142, 190], [5, 500], LAB),
  e('tibc.ugdl', 'Total iron binding capacity', 'µg/dL', 'iron', ['spleen'], [250, 450], [150, 600], [320, 300, 240], [50, 900], LAB),
  e('tsat.pct', 'Transferrin saturation', '%', 'iron', ['spleen'], [20, 50], [10, 70], [33, 47, 79], [1, 100], LAB),
  e('transferrin.mgdl', 'Transferrin', 'mg/dL', 'iron', ['spleen'], [200, 360], [100, 500], [270, 250, 205], [20, 800], LAB),
  e('stfr.mgl', 'Soluble transferrin receptor', 'mg/L', 'iron', ['spleen'], null, null, [1.4, 1.2, 0.9], [0, 20], { ...LAB, msrc: 'nutStat' }),

  // ---- Thyroid and hormones
  e('tsh.miul', 'TSH', 'mIU/L', 'endo', ['body'], [0.4, 4.0], [0.1, 10], [1.8, 2.9, 4.6], [0, 100], LAB),
  e('ft4.ngdl', 'Free T4', 'ng/dL', 'endo', ['body'], [0.8, 1.8], [0.4, 3], [1.2, 1.1, 0.9], [0.1, 8], LAB),
  e('testosterone.ngdl', 'Testosterone', 'ng/dL', 'endo', ['body'], null, null, [520, 34, 310], [1, 3000], { ...LAB, msrc: 'nutStat' }),
  e('igf1.ngml', 'IGF-1', 'ng/mL', 'endo', ['body'], null, null, [180, 160, 120], [10, 1500], { ...LAB, msrc: 'params' }),
  e('leptin.ngml', 'Leptin', 'ng/mL', 'endo', ['body'], null, null, [6, 12, 3], [0, 200], { ...LAB, msrc: 'params' }),

  // ---- Bone markers (no in-flight thresholds; trend against preflight)
  e('pth.pgml', 'Intact parathyroid hormone', 'pg/mL', 'boneMk', ['pelvis', 'spineL'], [15, 65], [5, 150], [38, 52, 13], [1, 2000], LAB),
  e('bsap.ugl', 'Bone-specific alkaline phosphatase', 'µg/L', 'boneMk', ['pelvis', 'spineL'], null, null, [13, 15, 11], [1, 200], { ...LAB, msrc: 'params' }),
  e('p1np.ugl', 'P1NP bone formation marker', 'µg/L', 'boneMk', ['pelvis', 'spineL'], null, null, [52, 48, 38], [1, 500], { ...LAB, msrc: 'params' }),
  e('osteocalcin.ngml', 'Osteocalcin', 'ng/mL', 'boneMk', ['pelvis', 'spineL'], null, null, [21, 18, 14], [1, 200], { ...LAB, msrc: 'params' }),
  e('ucoc.ngml', 'Undercarboxylated osteocalcin', 'ng/mL', 'boneMk', ['pelvis', 'spineL'], null, null, [4.1, 4.8, 6.2], [0, 50], { ...LAB, msrc: 'params' }),
  e('vitd125.pgml', '1,25-dihydroxyvitamin D', 'pg/mL', 'boneMk', ['pelvis', 'kidney'], null, null, [42, 36, 22], [1, 300], { ...LAB, msrc: 'params' }),
  e('sclerostin.pmol', 'Sclerostin', 'pmol/L', 'boneMk', ['pelvis'], null, null, [28, 33, 41], [1, 300], { ...LAB, msrc: 'params' }),
  e('opg.pmol', 'Osteoprotegerin', 'pmol/L', 'boneMk', ['pelvis'], null, null, [4.2, 4.6, 5.3], [0, 50], { ...LAB, msrc: 'params' }),
  e('rankl.pmol', 'RANKL', 'pmol/L', 'boneMk', ['pelvis'], null, null, [0.21, 0.26, 0.38], [0, 20], { ...LAB, msrc: 'params' }),
  e('ntx.nmolbce', 'Urinary NTX bone resorption', 'nmol BCE/mmol', 'boneMk', ['pelvis', 'spineL'], null, null, [38, 56, 84], [1, 1000], { how: 'Urine sample', msrc: 'params' }),

  // ---- Immune system
  e('il6.pgml', 'Interleukin-6', 'pg/mL', 'immune', ['spleen', 'body'], [0, 7], [0, 40], [1.8, 4.2, 22], [0, 1000], { ...LAB, msrc: 'params' }),
  e('tnf.pgml', 'TNF-alpha', 'pg/mL', 'immune', ['spleen'], null, null, [6, 8, 14], [0, 500], { ...LAB, msrc: 'params' }),
  e('tcell.pct', 'T-cell function vs. baseline', '%', 'immune', ['spleen'], null, null, [98, 86, 61], [0, 300], { how: 'Stimulated cytokine profile, compared with preflight', msrc: 'params' }),
  e('ige.kul', 'Total IgE, allergy profile', 'kU/L', 'immune', ['spleen', 'airway'], [0, 100], [0, 400], [40, 88, 160], [0, 5000], { ...LAB, msrc: 'params' }),

  // ---- Vitamins and oxidative stress
  e('folate.ngml', 'Serum folate', 'ng/mL', 'vit', ['body'], [4, 20], [2, 40], [11, 7, 3.4], [0.5, 60], { ...LAB, msrc: 'nutStat' }),
  e('b12.pgml', 'Vitamin B12', 'pg/mL', 'vit', ['body'], [200, 900], [100, 2000], [480, 310, 190], [20, 5000], { ...LAB, msrc: 'nutStat' }),
  e('vite.mgl', 'Vitamin E alpha-tocopherol', 'mg/L', 'vit', ['body'], [5.5, 17], [3, 30], [11, 9, 5.1], [0.5, 60], { ...LAB, msrc: 'nutStat' }),
  e('vitk.ngml', 'Vitamin K1', 'ng/mL', 'vit', ['body'], null, null, [0.9, 0.6, 0.3], [0, 20], { ...LAB, msrc: 'nutStat' }),
  e('homocysteine.umol', 'Homocysteine', 'µmol/L', 'vit', ['artery'], [5, 15], [2, 30], [8, 11, 17], [1, 200], { ...LAB, msrc: 'nutStat' }),
  e('ohdg.ngmg', '8-OHdG oxidative DNA damage', 'ng/mg creatinine', 'vit', ['body'], null, null, [4.1, 5.6, 8.9], [0, 100], { how: 'Urine sample', msrc: 'nutStat' }),
  e('pgf2a.ngmg', 'Prostaglandin F2-alpha', 'ng/mg creatinine', 'vit', ['body'], null, null, [0.8, 1.1, 1.9], [0, 50], { how: 'Urine sample', msrc: 'cardioOx' }),

  // ---- Urine, 24 hours
  e('urine.sodiumMmol', 'Urinary sodium', 'mmol/day', 'urine', ['kidney'], [40, 220], [10, 350], [150, 196, 260], [1, 800], U24),
  e('urine.potassiumMmol', 'Urinary potassium', 'mmol/day', 'urine', ['kidney'], [25, 125], [10, 200], [70, 55, 38], [1, 500], U24),
  e('urine.creatG', 'Urinary creatinine', 'g/day', 'urine', ['kidney'], null, null, [1.6, 1.1, 1.3], [0.1, 5], U24),
  e('urine.magnesiumMg', 'Urinary magnesium', 'mg/day', 'urine', ['kidney'], null, null, [110, 92, 70], [1, 600], U24),
  e('urine.phosphorusMg', 'Urinary phosphorus', 'mg/day', 'urine', ['kidney'], null, null, [820, 900, 1100], [10, 4000], U24),
  e('urine.uricMg', 'Urinary uric acid', 'mg/day', 'urine', ['kidney'], null, null, [560, 610, 790], [10, 3000], U24),
  e('urine.oxalateMg', 'Urinary oxalate', 'mg/day', 'urine', ['kidney'], [10, 40], [0, 80], [28, 38, 52], [0, 300], U24),
  e('urine.sulfateMmol', 'Urinary sulfate', 'mmol/day', 'urine', ['kidney'], null, null, [18, 22, 28], [0, 200], U24),

  // ---- Stone-forming salts: relative supersaturation (from the 24 h urine; trend only here)
  e('ss.caox', 'Supersaturation calcium oxalate', '', 'stone', ['kidney'], null, null, [1.4, 2.1, 3.6], [0, 50], U24),
  e('ss.cap', 'Supersaturation brushite', '', 'stone', ['kidney'], null, null, [0.8, 1.2, 1.9], [0, 50], U24),
  e('ss.naurate', 'Supersaturation sodium urate', '', 'stone', ['kidney'], null, null, [1.2, 1.6, 2.4], [0, 50], U24),
  e('ss.struvite', 'Supersaturation struvite', '', 'stone', ['kidney'], null, null, [0.4, 0.5, 0.6], [0, 50], U24),
  e('ss.uric', 'Supersaturation uric acid', '', 'stone', ['kidney'], null, null, [0.9, 1.6, 2.8], [0, 50], U24),

  // ---- Heart and vessels
  e('sv.ml', 'Stroke volume', 'mL', 'cardio', ['heart'], null, null, [78, 84, 58], [10, 250], { how: 'Heart ultrasound', msrc: 'params' }),
  e('co.lmin', 'Cardiac output', 'L/min', 'cardio', ['heart'], [4, 8], [2.5, 12], [5.4, 5.9, 3.6], [0.5, 30], { how: 'Heart ultrasound or finger cuff', msrc: 'params' }),
  e('ivc.mm', 'Inferior vena cava diameter', 'mm', 'cardio', ['vein'], null, null, [18, 15, 11], [1, 40], { how: 'Ultrasound', msrc: 'params' }),
  e('pwv.ms', 'Pulse wave velocity', 'm/s', 'cardio', ['artery'], [4, 10], [3, 13], [6.8, 8.4, 10.9], [1, 30], { how: 'Arterial stiffness measurement', msrc: 'cardioOx' }),
  e('fmd.pct', 'Flow-mediated dilation', '%', 'cardio', ['artery'], null, null, [7.2, 5.9, 3.1], [-10, 40], { how: 'Brachial artery ultrasound', msrc: 'cardioOx' }),
  e('qtc.ms', 'QTc interval', 'ms', 'cardio', ['heart'], { m: [350, 450], f: [350, 460] }, [300, 500], [405, 438, 482], [200, 700], { how: 'Resting 12-lead ECG', msrc: 'mer' }),
  e('abp.meanSys', '24-h mean systolic pressure', 'mmHg', 'cardio', ['artery'], [90, 130], [80, 150], [116, 132, 104], [50, 250], { how: '24-hour ambulatory blood pressure', msrc: 'params' }),

  // ---- Lung function
  e('fev1.pctPred', 'FEV1', '% predicted', 'lungF', ['lung', 'airway'], [80, 130], [50, 200], [98, 88, 76], [10, 200], { how: 'Spirometry', msrc: 'params' }),
  e('fvc.pctPred', 'FVC', '% predicted', 'lungF', ['lung'], [80, 130], [50, 200], [101, 91, 79], [10, 200], { how: 'Spirometry', msrc: 'params' }),
  e('fev1fvc.pct', 'FEV1/FVC ratio', '%', 'lungF', ['airway'], [70, 95], [50, 100], [81, 78, 74], [20, 100], { how: 'Spirometry', msrc: 'params' }),
  e('dlco.pctPred', 'Diffusing capacity DLCO', '% predicted', 'lungF', ['lung'], [75, 140], [50, 200], [96, 84, 71], [10, 200], { how: 'Gas transfer test', msrc: 'params' }),

  // ---- Fluid distribution (Fluid Shifts study)
  e('plasmaVol.changePct', 'Plasma volume change', '%', 'fluidP', ['vein', 'body'], null, null, [-8, -12, -17], [-60, 40], { how: 'Carbon monoxide rebreathing, vs. preflight', msrc: 'fluid' }),
  e('tbw.L', 'Total body water', 'L', 'fluidP', ['body'], null, null, [46, 31, 44], [10, 90], { how: 'Deuterium dilution', msrc: 'fluid' }),
  e('ecf.L', 'Extracellular fluid', 'L', 'fluidP', ['body'], null, null, [18, 13, 16], [3, 40], { how: 'Bromide dilution', msrc: 'fluid' }),
  e('tissue.foreheadMm', 'Forehead tissue thickness', 'mm', 'fluidP', ['skull'], null, null, [5.6, 6.1, 6.8], [1, 20], { how: 'Ultrasound', msrc: 'fluid' }),
  e('tissue.tibiaMm', 'Shin tissue thickness', 'mm', 'fluidP', ['shin'], null, null, [4.2, 3.7, 3.3], [1, 20], { how: 'Ultrasound', msrc: 'fluid' }),

  // ---- Eyes (ocular health measures)
  e('va.logmar', 'Visual acuity logMAR', '', 'eyeP', ['eye'], [-0.3, 0.1], [-0.5, 0.3], [0, 0.1, 0.4], [-0.5, 2], { how: 'Eye chart, near and far', msrc: 'ocular' }),
  e('iop.mmhg', 'Intraocular pressure', 'mmHg', 'eyeP', ['eye'], [10, 21], [6, 30], [15, 17, 22], [1, 60], { how: 'Tonometry', msrc: 'ocular' }),
  e('onsd.mm', 'Optic nerve sheath diameter', 'mm', 'eyeP', ['eye'], null, null, [5.1, 5.7, 6.6], [2, 10], { how: 'Ultrasound; NASA gives no normal value, so only the trend counts', msrc: 'ocular' }),
  e('choroid.um', 'Choroid thickness change', 'µm', 'eyeP', ['eye'], null, null, [8, 21, 46], [-200, 400], { how: 'OCT, compared with preflight', msrc: 'ocular' }),
  e('rnfl.um', 'Retinal nerve fibre layer change', 'µm', 'eyeP', ['eye'], null, null, [1, 4, 11], [-100, 200], { how: 'OCT, compared with preflight', msrc: 'ocular' }),
  e('contrast.logcs', 'Contrast sensitivity', 'log CS', 'eyeP', ['eye'], null, null, [1.95, 1.8, 1.55], [0, 3], { how: 'Contrast chart', msrc: 'ocular' }),
  e('vf.md', 'Visual field mean defect', 'dB', 'eyeP', ['eye'], null, null, [-0.4, -1.1, -3.2], [-35, 5], { how: 'Threshold perimetry', msrc: 'ocular' }),

  // ---- Bone and muscle imaging
  e('bmd.femNeckPct', 'Femoral neck BMD change', '%', 'musc', ['femur', 'pelvis'], [-5, 10], [-10, 20], [-2.8, -6.4, -12.1], [-40, 20], { how: 'DXA, before and after flight (every 3 years in the annual exams)', msrc: 'mer', flight: false }),
  e('muscle.volCalfPct', 'Calf muscle volume change', '%', 'musc', ['mShin'], [-4, 10], [-10, 20], [-3, -7, -14], [-50, 30], { how: 'MRI, compared with preflight', msrc: 'params', flight: false }),
  e('muscle.volThighPct', 'Thigh muscle volume change', '%', 'musc', ['mThigh'], [-4, 10], [-10, 20], [-2, -5, -11], [-50, 30], { how: 'MRI, compared with preflight', msrc: 'params', flight: false }),
  e('bone.tibiaStrengthPct', 'Tibia strength change, HR-pQCT', '%', 'musc', ['shin'], null, null, [-1, -3, -6], [-50, 30], { how: 'High-resolution CT, before and after flight', msrc: 'params', flight: false }),

  // ---- Balance and motor control (field test)
  e('sts.sec', 'Sit-to-stand, time to stable stance', 's', 'sensori', ['brain', 'mThigh'], null, null, [2.1, 3.4, 6.8], [0, 120], { how: 'Field test: seated to standing, then 10 s still', msrc: 'params' }),
  e('tandem.pct', 'Tandem walk eyes closed, correct steps', '%', 'sensori', ['brain'], null, null, [92, 70, 38], [0, 100], { how: 'Field test', msrc: 'params' }),
  e('prone.sec', 'Prone-to-stand time', 's', 'sensori', ['brain'], null, null, [3.2, 4.6, 9.8], [0, 300], { how: 'Field test: from lying face down to standing, then 3 min still', msrc: 'params' }),
  e('finemotor.pct', 'Fine motor test vs. baseline', '%', 'sensori', ['brain', 'mForearm'], null, null, [99, 92, 81], [0, 200], { how: 'Tablet: tracking, pointing, tracing, pinch-rotate', msrc: 'params' }),

  // ---- Cognition: 10 tests of the NASA battery, each vs. own baseline
  e('cog.mpt', 'Motor praxis', '% of baseline', 'cog', ['brain'], null, null, [101, 97, 88], [0, 200], { ...BASE, msrc: 'params' }),
  e('cog.volt', 'Visual object learning', '% of baseline', 'cog', ['brain'], null, null, [99, 92, 76], [0, 200], { ...BASE, msrc: 'params' }),
  e('cog.f2b', 'Fractal 2-back working memory', '% of baseline', 'cog', ['brain'], null, null, [102, 90, 71], [0, 200], { ...BASE, msrc: 'params' }),
  e('cog.am', 'Abstract matching', '% of baseline', 'cog', ['brain'], null, null, [98, 95, 84], [0, 200], { ...BASE, msrc: 'params' }),
  e('cog.lot', 'Line orientation', '% of baseline', 'cog', ['brain'], null, null, [100, 96, 85], [0, 200], { ...BASE, msrc: 'params' }),
  e('cog.ert', 'Emotion recognition', '% of baseline', 'cog', ['brain'], null, null, [100, 94, 80], [0, 200], { ...BASE, msrc: 'params' }),
  e('cog.mrt', 'Matrix reasoning', '% of baseline', 'cog', ['brain'], null, null, [101, 93, 79], [0, 200], { ...BASE, msrc: 'params' }),
  e('cog.dsst', 'Digit symbol substitution', '% of baseline', 'cog', ['brain'], null, null, [103, 91, 74], [0, 200], { ...BASE, msrc: 'params' }),
  e('cog.bart', 'Balloon analog risk', '% of baseline', 'cog', ['brain'], null, null, [100, 108, 126], [0, 300], { ...BASE, msrc: 'params' }),
  e('cog.pvt', 'Psychomotor vigilance', '% of baseline', 'cog', ['brain'], null, null, [99, 86, 63], [0, 200], { ...BASE, msrc: 'params' }),

  // ---- Behaviour, team and environment (monthly questionnaire, actigraphy)
  e('team.cohesion', 'Team cohesion', '/7', 'behav', ['brain'], null, null, [6, 5, 3], [1, 7], { how: 'Monthly questionnaire', msrc: 'params' }),
  e('team.performance', 'Team performance', '/7', 'behav', ['brain'], null, null, [6, 5, 3], [1, 7], { how: 'Monthly questionnaire', msrc: 'params' }),
  e('habitability', 'Habitability rating', '/7', 'behav', ['body'], null, null, [6, 4, 3], [1, 7], { how: 'Monthly questionnaire', msrc: 'params' }),
  e('workload.score', 'Workload', '/10', 'behav', ['brain'], null, null, [5, 7, 9], [0, 10], { how: 'Self-report' }),
  e('activity.countsK', 'Daytime activity counts', 'k/day', 'behav', ['body'], null, null, [310, 240, 160], [0, 5000], { how: 'Wrist actigraphy', msrc: 'params' }),
  e('dose.missionMsv', 'Mission dose, crew dosimeter', 'mSv', 'behav', ['body'], null, null, [24, 61, 118], [0, 2000], { how: 'Personal active dosimeter' }),

  // ---- Exercise devices (minutes this week) and tests
  e('ex.aredMin', 'Resistive device ARED', 'min/wk', 'exDev', ['mThigh'], null, null, [270, 190, 90], [0, 1500], { how: 'Exercise log' }),
  e('ex.cevisMin', 'Cycle ergometer CEVIS', 'min/wk', 'exDev', ['heart'], null, null, [180, 150, 90], [0, 1500], { how: 'Exercise log' }),
  e('ex.t2Min', 'Treadmill T2', 'min/wk', 'exDev', ['mShin'], null, null, [160, 130, 60], [0, 1500], { how: 'Exercise log' }),
  e('ex.squatKg', 'ARED squat load', 'kg', 'exTest', ['mThigh'], null, null, [120, 82, 64], [0, 400], { how: 'Exercise log' }),
  e('ex.vo2peak', 'Absolute VO2peak', 'mL/kg/min', 'exTest', ['heart', 'lung'], null, null, [44, 33, 30], [5, 90], { how: 'Cycle ergometer test', msrc: 'params' }),
  e('ex.wattPeak', 'Peak power, cycle test', 'W', 'exTest', ['mThigh'], null, null, [310, 190, 210], [20, 800], { how: 'Cycle ergometer test', msrc: 'params' }),
  e('ex.hrPeak', 'Exercise peak heart rate', 'bpm', 'exTest', ['heart'], null, null, [178, 171, 158], [60, 230], { how: 'Cycle ergometer test', msrc: 'params' }),
  e('ex.rpe', 'Perceived exertion Borg', '/20', 'exTest', ['body'], null, null, [15, 17, 19], [6, 20], { how: 'Borg scale at the end of the test', msrc: 'params' }),
  e('ex.z2Min', 'Time in moderate heart rate zone', 'min/wk', 'exTest', ['heart'], null, null, [190, 150, 70], [0, 2000], { how: 'Wearable during exercise' }),
  e('ex.z4Min', 'Time in hard heart rate zone', 'min/wk', 'exTest', ['heart'], null, null, [75, 40, 12], [0, 2000], { how: 'Wearable during exercise' }),

  // ---- Energy and macronutrients (food log). Ranges: US acceptable macronutrient ranges, general population.
  e('nut.kcal', 'Energy intake per day', 'kcal', 'nutMacro', ['stomach'], null, null, [2850, 1700, 1750], [0, 8000], { how: 'Food log', msrc: 'nutStat' }),
  e('nut.carbPct', 'Carbohydrate share of energy', '%', 'nutMacro', ['intestine'], [45, 65], [30, 80], [52, 50, 61], [0, 100], { how: 'Food log', basis: 'verified', tsrc: 'amdr' }),
  e('nut.fatPct', 'Fat share of energy', '%', 'nutMacro', ['liver'], [20, 35], [10, 45], [31, 34, 28], [0, 100], { how: 'Food log', basis: 'verified', tsrc: 'amdr' }),
  e('nut.proteinPct', 'Protein share of energy', '%', 'nutMacro', ['mThigh'], [10, 35], [5, 45], [17, 16, 11], [0, 100], { how: 'Food log', basis: 'verified', tsrc: 'amdr' }),
  e('nut.fiberG', 'Fibre', 'g/day', 'nutMacro', ['intestine'], [25, 70], [10, 100], [31, 26, 14], [0, 150], { how: 'Food log' }),
  e('nut.omega3G', 'Omega-3 fatty acids', 'g/day', 'nutMacro', ['brain'], null, null, [1.6, 0.9, 0.4], [0, 20], { how: 'Food log' }),

  // ---- Micronutrient intake (food log), general Dietary Reference Intakes
  e('nut.sodiumMg', 'Sodium intake', 'mg/day', 'nutMicro', ['kidney'], [1500, 2300], [500, 4500], [2200, 3100, 4800], [0, 15000], { how: 'Food log' }),
  e('nut.potassiumMg', 'Potassium intake', 'mg/day', 'nutMicro', ['heart'], { m: [3400, 6000], f: [2600, 6000] }, [1500, 9000], [3700, 2400, 1900], [0, 15000], { how: 'Food log' }),
  e('nut.calciumMg', 'Calcium intake', 'mg/day', 'nutMicro', ['pelvis'], [1000, 2500], [500, 3000], [1150, 820, 560], [0, 6000], { how: 'Food log' }),
  e('nut.vitdIU', 'Vitamin D intake', 'IU/day', 'nutMicro', ['pelvis'], [600, 4000], [200, 10000], [800, 600, 150], [0, 50000], { how: 'Food log and supplement' }),
  e('nut.ironMg', 'Iron intake', 'mg/day', 'nutMicro', ['spleen'], { m: [8, 45], f: [18, 45] }, [4, 60], [14, 16, 26], [0, 200], { how: 'Food log' }),
  e('nut.folateUg', 'Folate intake', 'µg/day', 'nutMicro', ['body'], [400, 1000], [150, 1500], [460, 330, 210], [0, 5000], { how: 'Food log' }),
  e('nut.vitkUg', 'Vitamin K intake', 'µg/day', 'nutMicro', ['body'], { m: [120, 1000], f: [90, 1000] }, [30, 5000], [135, 88, 60], [0, 5000], { how: 'Food log' }),
  e('nut.caffeineMg', 'Caffeine', 'mg/day', 'nutMicro', ['brain'], [0, 400], [0, 800], [180, 320, 520], [0, 3000], { how: 'Food log' })
]);

/** Entries keyed by indicator key. */
export const CATALOG_BY_KEY = Object.freeze(Object.fromEntries(CATALOG.map(x => [x.key, x])));
/** Usual range for one entry and one person (null when the entry is only tracked or uses its own rule). */
export function refRange(entry, M = {}) {
  const r = entry.ref; if (!r || r === 'custom') return null;
  return Array.isArray(r) ? r : (M.sex === 'f' ? r.f : r.m);
}
export function farRange(entry, M = {}) {
  const r = entry.far; if (!r) return null;
  return Array.isArray(r) ? r : (M.sex === 'f' ? r.f : r.m);
}

/* ---------- Hypnogram: one night as stages per 5-minute epoch ----------
   With real epoch data (M['sleep.hypnogram'] = 'WW1122333R2…', W/1/2/3/R per 5 min) the chart shows it as is.
   Without it the night is RECONSTRUCTED from the summary values (latency, stage shares, awakenings, cycles):
   deep sleep early in the night, REM growing towards morning, as in typical adult sleep. The UI labels it as reconstructed. */
export function hypnogram(M = {}) {
  if (typeof M['sleep.hypnogram'] === 'string' && /^[W123R]+$/.test(M['sleep.hypnogram'])) return { epochs: M['sleep.hypnogram'].split(''), real: true };
  const tib = M['sleep.inBedH'], slp = M['sleep.hours'];
  if (!(tib > 0) || !(slp > 0)) return null;
  const E = Math.max(12, Math.round(tib * 12)), lat = Math.round((M['sleep.latencyMin'] || 10) / 5);
  const waso = Math.round((M['sleep.wasoMin'] || 0) / 5), aw = Math.max(0, Math.round(M['sleep.awakenings'] || 0));
  const sleepE = Math.max(6, E - lat - waso - 1);
  const share = k => Math.max(0, M[k] || 0) / 100;
  let n1 = share('sleep.n1Pct'), n3 = share('sleep.n3Pct'), rem = share('sleep.remPct'); const n2 = Math.max(0, 1 - n1 - n3 - rem);
  const cycles = Math.max(2, Math.round(M['sleep.cycles'] || sleepE * 5 / 90));
  const per = sleepE / cycles, out = [];
  for (let i = 0; i < lat; i++) out.push('W');
  // N3 weight falls and REM weight rises over the night
  const w3 = [...Array(cycles)].map((_, c) => Math.max(0.05, 1 - c / (cycles - 0.5))), wR = [...Array(cycles)].map((_, c) => 0.4 + c / cycles);
  const s3 = w3.reduce((a, b) => a + b, 0), sR = wR.reduce((a, b) => a + b, 0);
  for (let c = 0; c < cycles; c++) {
    const len = Math.round(per), e3 = Math.round(n3 * sleepE * w3[c] / s3), eR = Math.round(rem * sleepE * wR[c] / sR), e1 = Math.max(1, Math.round(n1 * len));
    const e2 = Math.max(1, len - e3 - eR - e1), half = Math.ceil(e2 / 2);
    out.push(...Array(e1).fill('1'), ...Array(half).fill('2'), ...Array(e3).fill('3'), ...Array(e2 - half).fill('2'), ...Array(eR).fill('R'));
  }
  // awakenings spread over the second half of the night, sharing the wake time
  const each = aw ? Math.max(1, Math.round(waso / aw)) : 0;
  for (let a = 0; a < aw; a++) {
    const at = Math.round(lat + (0.35 + 0.6 * (a + 1) / (aw + 1)) * (out.length - lat));
    out.splice(Math.min(out.length, at), 0, ...Array(each).fill('W'));
  }
  while (out.length < E) out.push('W');
  return { epochs: out.slice(0, Math.max(E, out.length)), real: false, n2 };
}

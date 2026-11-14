/* knowledge.mjs — info cards per body system, verified statements only (sources in SOURCES).
   Pure data, no UI. Every statement points to a source; 'primary' = NASA / peer-reviewed publication,
   'secondary' = press release, review or summary. Gaps are listed in GAPS instead of invented text. */

export const SOURCES = Object.freeze({
  hrpHazards:   { kind: 'primary',   title: 'NASA HRP: Five hazards of human spaceflight', url: 'https://www.nasa.gov/hrp/hazards' },
  boneER2017:   { kind: 'primary',   title: 'NASA Evidence Report: Risk of Bone Fracture due to Spaceflight-induced Changes to Bone (2017)', url: 'https://ntrs.nasa.gov/api/citations/20170004597/downloads/20170004597.pdf' },
  boneSibonga15:{ kind: 'primary',   title: 'Sibonga (NASA HRP, 2015): Bone changes during spaceflight', url: 'https://ntrs.nasa.gov/api/citations/20150001885/downloads/20150001885.pdf' },
  boneSibonga13:{ kind: 'primary',   title: 'Sibonga (2013): Spaceflight-induced bone loss: is there an osteoporosis risk?', url: 'https://doi.org/10.1007/s11914-013-0136-5' },
  fitnessRisk:  { kind: 'primary',   title: 'NASA HRP: Risk of Reduced Cardiorespiratory and Musculoskeletal Fitness', url: 'https://www.nasa.gov/reference/risk-of-reduced-cardiorespiratory-and-musculoskeletal-fitness' },
  exerciseIss:  { kind: 'primary',   title: 'NASA: Astronaut exercise on the ISS', url: 'https://www.nasa.gov/missions/station/iss-research/astronaut-exercise/' },
  exerciseNews: { kind: 'secondary', title: 'NASA release (via Phys.org, 2024): Exercise and crew health', url: 'https://phys.org/news/2024-05-important-crew-health-space-missions.html' },
  cvRisk:       { kind: 'primary',   title: 'NASA: Risk of Cardiovascular Adaptations (CV Risk)', url: 'https://www.nasa.gov/directorates/esdmd/hhp/risk-of-cardiovascular-adaptations-contributing-to-adverse-mission-performance-and-health-outcomes/' },
  cvRiskPage:   { kind: 'primary',   title: 'NASA: Risk of Cardiovascular Adaptations (overview)', url: 'https://www.nasa.gov/reference/risk-of-cardiovascular-adaptations' },
  cvVte:        { kind: 'primary',   title: 'NASA: CV Risk, venous thromboembolism concern', url: 'https://www.nasa.gov/?p=222800' },
  sans:         { kind: 'primary',   title: 'Lee et al. 2020: SANS and the neuro-ophthalmologic effects of microgravity', url: 'https://pmc.ncbi.nlm.nih.gov/articles/PMC7005826' },
  sansCohort:   { kind: 'primary',   title: 'Prospective cohort of 11 astronauts: ocular structure changes on the ISS', url: 'https://pmc.ncbi.nlm.nih.gov/articles/PMC7118682' },
  sleepER:      { kind: 'primary',   title: 'NASA Evidence Report: Sleep Loss, Circadian Desynchronization, Work Overload (2016)', url: 'https://ntrs.nasa.gov/api/citations/20160003864/downloads/20160003864.pdf' },
  pvtB:         { kind: 'primary',   title: 'Basner, Mollicone, Dinges 2011: PVT-B', url: 'https://pmc.ncbi.nlm.nih.gov/articles/3197786' }
});

export const KNOWLEDGE = Object.freeze({
  skeleton: {
    title: 'Skeleton',
    facts: [
      { text: 'Bone mineral density falls on average by 1–1.5 % per month in weight-bearing skeletal sites.', source: 'boneER2017' },
      { text: 'Site-specific rates (DXA): hip about 1.5 %, lumbar spine about 1 %, whole body about 0.3 % per month.', source: 'boneSibonga15' },
      { text: 'The 1–1.5 % rate comes from pre- and postflight DXA scans, so bone loss is not measured in flight; MEDvital shows a model.', source: 'boneSibonga13' },
      { text: 'The ISS exercise devices are ARED (resistive), the T2 treadmill and the CEVIS cycle ergometer.', source: 'exerciseIss' },
      { text: 'Crew members now average about two hours of exercise per day.', source: 'exerciseNews' }
    ]
  },
  muscle: {
    title: 'Muscles',
    facts: [
      { text: 'ISS data show average losses of 10–12 % of pre-mission strength and aerobic fitness.', source: 'fitnessRisk' },
      { text: 'Between 12 % and 38 % of ISS crew members lose more than 20 % of pre-mission fitness, depending on how it is measured.', source: 'fitnessRisk' },
      { text: 'Strength loss affects a larger share of the crew than the decline in aerobic fitness.', source: 'fitnessRisk' }
    ]
  },
  cardio: {
    title: 'Heart & circulation',
    facts: [
      { text: 'Orthostatic intolerance is the primary in-mission cardiovascular risk, particularly in low Earth orbit and on the lunar surface.', source: 'cvRisk' },
      { text: 'Cardiovascular disease is a significant long-term health risk, especially for missions beyond low Earth orbit.', source: 'cvRisk' },
      { text: 'Exercise and a healthy diet help maintain cardiovascular fitness; compression garments and fluids before landing help prevent low blood pressure.', source: 'cvRiskPage' },
      { text: 'Stagnant or reverse flow in the internal jugular vein was seen in 6 of 11 crew members tested around flight day 50; one occlusive clot needed treatment in flight.', source: 'cvVte' }
    ]
  },
  brain: {
    title: 'Brain & eyes',
    facts: [
      { text: 'SANS (spaceflight associated neuro-ocular syndrome) covers optic disc edema, globe flattening, choroidal and retinal folds and hyperopic shifts.', source: 'sans' },
      { text: 'A reported symptom is reduced near vision (hyperopic shift of +0.50 to +1.75 D in six astronauts).', source: 'sans' },
      { text: 'A prospective ISS cohort of 11 astronauts showed optic disc edema and choroidal thickening during 6-month missions, measured by imaging.', source: 'sansCohort' },
      { text: 'Sleep loss is apparent during spaceflight, and ground evidence suggests it leads to performance impairment.', source: 'sleepER' },
      { text: 'The brief 3-minute PVT with a 355 ms lapse threshold is as sensitive to sleep loss as the 10-minute PVT.', source: 'pvtB' }
    ]
  }
});

/** Systems without a verified card. Research goes here, not guesses. */
export const GAPS = Object.freeze({
  lung: 'No verified fact collected yet (HRP evidence for lung and airway not read).',
  digest: 'No verified fact collected yet (HRP evidence for liver, kidney, digestion not read).'
});

export const HAZARDS = Object.freeze({
  list: ['Space radiation', 'Isolation and confinement', 'Distance from Earth', 'Gravity fields', 'Hostile/closed environments'],
  source: 'hrpHazards'
});

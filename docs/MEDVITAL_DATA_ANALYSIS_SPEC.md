# MEDVITAL data analysis specification

Audience: the implementation team. Scope: what to measure, in what units, how NASA collects it,
what real data exists, and which statistics are defensible. Written 2026-11-14.

> **Research prototype. Not a medical device.** This document defines no diagnosis and no clinical
> threshold. Where NASA itself uses thresholds, they are named only to say we do **not** encode them.

## 0. How to read this document

### 0.1 Evidence classes (as requested)

| Code | Class | Meaning |
| --- | --- | --- |
| **D** | Downloadable measured data | Raw or processed values a person can actually download |
| **P** | Published research findings | Results in a paper or report; numbers exist, raw data may not |
| **M** | Measurement protocols | How a quantity is collected or defined |
| **G** | Ground-analog or animal research | Bed rest, Antarctic/isolation analogs, rodents, etc. |
| **S** | Simulated data | MEDVITAL's own generator. Says nothing about real astronauts |

### 0.2 Verification levels (honest limits of this research)

| Level | Meaning |
| --- | --- |
| **Read** | I opened the document or page and read the text |
| **Snippet** | Seen only in a web-search summary; the source was not opened |
| **Known** | Standard textbook definition from general knowledge; **not checked against a source in this session**; verify before relying on it |

Several sources could not be opened: PubMed Central pages returned a bot check, one journal PDF
required a login, the Space Apps site had a certificate error, and Europe PMC returned errors. Those
sources are listed in section 9 as **not read**. Nothing in this document was invented to fill a
gap; gaps are stated as "not found" or "not stated".

### 0.3 Summary

| Domain | Real downloadable data found? | What we can do now |
| --- | --- | --- |
| Radiation | **Possibly** (ISS telemetry via OSDR RadLab and Environmental Data App; units and terms unread) | Verify RadLab, then import with the existing pipeline |
| Bone | **No.** Astronaut data is by request (LSAH); NASA reports are public | Simulate; implement the published change-from-baseline method |
| Cardiovascular | **No** open astronaut time series found | Simulate; implement standard HR/BP/HRV definitions |
| Behavioral | **No** open astronaut time series found | Simulate; implement sleep and reaction-time summaries |

OSDR does hold human data from the Inspiration4 mission (4 crew, 3 days), but those are omics and
clinical blood assays, mostly controlled-access, and do not map to our eight metrics (section 7).

## 1. Cross-cutting analysis design

### 1.1 Small N and repeated measures
Astronaut cohorts are tiny. The HRP bone report describes n = 92 long-duration astronauts at the
time of writing; analog studies in NASA's behavioral overview are described as small-n (Read).
Therefore:

- **Individual baseline first.** Compare each person with their own earlier values.
- Prefer **estimation with intervals** over p-values; report n beside every number.
- For group data use **linear mixed-effects models** for repeated measures
  (`y_ij = b0 + b1·t_ij + u_i + e_ij`, person random intercept `u_i`, optional random slope),
  not independent t-tests. (Known; the NASA papers read here used within/between-group
  comparisons at p < 0.05 for bone, Read.)
- Never pool across `origin` (simulated / measured / modeled) or across measurement `medium`/`site`.
- Declare multiple comparisons; correct (Holm or Benjamini-Hochberg) when many metrics are tested.

### 1.2 Core formulas (implemented in `core/stats.py` unless noted)

| Quantity | Formula | Notes |
| --- | --- | --- |
| Mean, sample SD | `x̄ = Σx/n`, `s = sqrt(Σ(x-x̄)²/(n-1))` | `n-1` (ddof=1) |
| Trend per day | OLS slope of `y` on time in days | Only when n >= 3 and times differ |
| Baseline z | `z_i = (x_i - mean(first k)) / sd(first k)` | Deviation from own early values; **not a normal range** |
| Percent change | `100·(x - x_base)/x_base` | Baseline > 0 |
| Cumulative from rate | `∫ rate dt ≈ Σ ½(r_i + r_{i+1})Δt` | Trapezoid rule |
| Outlier rank | IsolationForest score, fixed seed | Relative rank only |

### 1.3 Data-quality rules
Preserve timestamps in UTC; record uptime/missing data rather than imputing silently (the SRAG BEAM
report documents uptime gaps, Read); keep units exactly as stated and convert only by exact
definitions (`importers/units.py`).

## 2. Radiation health

### 2.1 Quantities and units

| Quantity | Symbol | Unit | Source / level |
| --- | --- | --- | --- |
| Absorbed dose | `D = E/m` | Gy (= J/kg); older: rad (100 rad = 1 Gy) | Benton 2012 (Read) |
| LET | `dE/dx` | keV/µm | Benton 2012 (Read) |
| Dose equivalent | `H = Q·D` | Sv | Benton 2012 (Read) |
| Absorbed dose in silicon | `D_Si` | mGy | BEAM report (Read) |
| Dose rate | `Ḋ` | µGy/day (passive RAM results); REM dose rate is recorded at a 1-minute cadence (its unit was not extracted) | BEAM report (Read) |

**Important:** SRAG reports dose *in silicon* (REM detectors) and *in water* in different places
(BEAM report, Read). These are different media and must never be averaged. **Schema gap:** add a
`medium` context key (`silicon`, `water`, `tissue_equivalent`) before importing real data.

### 2.2 Formulas (from Benton 2012, Read; symbols as in that review)

- `D [Gy] = 1.602×10⁻⁹ · Σ_i Φ_i · LET_i / ρ`, with `Φ` fluence (particles/cm²), `LET` in keV/µm,
  `ρ` density in g/cm³ (the constant converts keV to joules and units).
- `H = Σ Q(LET)·D(LET)`; mean quality factor `Q̄ = H/D`.
- `Q(LET) = 1` for `LET < 10`; `0.32·LET - 2.2` for `10 ≤ LET ≤ 100`; `300/√LET` for `LET > 100`
  (ICRP 1991 as reproduced by Benton; the PDF text extraction was imperfect, so **check the
  three branches against the original before coding**). This is a *definition of the weighting*, not a limit.
- Passive combination method (Benton): TLD gives total absorbed dose; CR-39 gives the LET spectrum
  above about 5 keV/µm; the remaining TLD dose is assumed to have `Q = 1`.
- Accumulated dose: `D_cum = Σ ½(Ḋ_i + Ḋ_{i+1})·Δt_i` (already `modules/radiation`).

### 2.3 How measurements are collected

| Method | Class | What it gives | Level |
| --- | --- | --- | --- |
| Passive detectors (TLD/OSLD, CR-39) | M | One cumulative value per deployment-to-return period; no time resolution | Read (Benton; BEAM) |
| Active REM detectors (silicon) | M | Dose rate, LET spectra, particle-specific dose at a **1-minute cadence** | Read (BEAM report) |
| TEPC (active, all LET) | M | LET spectra, time-resolved | Snippet |
| Crew passive dosimeter (CPD) | M | Per-crew dose of record | Snippet |

BEAM facts (Read): REM data about 20 MB/day/sensor, transferred roughly every 9 hours, then to ground;
analysis partitions data into South Atlantic Anomaly (SAA) versus upper-latitude (galactic cosmic ray)
components by ISS position. **Analysis implication:** stratify by SAA / non-SAA; do not average them.

### 2.4 Data availability

| Item | Class | Finding | Level |
| --- | --- | --- | --- |
| OSDR RadLab portal | **D (candidate)** | Overview page says users can query, visualise and download; export formats CSV, TSV, JSON, HTML; a Data API is linked. **Units, time coverage, registration and terms not stated** | Read (overview page only) |
| OSDR Environmental Data Application | **D (candidate)** | ISS cabin telemetry and radiation views for named experiments; raw and summary data downloadable from a Data Tables tab. Units and time span not stated | Read |
| BEAM final report (NASA/TP-20240011436) | P | Summary dose and dose-rate results, figures; raw data not published in the report | Read |
| Passive dosimetry review (Benton 2012) | M | Methods and definitions | Read |
| GeneLab dosimetry tables for experiments | D (candidate) | A search summary mentions downloadable dosimetry for STS experiments; ISS "being compiled" | Snippet |

### 2.5 Limitations and uncertainties
Passive detectors have no time resolution; TLD response drops for high-LET radiation and gives no LET
information (Benton, Read). Dose depends on shielding and location (BEAM report: rates differ by module and
placement, Read). BEAM data cover an empty module (Read). Shuttle-era passive values may be under-reported
by a few percent (Snippet). Detector uptime gaps exist (Read).

### 2.6 Analysis methods
Time series of dose rate with SAA/non-SAA stratification; cumulative dose by trapezoid integration with
documented gaps; between-location ratios (as the BEAM report does) with uncertainty; compare instruments
only within the same medium. **Do not** apply or encode exposure limits; NASA's LEO limits (NCRP Report 132,
mentioned in Benton, Read) are out of scope.

## 3. Bone health

### 3.1 Quantities and units

| Quantity | Unit | Collection | Level |
| --- | --- | --- | --- |
| Areal BMD (aBMD), hip and lumbar spine | g/cm² | DXA | Read (HRP report 2024) |
| Trabecular volumetric BMD (vBMD), hip | mg/cm³ (typical; unit **not stated** in what I read) | Hip QCT | Read (abstract); unit Known |
| Hip strength estimate | model output, units per method | Finite element model of QCT | Read (abstract) |
| Trabecular Bone Score (TBS) | unitless | From serial lumbar DXA | Read (Vasadi 2015) |
| Bone turnover markers (e.g. urinary NTX) | assay-specific | Urine/blood | Read (report figure titles) |

### 3.2 Formulas

- `%Δ = 100·(aBMD_post - aBMD_pre)/aBMD_pre` (NASA's "percentage change from preflight aBMD", Read).
- Monthly rate `≈ %Δ / months_in_flight` (arithmetic; the Mir study averaged 1-1.5 % per month, below).
- Precision error `RMS-SD = sqrt( mean_i( s_i² ) )` over repeated scans; **least significant change**
  `LSC = 2.77 · RMS-SD` at 95 % confidence (**Known**: ISCD convention; NASA's report shades the
  "% least significant change for DXA at JSC" in a figure, Read, but I did not extract its value).
  A change smaller than LSC is not distinguishable from measurement error.

### 3.3 Collection and frequency

| Item | Finding | Level |
| --- | --- | --- |
| Routine DXA | Preflight-to-postflight surveillance; **triennial** testing of active and retired astronauts (active since about 1997, retired about 2006) | Read |
| In-flight imaging | Hip QCT included in flight studies | Read (abstract) |
| Proposed surveillance | Hip QCT to monitor recovery of trabecular deficit by 2 years after return; FEM of hip strength; TBS from serial lumbar DXA | Read (Vasadi 2015) |
| Exact postflight scan timing, in-flight sampling frequency | **Not stated** in text I could read | n/a |

### 3.4 Published findings (P, with caveats)

- Mir cosmonauts, n = 18, missions of 4-14 months: average loss of preflight BMD about 1-1.5 % per month
  (LeBlanc 2000, as cited in the HRP report, Read). Hip and spine loss rates are described as faster than
  yearly terrestrial loss (Read).
- HRP report: ISS astronauts with ARED resistive exercise showed attenuated group-mean aBMD deficits; BMD
  loss rates shown for n = 11 astronauts as of summer 2012 (Read). Group-mean comparisons by exercise/drug
  arm at p < 0.05 (Read). Numerical values are in the report's figures; **not extracted here**.
- QCT-based comparison of hip trabecular loss in long-duration astronauts versus terrestrial cohorts, and
  increased hip and spine fracture incidence after longer flights from health-record analysis (2024 abstract, Read).
- Key caution from NASA itself (Read): **no clinical-trial data link a specific percentage change in aBMD
  to skeletal fragility**, and DXA aBMD is an insufficient sole surrogate for fracture risk.

### 3.5 Data availability

| Item | Class | Finding |
| --- | --- | --- |
| HRP bone evidence reports (2017, 2024) | P / M | Public (NTRS distribution "Public", Read) |
| Individual astronaut aBMD, QCT | **not found as downloadable** | The HRP report mentions the Lifetime Surveillance of Astronaut Health (LSAH) program (Read); a search summary describes a request-and-approval process (Snippet, unverified) |
| Open raw bone time series | **None found** | |
| Rodent and bed-rest bone studies | G | Exist in OSDR/analog literature in general; **not checked here** |

### 3.6 Limitations
DXA cannot distinguish bone size changes or detect all skeletal change that QCT detects (Read/Snippet); DXA is
not a fracture surrogate for younger adults (Vasadi 2015, Read); astronaut mean age about 47 years and a
mostly male cohort, so generalisation is limited (Read: mean 47 ± 5, n = 92); few scans per person.

### 3.7 Analysis methods
Per-person `%Δ` against own baseline with `LSC` as the detectability criterion; compare group means with mixed
models; model recovery with time-since-return as covariate, not as a fitted law we invented; keep **site**
(`hip`, `spine`, ...) as a required context key; report scanner/site precision. **Do not** implement T-score
"operating bands": NASA's report adapts WHO cut-points as operating bands (Read), but MEDVITAL applies none.

## 4. Cardiovascular health

Primary full texts were **not readable** (PMC bot check, login wall). Content below rests on a NASA summary
page and a Canadian Space Agency page (**Read**) plus search summaries (**Snippet**).

### 4.1 Quantities and units

| Quantity | Unit | Collection | Level |
| --- | --- | --- | --- |
| Heart rate | bpm | ECG or wearable | Read (CSA CCISS page: measured; no unit stated) |
| Blood pressure (systolic, diastolic) | mmHg | Ambulatory or beat-to-beat | Read (CCISS: measured; unit Known) |
| Physical activity | not stated | Wearable | Read (CCISS) |
| HRV spectra (e.g. LF/HF) | unitless ratio | From RR intervals | Snippet (review) |
| Ultrasound, MRI, CT imaging | modality-specific | CIPHER studies | Snippet (CIPHER summary) |

### 4.2 Formulas (Known; verify against the Task Force on HRV, 1996)

- `HR [bpm] = 60000 / RR [ms]`.
- `RMSSD [ms] = sqrt( (1/(N-1)) · Σ (RR_{i+1} - RR_i)² )`; `SDNN [ms] = sample SD of RR`.
- `PP = SBP - DBP`; `MAP ≈ DBP + PP/3` (implemented).
- Use only normal-to-normal intervals; exclude ectopic/artefact beats and record how.

### 4.3 Collection and frequency
CCISS (Canadian experiment 2007-2010; **Read**): six astronauts wore devices measuring blood pressure,
heart rate and activity over **24-hour periods before, during and after** missions. Device model, sampling rate
and analysis methods: **not stated**. Other methods (**Snippet**): NASA Cardiovascular and Vision Laboratory uses
ultrasound, ambulatory ECG and ambulatory blood-pressure monitoring; a thigh-cuff occlusion test studied heart rate
and arterial pressure responses; a smart-shirt study logs heart rate and breathing for 48 hours in flight.

### 4.4 Published findings (P)
CCISS (Read, qualitative only): heart-rate response to blood-pressure changes differed between astronauts;
cerebral arteries were less able to react to sudden pressure changes after flight; no statistics given.
Snippet-level: two ISS studies of HRV spectra showed similar non-specific rises in LF/HF; reported inflight
blood-pressure findings **conflict** between studies. Treat as unsettled.

### 4.5 Data availability
CCISS page states no data availability. No open astronaut heart-rate, BP or HRV time series was found.
CIPHER (Read): 14 studies, up to 30 astronauts, data gathered before, during and after flight; data release
terms not stated. Class **D: none found**.

### 4.6 Limitations
Tiny N (six in CCISS); conflicting findings; sampling schedules and devices not documented in readable sources;
HRV depends on recording length, posture and artefact handling, so values from different protocols are not comparable.

### 4.7 Analysis methods
Window-based summaries (e.g. per 5-minute or 24-hour window) with the window **recorded as context**; within-person
pre/in/post comparison; circadian pattern (cosinor or hour-of-day stratification) for 24-hour data; mixed-effects
models across people. No normal ranges.

## 5. Behavioral health

### 5.1 Quantities and units

| Quantity | Unit / scale | Collection | Level |
| --- | --- | --- | --- |
| Sleep duration | h per night | Wrist actigraphy (Actiwatch Spectrum) | Snippet; HRP deck mentions objective sleep measurement (Read) |
| Reaction time / alertness | ms | Reaction Self Test, a 3-minute PVT-Brief | Snippet |
| Stress, workload, mood ratings | visual analog scales (range not stated) | Self report in the Reaction Self Test | Snippet |
| Cognitive batteries (PVT, DSST, matrix reasoning, 2-back, etc.) | task-specific | Computerised tests | Read (HRP deck lists the tests in an analog study) |

### 5.2 Formulas
- Sleep summary: `mean sleep = Σ sleep_i / n`; trailing mean over a stated window (implemented: last 7 samples).
- PVT: response speed `= 1/RT` is a common transform and **lapse** is defined by a fixed reaction-time cut-off
  in the PVT literature; the **exact cut-off must be taken from the protocol paper** (Basner and Dinges 2011 is the
  usual citation; **not read**). Do not hard-code one from memory.
- Within-person standardisation: `z = (x - mean_baseline)/sd_baseline`.

### 5.3 Collection and frequency
Not documented in sources I could read. Snippet-level: actigraphy is worn continuously; the Reaction Self Test is
a computerised session; a six-month-mission study analysed 24 astronauts. **Schedule per astronaut: not found.**

### 5.4 Published findings (P; Read from a NASA HRP overview, secondary)
Average nightly sleep just over six hours on ISS up to 2011 (Flynn-Evans 2015); PVT reaction time related to sleep
and fatigue (Dinges 2017); self-reported stress rose for some crew in the second half of missions (Dinges 2017);
other cognitive measures suggest minimal changes (Strangman 2015, Tays 2021). Snippet: a 2022 Sleep paper (24
astronauts, six-month missions) linked shorter sleep to slower responses and higher stress. Numbers not verified.

### 5.5 Ground analogs (G, Read from HRP deck)
SIRIUS/NEK isolation, HERA, Antarctic stations, head-down bed rest, plus NSRL for radiation. The deck lists analog
limitations: small n, measurement limitations, uncertain generalisation to exploration and to astronauts.

### 5.6 Data availability
No open raw astronaut sleep, reaction-time or mood data found. CIPHER's Standard Measures (the baseline all astronauts
complete) are described but their contents are **not listed** on the CIPHER page read. Class **D: none found**.

### 5.7 Limitations
Self-report scales are not clinical instruments; the placeholder 0-10 scale in MEDVITAL is not any of NASA's;
cohorts are small, high-performing and heavily scheduled; analog populations differ from astronauts (Read).

### 5.8 Analysis methods
Per-person baseline and change; sleep-reaction-time association via mixed models with person random effects;
report distributions, not only means; keep analog results labelled `ground analog`. No cut-offs for "poor sleep" or
"high stress" are defined here.

## 6. Implementation guidance (maps to the current schema)

| Need | Action |
| --- | --- |
| Distinguish silicon vs water dose | Add `medium` to `context` (new metric variants only if units differ) |
| Bone site | Already `context.site`; make it required for `bmd_areal` when importing real data |
| Time since reference | Add `context.timepoint` (`L-<days>`, `FD<n>`, `R+<days>`) as used by the Inspiration4 dataset (Read) |
| Evidence class on non-data records | Add an `evidence_class` field only to documents/sources, not to observations; observations already carry `origin` |
| Measurement precision | Add optional `uncertainty` and `precision_error` fields before importing instrument data |
| HRV | Compute RMSSD/SDNN from RR in a new calculations function with a hand-computed test |
| Ground analog | New origin value is **not** needed: use `measured` with a `source_ref` that names the analog study |

Do not change the schema silently: update `contracts/`, `docs/DATA_DICTIONARY.md` and tests together.

## 7. NASA OSDR human data (Inspiration4), Read

Source: Sanders et al., npj Microgravity 2024 (Read via PMC). Ten OSD studies (a paper statement of "eight"
is internally inconsistent); four civilian crew; a **3-day** mission at 590 km; time points include L-92, L-44,
L-3, FD1-3, R+1, R+45 and R+82 for the skin microbiome study (the R+82 value was inferred from a run-together string in the text). Data types: sequencing, spatial transcriptomics,
proteomics, clinical blood assays (complete blood count, metabolic panels), cytokines, imaging, ultrasonography.
Only processed data are public; **individual-level raw data need an application and ethics approval**; human
RNA-seq needs authentication; medical datasets expose metadata only. Wearables: **not stated**. Programmatic access:
GLOpenAPI. Mapping to MEDVITAL metrics: **none of our eight base metrics**. Class: P and D (processed omics only).

## 8. Reproducibility rules for implementers

1. Every number you add to code or docs carries a source and a verification level from section 0.2.
2. Every calculation has a test with a hand-computed expected value.
3. Re-verify Known formulas (Q(LET), LSC, HRV, PVT lapse) against the cited primary source before coding.
4. No thresholds, normal ranges, risk scores or diagnostic labels, now or later, without a cited standard and expert review.

## 9. References

Read (opened and read, 2026-11-14):

1. Benton E. *Space Radiation Passive Dosimetry.* THREE, posted 2012-01-04. https://three.jsc.nasa.gov/articles/BentonPassiveDosimetry.pdf
2. Fry D, et al. *Final Report on Radiation Measurements Performed Inside of the BEAM Module.* NASA/TP-20240011436 (2024). https://ntrs.nasa.gov/citations/20240011436
3. Sibonga J, et al. *Evidence Report: Risk of Bone Fracture due to Spaceflight-induced Changes to Bone.* HRP-F07-ERFT.R2, NASA HRP (2024). https://ntrs.nasa.gov/citations/20240005190
4. Vasadi LJ, et al. *Recommended methods for monitoring skeletal health in astronauts...* (abstract, c. 2015). NTRS 20150019639. https://ntrs.nasa.gov/citations/20150019639
5. Whitmire A, Williams T. *Overview of NASA HRP Integrated Research Plan* (SBMT 2024). https://ntrs.nasa.gov/citations/20240003281
6. Sanders LM, et al. *Inspiration4 data access through the NASA Open Science Data Repository.* npj Microgravity 10:56 (2024). https://pmc.ncbi.nlm.nih.gov/articles/PMC11094041
7. NASA *About CIPHER* (updated 2024-07-30). https://www.nasa.gov/reference/about-cipher
8. NASA OSDR overview. https://science.nasa.gov/biological-physical/data/osdr
9. OSDR Environmental Data Application. https://visualization.osdr.nasa.gov/eda
10. OSDR RadLab overview. https://visualization.osdr.nasa.gov/radlab/gui/data-overview/
11. Canadian Space Agency, CCISS. https://asc-csa.gc.ca/eng/sciences/cciss.asp

Seen only in search summaries (Snippet; **not read**):

- Standard-measures and Actiwatch/Reaction Self Test descriptions; the 2022 Sleep paper (PMC8919197); the cardiovascular
  review (PMC4465859); the npj Microgravity paper s41526-019-0082-3; NASA Cardiovascular and Vision Laboratory page;
  LSDA data request page https://lsda.jsc.nasa.gov/explore/lsdahome/datarequest ; 2017 HRP bone report (NTRS 20170004597).

Standard methods used from general knowledge (**Known; verify before coding**): ICRP 1991 quality factor Q(LET); ISCD
precision-error and LSC convention; Task Force of the European Society of Cardiology and NASPE (1996) HRV definitions;
Basner M, Dinges DF (2011), PVT metrics.

Inaccessible (**not read**): the Space Apps 2026 official site (certificate error), PMC articles (bot check), Nature PDF
(login), Europe PMC (HTTP errors), OSDR terms page, RadLab ISS and API pages.

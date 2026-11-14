# Scientific Methodology

**Scope of v0.1.** MEDVITAL computes *descriptive* quantities from observations using standard,
documented arithmetic. It does not diagnose, classify, predict, or compare against clinical
or regulatory thresholds. **No finding in this repository is a scientific result.** The
domain-specific choices below have **not yet been reviewed by a subject-matter expert**; that review is an
open item (DECISIONS Q-6).

## 1. Data origins and the simulated data

Every observation is exactly one of:

| Origin | Meaning | Requirements |
|---|---|---|
| `simulated` | produced by MEDVITAL's generator | `generator_version`, `seed` |
| `measured` | recorded outside MEDVITAL (instrument, person, external dataset) | `source_ref` |
| `modeled` | computed by a documented method | `method` |

Rules: origins are never pooled in any statistic; a derived value is always `modeled` and records the origin
of its inputs (`input_origin`); summaries are partitioned by origin.

**Simulation.** `simulation/generator.py` draws from `numpy.random.default_rng(seed)`. Magnitudes (e.g. 1.0 mGy/day,
−0.01 %/day bone drift, 5 % noise) are **arbitrary round test-signal values chosen to exercise software**. They
are not taken from any NASA dataset, mission, paper or standard, and nothing computed from them is a
finding. Profiles (`SIM-A01…A04`) are synthetic and correspond to no real person. Identical
(profile, start, days, seed, parameters) yields identical observations and ids (UUIDv5).

## 2. Radiation

Inputs: `radiation.absorbed_dose_daily` (mGy), `radiation.dose_equivalent_daily` (mSv) — each a per-UTC-day integral.

Calculations (`modules/radiation/calculations.py`):
* **Cumulative dose over observed days** = Σ values, in time order. Missing days are **not imputed**, so with gaps this is a
  lower bound on true accumulation of the supplied series.
* **Mean daily dose** = arithmetic mean of supplied daily values (unit `<unit>/d`).
* Duplicate-day guard: more than one observation of a series on the same UTC day produces a warning (possible double counting).

Not implemented / out of scope: dose-to-risk models, organ doses, quality-factor derivation, effective-dose computation,
career or mission limits, SAA/solar-event attribution. Any limit comparison must come with a citation (see
`NASA_SOURCES.md`) and will be an injected, sourced reference object — not a constant in code.

## 3. Bone health

Input: `bone.areal_bmd` (g/cm²), context `site` (and optionally `device`). Series are separated per origin, site and device.

* **Percent change from first observation** = 100·(latest − first)/first; requires ≥ 2 points and first > 0.
* **Trend slope** = ordinary least-squares slope of value vs elapsed days (`scipy.stats.linregress`); requires ≥ 3
  points at distinct times. Descriptive of the supplied points, **not a forecast**.

Limitations: no measurement-precision / least-significant-change handling (instrument-specific and must be sourced);
no cross-device calibration; no site-specific interpretation; no T/Z-score (these embed clinical reference populations — not implemented).

## 4. Cardiovascular health

Inputs: `resting_heart_rate` ({beats}/min), `rr_interval` (ms), `systolic_bp`/`diastolic_bp` (mm[Hg]).

* Heart rate and blood pressure: descriptive statistics only (count, mean, sample SD, min, max), per origin/device(/posture).
* **RMSSD** per recording session (context `session_id`):
  RMSSD = √( mean( (RRᵢ₊₁ − RRᵢ)² ) ). Requires ≥ 3 intervals, all > 0, time-ordered.

Limitations: **no artefact or ectopic-beat correction**; RMSSD is sensitive to such artefacts, so only clean
recordings are meaningful. Short-recording validity and frequency-domain HRV are not addressed. No BP classification.

## 5. Behavioral health

Inputs: `sleep_duration` (h), `self_report_score` ({score}; the **instrument must be named** in context).

* **Deviation from own baseline.** For each (origin, instrument/device) series, the first *N* values form the subject's baseline
  (default N = 7, an engineering default, configurable, no clinical meaning). `sklearn.preprocessing.RobustScaler` is fitted
  on the baseline only and applied to later values: (x − median)/IQR. The latest value's deviation is reported.
  If the baseline IQR is 0, scikit-learn uses scale 1 (deviation in raw units).

Interpretation: where the latest value sits relative to the person's *own* earlier values. It is not a score of wellbeing, mood
disorder, fatigue, or performance. Scores from different instruments are never pooled; no instrument norms or cut-offs are applied.

## 6. Cross-cutting statistics (`core/stats.py`)

* `describe`: count, mean, sample SD (ddof = 1; `None` for n < 2), min, max.
* `fit_linear_trend`: OLS slope/intercept/r/standard error; `None` if n < 3 or all times identical.

## 7. Method versioning and validation

Each derived value carries a `method` string with a version suffix (e.g. `… v1`). Change a calculation ⇒ bump the suffix and
update this document. Unit tests use hand-computed expected values (e.g. RMSSD of 800, 810, 790 = √250). There is **no
validation against external reference data yet** because none has been ingested (DECISIONS Q-2).

## 8. Planned work (not started)

Sourced reference limits as injectable objects with mandatory citations; real-dataset ingestion with licences; uncertainty
propagation; measurement-precision handling; expert review of each module's methods; the advanced analysis/AI layer
(to be specified separately, and held to the same provenance and no-diagnosis rules).

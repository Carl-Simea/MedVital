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

## 9. Analysis engine (`analysis/`, v0.1.0)

A cross-domain, descriptive engine used *alongside* the module summaries (it does not replace them). Arithmetic is in
`analysis/calculations.py` (NumPy only, pure); `analysis/engine.py` adapts observations and keeps provenance.
Entry point: `medvital.analysis.analyze(observations, config, registry=None) -> AnalysisReport`.

* **Series.** Values are compared only within one (subject, metric, unit, data origin, device id, full context) series.
  Simulated, measured and modeled values are never pooled; neither are devices, sites, instruments or sessions.
* **Exclusions are reported, never silent.** An observation is excluded from statistics, and listed with a reason, when it is
  superseded by another observation in the input, when its `quality` is not in `analyzed_qualities` (default: `valid` only; `suspect`/`invalid` are excluded and counted), or when it fails registry validation (only if a registry is passed).
* **Descriptive statistics:** count, mean, sample SD (ddof = 1; `None` for n < 2), median, quartiles (linear interpolation),
  IQR, MAD (median absolute deviation, unscaled), min, max.
* **Personal baseline:** the first *n* analysed values of the series (default n = 7, engineering default) or a configured
  time window `[start, end)`. Fewer than `min_count` (default 4) baseline values ⇒ no deviations, with a warning.
  Post-baseline values get: delta from baseline median (series unit); z = (x − mean)/SD; modified z =
  0.6745·(x − median)/MAD. Undefined scores (SD or MAD = 0) are `null`, never imputed.
* **Statistical anomaly flags:** |modified z| > cutoff, default 3.5 — the statistical convention of Iglewicz & Hoaglin (1993),
  *How to Detect and Handle Outliers*, ASQC Quality Press. It is an outlier heuristic for *review*, not a clinical threshold,
  and it is configurable. Each flag carries the observation id, timestamp, value, unit, data origin, method and cutoff.
* **Missingness / data quality:** quality-value counts, exclusion counts, duplicate timestamps, expected sampling interval
  (configured per metric, else inferred as the median spacing and labelled `inferred`), gaps (spacing > `gap_factor` × interval,
  default 2), expected count ⌊span/interval⌋ + 1, coverage = distinct timestamps / expected (capped at 1), and
  `missing_series` for configured `expected_metrics` absent per subject.
* **Output:** `AnalysisReport` (pydantic, frozen) → `model_dump(mode="json")`; strict JSON (no NaN). Carries `ANALYSIS_NOTICE`.

Limitations: no autocorrelation, seasonality (e.g. circadian) or trend adjustment, so a drifting series will accumulate
flags; baseline is a single fixed reference; no measurement-uncertainty handling; inferred intervals are meaningless for
event-driven (irregular) metrics. Defaults are engineering choices and need expert review (Q-6).

## 10. Pure calculations added in M1b (not yet wired into summaries)

Formula provenance, assumptions and source status: docs/MODELING_GAP_ANALYSIS.md §1 (F1–F6). All take explicit units,
reject anything else (no silent conversion), and return numbers only — no labels, no thresholds.

| Function | Formula | Notes |
|---|---|---|
| `core.stats.percent_change(current, baseline, u_current, u_baseline)` | 100·(x − x₀)/x₀; u per F2 | `uncertainty=None` unless both input uncertainties are known; explicit 0 means known zero. x₀ ≠ 0. |
| `cardiovascular.cardiac_output(hr, sv, heart_rate_unit, stroke_volume_unit)` | HR·SV/1000 → L/min | Units `{beats}/min`, `mL` only; HR, SV > 0. |
| `cardiovascular.mean_arterial_pressure_estimate(sbp, dbp, unit)` | DBP + (SBP − DBP)/3 | **Uncited approximation** (G-7); `mm[Hg]`; SBP ≥ DBP > 0. Output is modeled, never a measured MAP. |
| `behavioral.sleep_efficiency(tst, tib, unit)` | TST/TIB·100 | Hand & Siengsukon 2025. Same unit (h/min/s); 0 ≤ TST ≤ TIB, TIB > 0. TIB definition must be recorded by the caller (G-10). No cut-off. |
| `radiation.dose_from_constant_rate(rate, rate_unit, elapsed_s)` | Ḋ·Δt | Units `uGy/h`, `mGy/d`, `uSv/h`, `mSv/d`; output keeps Gy vs Sv; assumes constant rate over the interval. |

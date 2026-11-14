# Scientific methodology

MEDVITAL is a research prototype. This document states exactly what the code computes and,
just as importantly, what it does **not** claim.

## Principles

1. **No fabricated science.** No dataset, finding, citation, reference range or dose figure is
   invented. Numbers that appear in code are either (a) arithmetic definitions, or (b) clearly
   labelled illustrative simulator parameters.
2. **Three kinds of data, never blended.**
   - *Simulated*: produced by our seeded generator. Says nothing about real astronauts.
   - *Measured*: a recorded value with a citation or dataset reference. **None exist in this repo yet.**
   - *Modeled*: computed by a named, versioned method from other observations, with input ids.
3. **No diagnosis, no clinical thresholds.** The software never labels a value normal, abnormal,
   safe, dangerous, healthy or at risk. It never compares against a limit.
4. **Describe, don't judge.** Outputs are descriptive statistics and arithmetic transformations.

## What is computed

### Generic (`core/stats.py`)

| Function | Definition |
| --- | --- |
| `series_stats` | Mean; sample standard deviation (n-1); ordinary least-squares slope per day via `scipy.stats.linregress` (only when n >= 3 and times differ) |
| `baseline_z_scores` | `(x - mean(first k)) / sd(first k)`: deviation from the person's own early values. NaN when the baseline has zero spread. Available, not yet wired to an endpoint |
| `multivariate_outlier_scores` | scikit-learn `IsolationForest`, fixed seed, score = `-score_samples`. A relative rank within the supplied data. Available, not yet wired to an endpoint |
| `trapezoid_integral` | Trapezoidal rule via `scipy.integrate.trapezoid` |

### Module-specific (`modules/<name>/calculations.py`)

| Module | Derived metric | Method (id) | Formula |
| --- | --- | --- | --- |
| Radiation | `cumulative_absorbed_dose` (uGy) | `trapezoidal_integration_of_dose_rate_v1` | integral of dose rate (uGy/day) over elapsed days |
| Bone | `bmd_percent_change_from_baseline` (percent) | `percent_change_from_first_observation_v1` | `(last - first) / first * 100`, per site, first observation is the person's own baseline |
| Cardiovascular | `mean_arterial_pressure` (mmHg) | `map_diastolic_plus_one_third_pulse_pressure_v1` | `DBP + (SBP - DBP) / 3` (common approximation) for readings at the same instant |
| Behavioral | `sleep_duration_7d_mean` (h) | `trailing_mean_of_last_7_samples_v1` | mean of the 7 most recent samples |

The window of 7 and the "first observation is baseline" choices are **modelling conventions for
the prototype**, not clinical standards.

Method ids are versioned (`_v1`). A change to a formula must create a new id so stored modeled
values remain interpretable.

## Simulation

`core/simulation.py` draws each sample as `mean + drift_per_day * day + Normal(0, sd)`, clipped
to the metric's scale bounds, from a NumPy generator seeded by `(seed, crc32(profile), crc32(metric))`.
The same inputs always give the same series and the same observation ids.

- Profile means and SDs (`simulated_profiles.py`) are **illustrative developer choices** to give
  plausible scale and make profiles distinguishable. They are not derived from NASA or any
  published dataset and must not be quoted as such.
- **`drift_per_day` is 0 for every profile.** The simulator does not assume any effect of
  spaceflight. A scenario that wants one must set it explicitly and label it as an assumption.
- `physical_min` / `physical_max` only keep values on a valid scale (non-negative, 0-24 h in a
  day, 0-10 for the placeholder stress scale). They are not health limits.
- `self_reported_stress` uses a plain 0-10 placeholder scale. It is **not a validated
  instrument** and no interpretation is attached.

## Known scientific limitations

- Metric units and definitions were chosen for software clarity. They have not been reviewed by
  a domain expert (radiation physicist, bone/cardiovascular physiologist, behavioral scientist).
- Per-module simulation is univariate. It models no physiology, no correlation between metrics
  and no time-of-day or mission-phase structure.
- Trend slopes on short or noisy series are unstable; the API reports `null` rather than
  extrapolating when n < 3.
- Radiation: dose-rate to cumulative dose is arithmetic accumulation. It is not a dose-equivalent,
  effective-dose or risk calculation, and no quality factors or limits are applied.
- Bone: percent change from a single site's first observation ignores measurement precision.
- Cardiovascular: MAP is an approximation. HRV (`hrv_rmssd`) is accepted as a measured/simulated
  value; MEDVITAL does not yet compute it from RR intervals.

## Path to real data

Before any `measured` value is accepted by a deployed system: identify the source in
`NASA_SOURCES.md` and verify its license and access conditions; record `source_ref`; add unit
conversion tests; have a domain expert review the module's metric definitions; add
authentication (see D-011). Only then should thresholds or interpretation even be discussed, and
only from published standards cited in this repo, never invented.

## Validation strategy

- Every calculation has a test with hand-computed expected values (`tests/test_module_*.py`,
  `tests/test_stats.py`).
- Simulation reproducibility and bounds are tested (`tests/test_simulation.py`).
- Provenance rules are tested (`tests/test_provenance.py`, `tests/test_registry.py`).
- Module independence is enforced by import analysis (`tests/test_architecture.py`).

# Modeling Gap Analysis

**Status:** created in milestone M1 (2026-11-14). It records every formula and modelling assumption the roadmap needs,
what each one rests on, and what is still missing. Update it whenever a formula, source or assumption changes.

**Source key** (same as NASA_SOURCES.md)
* **V**: read at the source this session (page opened, or file downloaded and inspected).
* **S**: known only from search summaries. **Not verified.**
* **K**: stated from general knowledge. The source was **not opened**. Treat it as unverified until it is.
* **D**: definitional or algebraic. Needs no empirical source, and the derivation is shown here.

---

## 1. Formula review

| # | Quantity | Formula | Kind | Source | Output origin | Implemented |
|---|---|---|---|---|---|---|
| F1 | Percentage change from baseline | Δ% = 100·(x − x₀)/x₀ | D | — | modeled | `core/stats.percent_change` (M1b). Bone already has `percent_change_from_baseline` |
| F2 | Uncertainty of F1 | u(Δ%) = (100/x₀²)·√(x₀²·u(x)² + x²·u(x₀)²) | D (first-order Taylor, inputs independent) | GUM JCGM 100:2008, law of propagation: **K**. The PDF was fetched from bipm.org but could not be parsed here | modeled | `core/stats.percent_change` (M1b) |
| F3 | Cardiac output | CO [L/min] = HR [beats/min] × SV [mL] / 1000 | D (definition of CO, plus a unit conversion) | — | modeled | `cardiovascular/calculations.cardiac_output` (M1b) |
| F4 | Mean arterial pressure | MAP ≈ DBP + (SBP − DBP)/3 | **Convention** (an approximation) | StatPearls NBK538226: **not verified**, the NCBI page returned a bot check | modeled; the method string says "uncited approximation" | `cardiovascular/calculations.mean_arterial_pressure_estimate` (M1b) |
| F5 | Sleep efficiency | SE [%] = TST / TIB × 100 | Definition | Hand & Siengsukon 2025, *Sleep Adv* 6(3):zpaf045, DOI 10.1093/sleepadvances/zpaf045: **V**. The paper documents disagreement over TIB (literal time in bed vs "intention to sleep" window) | modeled | `behavioral/calculations.sleep_efficiency` (M1b) |
| F6 | Dose at a constant rate | D = Ḋ · Δt | D | — | modeled | `radiation/calculations.dose_from_constant_rate` (M1b) |
| F7 | Cumulative dose | D_total = Σ ΔD_i | D | — | modeled | `radiation/calculations.cumulative_dose` (existing) |
| F8 | RMSSD | √mean(Δ RR²) | D (standard HRV statistic) | **K** | modeled | `cardiovascular/calculations.rmssd` (existing) |
| F9 | Modified z-score | 0.6745·(x − median)/MAD | D, plus a statistical convention for the 3.5 cutoff | Iglewicz & Hoaglin 1993: **K** (not opened) | statistical flag, not an origin | `analysis/calculations` (existing) |
| F10 | Robust baseline deviation | (x − median)/IQR (RobustScaler) | D | — | modeled | `behavioral/calculations` (existing) |

### Derivation of F2

Δ% = f(x, x₀) = 100·(x − x₀)/x₀.

The partial derivatives are ∂f/∂x = 100/x₀ and ∂f/∂x₀ = −100·x/x₀².

For independent inputs, first-order propagation gives
u(Δ%)² = (100/x₀)²·u(x)² + (100·x/x₀²)²·u(x₀)².
Factoring out 100/x₀² gives F2.

**Assumptions:**
- **Independence.** Not true if the same scanner and operator produced both values. A correlation term would *reduce*
  u(Δ%), so ignoring it is conservative.
- **Linearisation.** Accurate only when u(x₀) ≪ x₀.

**Rules:**
- An unknown uncertainty gives `None`, never 0.
- An explicit `0.0` means "known to be zero".

### Input validation required by each implementation

| # | Validation rules |
|---|---|
| F1/F2 | x₀ ≠ 0 (division). Uncertainties ≥ 0 or `None`. Finite inputs. **Same unit for x and x₀.** The caller guarantees this, because both come from one series in which `analysis` never pools units. |
| F3 | Explicit units: HR in `{beats}/min`, SV in `mL`, anything else is rejected. HR > 0. SV > 0. |
| F4 | Both inputs in `mm[Hg]`. SBP ≥ DBP > 0. The result is labelled an estimate. |
| F5 | TST and TIB in the same unit (`h`, `min` or `s`). TIB > 0. 0 ≤ TST ≤ TIB. **The TIB definition must travel with the result** (context `tib_definition`). Values computed with different TIB definitions are never pooled. |
| F6 | Explicit rate unit from a closed table (`uGy/h`, `mGy/d`, `uSv/h`, `mSv/d`). Elapsed time in seconds, ≥ 0. Rate ≥ 0. Output unit follows the input quantity: Gy-based stays Gy, Sv-based stays Sv. **No Gy↔Sv conversion.** |

**What none of these formulas does:**
- No formula maps a value to "normal", "abnormal" or a risk class (rule 3).
- A sleep-efficiency cutoff seen in the literature search is **deliberately not adopted**.

---

## 2. Assumptions the roadmap needs that have no source yet

| ID | Assumption needed | Status | Allowed handling until it is sourced |
|---|---|---|---|
| G-1 | Rate of spaceflight bone loss per site and month | **No verified source.** Sibonga et al. 2007 (DOI 10.1016/j.bone.2007.08.022) is **S** and is about *recovery* | No coefficient is hard-coded. A modelled trajectory must take the rate as a configured, labelled assumption, with value and unit supplied by the user and recorded in provenance. |
| G-2 | Postflight bone recovery curve | **S** (Sibonga 2007, not opened) | Same as G-1 |
| G-3 | Effect size of exercise countermeasures | No source | Configurable assumption only, labelled. Default: **no effect modelled**. |
| G-4 | DXA/QCT scan precision | No source | `uncertainty = None`, so propagated uncertainty is `None`. Never invent a precision value. |
| G-5 | Solar-particle-event (SPE) scenario magnitudes | No source for the shape of a scenario | Synthetic scenario inputs, labelled `simulated`, with arbitrary magnitudes (rule 8). DONKI event timing can be real, **V**. |
| G-6 | Converting detector absorbed dose to human tissue dose | Requires a radiation-transport and dosimetry model | **Out of scope.** Never convert. Curiosity RAD and CRaTER values stay environmental (proposal P-2). |
| G-7 | MAP approximation (F4) | Citation not verified | Implement it labelled as an uncited approximation. Replace the label when a source has been read. |
| G-8 | GUM propagation law (F2) | **K** | The formula is algebraically derived above. The citation is still to be verified (open the PDF with a working PDF reader). |
| G-9 | Iglewicz & Hoaglin 1993 cutoff (F9) | **K** | The cutoff is configurable and not clinical. The citation is still to be verified. |
| G-10 | Definition of time in bed (TIB) for actigraphy sleep efficiency | Disputed in the literature, **V** | Record `tib_definition` with every value. Never pool across definitions. |
| G-11 | Mission time model (mission day, L-/R+ relative timepoints) | Design only (Q-4) | Converting a relative timepoint to an absolute timestamp is **modeled** and needs a mission record (M4). |
| G-12 | HRV suitability checks (artefact and ectopic-beat handling) | No method chosen | RMSSD assumes artefact-free input. No automatic suitability claim. |
| G-13 | Reference values from published cohorts | Needs the `PublishedReference` entity (D-019) | Never stored as observations. |

---

## 3. Coverage of master-prompt features, by domain

| Domain | Requested | Existing | Gap |
|---|---|---|---|
| Bone | DXA, QCT, sites, BMD, trabecular measures, formation and resorption markers, calcium, countermeasures, recovery | `bone.areal_bmd` (g/cm2; `site` and `device` context), percentage change | No `method` (DXA vs QCT) distinction, no QCT volumetric BMD, no trabecular metrics, no markers, no trajectory model (G-1 to G-4). OSD-804 data is mouse microCT, and as **V** it contains no BMD. |
| Cardiovascular | HR, BP, SpO2, respiration, ECG, beat-to-beat intervals, HRV, SV, CO, VO2max, biomarkers | resting HR, wearable HR, RR interval, SBP/DBP, RMSSD | No SpO2, respiration, SV, VO2max or biomarker metrics. CO and MAP come in M1b. Biomarkers need their own category (never telemetry). The OSD-569 blood counts are haematology. |
| Radiation | GCR/SPE distinction, environmental vs personal, Gy/Sv/rate, detector metadata, uncertainty, quality | daily absorbed dose, daily dose equivalent, dose rate (uGy/h), cumulative dose | No environmental entity (P-2), no detector metadata, no SPE scenarios. Dose from rate × time comes in M1b. |
| Behavioral | sleep duration and efficiency, actigraphy, activity, mood, team cohesion, cognition | `sleep_duration` (h), `self_report_score` with instrument | Sleep efficiency comes in M1b. No TIB, onset latency or WASO metrics, and no subscale context (decision pending). NLSP variables are **V**, but the data needs a formal request. |
| Shared | trends, uncertainty reporting | `analysis` engine, `core.stats.fit_linear_trend` | The analysis engine does not yet carry per-value uncertainty. The `HealthObservation` schema has **no uncertainty field**; that is a schema change for M2 or later. |

---

## 4. Known data defects in sources (verified, research pass 2)

* OSD-569 TRANSFORMED CSV labels hemoglobin as `percent`. The SUBMITTED CSV says `g/dL`. Take units from SUBMITTED.
* OSD-804 TRANSFORMED CSV gives the ratios BA/TA and BV/TV the units mm² and mm³. The original workbook gives no unit.
  BMD and Cort.TMD are defined in its data dictionary but absent from the data.

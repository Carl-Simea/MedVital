# Source register: decision logic (engine, PVT, check-in)

As of 2026-11-14. "Verified" = checked against the named source in this work (for NASA reports via search excerpts and abstracts, not the full text). "Convention" = not verified, marked as a placeholder. Sources for the per-part model are in `SOURCES-parts.md`.

## Verified

| Statement | Value in code | Source |
|---|---|---|
| Five HRP hazards: radiation, isolation/confinement, distance from Earth, gravity fields, hostile/closed environments | Info cards | NASA HRP, https://www.nasa.gov/hrp/hazards |
| Mean bone loss 1–1.5 % aBMD per month (weight-bearing skeletal sites) | `evalBoneModel` avg | NASA Evidence Report "Risk of Bone Fracture…", 2017, https://ntrs.nasa.gov/api/citations/20170004597/downloads/20170004597.pdf |
| Per site: hip 1.5 / lumbar spine 1 / whole body 0.3 % per month (DXA, LeBlanc 2000) | `evalBoneModel` detail | Sibonga, NASA HRP, 2015, https://ntrs.nasa.gov/api/citations/20150001885/downloads/20150001885.pdf |
| An updated Fracture Evidence Report 2023/2024 exists | Note | https://ntrs.nasa.gov/citations/20240005190 |
| Standard PVT: 10 min, interval 2–10 s, lapse = response ≥ 500 ms | Docs | Basner et al. 2011, https://pmc.ncbi.nlm.nih.gov/articles/3197786 |
| PVT-B: 3 min, interval 1–4 s incl. 1 s feedback, lapse threshold 355 ms, false start < 100 ms, 30 s without a response counts as a lapse | `PvtSession`, `scorePvt` | Basner et al. 2011 (above); implementation details: https://www.psytoolkit.org/experiment-library/pvtb.html (secondary) |
| 11 and 20 lapses (355 ms) separate high, medium and low performance in a simulated baggage-screening task | `evalPvt` thresholds warn/alert | Basner & Rubinstein 2011, https://pmc.ncbi.nlm.nih.gov/articles/PMC3190077 (applies to a baggage-screening task, not to astronauts) |
| NASA PVT app on touchscreens: device latency 77.42 ms (SD 16.77); responses slower than PVT-192 | Warning: the web version is not calibrated | Arsintescu, NASA, 2017, https://ntrs.nasa.gov/api/citations/20170009855/downloads/20170009855.pdf |
| Healthy reference, 10-min PVT: mean 1/RT 4.51 ± 0.42 (≈ 222 ms) | Baseline note | Thomann et al. 2014 via PsyToolkit (secondary) |
| One-way radio delay Mars–Earth 3–22 min | `CONTEXTS.mars` 182–1337 s | NASA/JPL, https://science.nasa.gov/?p=354728 |
| Sleep loss occurs in flight; performance decline is expected | Info card brain/sleep | NASA Evidence Report "Sleep Loss, Circadian Desynchronization, Work Overload", https://ntrs.nasa.gov/api/citations/20160003864/downloads/20160003864.pdf |
| ISS exercise devices ARED, T2, CEVIS; crew average about 2 h of exercise per day (2.5 h scheduled, 6 days per week) | `knowledge.mjs` skeleton | https://www.nasa.gov/missions/station/iss-research/astronaut-exercise/ ; https://phys.org/news/2024-05-important-crew-health-space-missions.html (secondary) ; NASA podcast https://www.nasa.gov/?p=407627 |
| Mean loss of strength and aerobic fitness 10–12 %; 12–38 % of crew lose > 20 % | `knowledge.mjs` muscle | https://www.nasa.gov/reference/risk-of-reduced-cardiorespiratory-and-musculoskeletal-fitness |
| Orthostatic intolerance = main in-flight risk (LEO, Moon); cardiovascular disease = long-term risk; jugular vein: stagnant or reverse flow in 6 of 11, one thrombus | `knowledge.mjs` cardio | https://www.nasa.gov/directorates/esdmd/hhp/risk-of-cardiovascular-adaptations-contributing-to-adverse-mission-performance-and-health-outcomes/ ; https://www.nasa.gov/?p=222800 |
| SANS: optic disc edema, globe flattening, choroidal folds, hyperopic shift; measured by OCT and imaging | `knowledge.mjs` brain | https://pmc.ncbi.nlm.nih.gov/articles/PMC7005826 ; https://pmc.ncbi.nlm.nih.gov/articles/PMC7118682 |
| The 1–1.5 % figure comes from pre- and postflight DXA; bone is not measured in flight | Rationale for the model | https://doi.org/10.1007/s11914-013-0136-5 |

## Corrections to earlier statements

- "1–2 % bone loss per month" comes from an older article (NASA Astrobiology 2001). The 2017 Evidence Report states 1–1.5 %.
- "About 250 ms when rested" for the NASA PVT was not verified and is not in the code. Only the reference value above is verified.
- "20 minutes each way" (quoted from the HRP page) is an approximation. Verified is 3–22 min.

## Convention or assumption (not verified)

- Resting heart-rate thresholds 40 / 50 / 100 / 120 per minute (`evalHeartRate`).
- z-limits against the personal baseline: −1.5 / −2.5 (PVT 1/RT) and +2 / +3 (resting heart rate).
- "Re-measure after about 10 min" in the triage.
- Radio delay ISS 1 s (depends on the relay), Moon 1.3 s (light time, secondary source).
- Caps per data source: camera and simulation at most `warn`, models at most `watch`.

## Not read

The HRP Integrated Research Plan and the full text of the Evidence Reports.

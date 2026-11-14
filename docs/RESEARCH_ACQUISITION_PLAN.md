# Research & Data Acquisition Plan

**Status:** plan only, 2026-11-14. Nothing listed here has been downloaded or ingested. Builds on
[NASA_SOURCES.md](NASA_SOURCES.md) (research pass 1); does not replace it.

**Verification key**
* **V**: read at the primary host in research pass 1 (see NASA_SOURCES.md).
* **S**: seen only in search-result summaries on 2026-11-14. The page was **not opened**. Confirm at source before use.
* **?**: the item is a question to answer, not a fact.

No numbers, thresholds or findings are copied from any publication here. Publications are listed so the team can read
their methods and data-availability statements. Every variable or unit marked S or ? must be confirmed in the dataset's own
documentation before it goes into `metrics.py`.

**Acquisition tiers** (ordered by priority)
1. **Downloadable now.** Public, no request needed, machine-readable.
2. **Downloadable, wrong population.** Public, but animal, cell or ground-analogue data. Never stored as an astronaut
   `subject_id`, and never mixed with crew series.
3. **Controlled.** Needs a NASA request, IRB documentation or a Data User Agreement. Not realistic within a hackathon.
4. **Publication only.** Aggregate results in a paper. Use it for methods and context, never as observations.

---

## 1. Radiation

| Priority | Source | Tier | What it gives | Variables / units | Links | Ver. |
|---|---|---|---|---|---|---|
| 1 | **NASA DONKI** (space-weather events) | 1 | Event timeline (SEP, CME, flares, storms) as *environmental context* | Field names verified (NASA_SOURCES §1). **Units of numeric fields not verified.** UTC `…Z` timestamps | <https://api.nasa.gov/>, <https://ccmc.gsfc.nasa.gov/DONKI/> | V |
| 1 | **MSL RAD RDR** `MSL-M-RAD-3-RDR-V1.0` (Curiosity) | 1 | Calibrated environmental dose-rate time series, Mars cruise and surface | `TOT_DOSE_B`, `TOT_DOSE_E` in **µGy/h**; LET arrays in keV/µm | <https://pds-ppi.igpp.ucla.edu/data/MSL-M-RAD-3-RDR-V1.0/> | V |
| 2 | **LRO CRaTER** derived data `LRO-L-CRAT-3_4-DDR-PROCESSED-V1.0` (lunar orbit) | 1 | Product listing names daily dose rates and dose equivalent | ? File names, formats and units not confirmed | <https://pds-ppi.igpp.ucla.edu/data/LRO-L-CRAT-3_4-DDR-PROCESSED-V1.0/ERRATA.TXT>, PDS4 bundle readme <https://pds.nasa.gov/data/pds4/releases/ppi/lro-crater-20260306/Readme_2.2.txt>, product site <https://crater-products.sr.unh.edu/> | S |
| 3 | **Artemis I MARE** (Helga/Zohar phantoms in Orion), *Nature* paper "Space radiation measurements during the Artemis I lunar mission" | 4 (data-availability statement still to check) | Dose measured inside a crewed-vehicle geometry | ? DOI not confirmed | DLR summary <https://www.dlr.de/en/latest/news/2024/orion-spacecraft-radiation-protection-tested-initial-findings-from-artemis-i-moon-mission>, OSTI <https://www.osti.gov/pages/servlets/purl/2447574> | S |
| — | ISS Crew Active Dosimeters (SRAG) | 3 | Individual time-resolved crew dose | — | <https://srag.jsc.nasa.gov/SpaceRadiation/How/How.cfm> | V (existence only) |

**Modelling note:** DONKI, RAD and CRaTER all measure the *environment*. None of them measures a person. Proposal P-2 in
DECISIONS (a separate `EnvironmentalMeasurement` entity) has to be decided before ingestion. The uncommitted
`radiation.dose_rate` metric (uGy/h) has the same unit as RAD's `TOT_DOSE_*`, but RAD values must not be stored as a
crew member's dose rate.

## 2. Bone health

| Priority | Source | Tier | What it gives | Variables / units | Links | Ver. |
|---|---|---|---|---|---|---|
| 1 | **OSD-804**, Rodent Research-1 (37-day flight), femur and vertebra microCT | 2 | Real spaceflight bone-structure measurements (mouse). **No BMD in the data.** | Verified in NASA_SOURCES §6b (unit defects noted) | <https://osdr.nasa.gov/bio/repo/data/studies/OSD-804> (DOI 10.26030/yh5h-h706 not seen in the files) | V |
| 2 | **OSD-396**, femoral segmental defect healing (SpaceX-10, mouse) | 2 | microCT of the femur | ? | catalog <https://catalog.data.gov/dataset/gene-metabolite-networks-associated-with-impediment-of-bone-fracture-repair-in-spaceflight> | S |
| 3 | **LSDA / NLSP**, astronaut DXA (Lifetime Surveillance of Astronaut Health) | 3 | Individual areal BMD (the metric `bone.areal_bmd` assumes) | — | Request form <https://nlsp.nasa.gov/explore/lsdahome/datarequest>, context <https://www.nasa.gov/content/bone-and-mineral-evaluation-and-analysis> | S |
| — | Sibonga et al. 2007, *Bone* 41(6), DOI 10.1016/j.bone.2007.08.022 (post-flight BMD recovery, DXA) | 4 | Methods for fitting a recovery curve | Aggregate only | <https://ntrs.nasa.gov/citations/20070032016> | S |

**Gap:** no public, individual-level astronaut BMD found. For crew, the bone module stays on *simulated* data.

## 3. Cardiovascular health

| Priority | Source | Tier | What it gives | Variables / units | Links | Ver. |
|---|---|---|---|---|---|---|
| 1 | **OSD-569**, Inspiration4 complete blood count (4 crew, pre/post flight) | 1 | Only clinical-lab-style astronaut table found so far (haematology, not haemodynamics) | Verified in NASA_SOURCES §6a (hemoglobin unit defect in TRANSFORMED) | <https://osdr.nasa.gov/osdr/data/osd/files/569> | V |
| 2 | **NLSP/LSDA**: browse for public, non-attributable cardiovascular downloads | 1 or 3 ? | LSDA says much non-attributable data downloads directly; which datasets do is unknown | ? | <https://data.nasa.gov/dataset/nasa-life-sciences-portal-nlsp> | S |
| — | NASA Twins Study, Garrett-Bakelman et al. 2019, *Science*, DOI 10.1126/science.aau8650 | 4 (data availability still to check) | Methods for carotid and cardiovascular measurements across a long-duration mission | Aggregate | <https://pubmed.ncbi.nlm.nih.gov/30975860/> | S |
| — | Miniature Biometric Sensor Project (ISS heart-rate monitoring context) | 4 | Background on sensor drop-out and motion artefact, for wearable design | — | <https://ntrs.nasa.gov/citations/20150016028> | V |

**Gap:** no public continuous HR, ECG, RR or BP astronaut series (confirmed in pass 1 at OSDR; not contradicted this pass).

## 4. Behavioral health

| Priority | Source | Tier | What it gives | Variables / units | Links | Ver. |
|---|---|---|---|---|---|---|
| 1 | **NLSP "Standard Measures – HERA"** (analogue: behavioural health + cortisol) | **3** (pass 2: "accessible via data request") | Analogue-crew behavioural standard measures | Variable names verified, no units (NASA_SOURCES §6c) | <https://nlsp.nasa.gov/resources/standard-measures> | V |
| — | HERA facility capabilities (2019), which lists actigraphy | 4 | Which measures exist in HERA | — | <https://www.nasa.gov/wp-content/uploads/2016/05/2019_hera_facility_capabilities_information.pdf> | S |
| — | Barger et al. 2014, *Lancet Neurology* 13(9):904–912 (actigraphy and sleep diaries, Shuttle/ISS) | 4 | Sleep-measurement methods for `behavioral.sleep_duration` | Aggregate | <https://pmc.ncbi.nlm.nih.gov/articles/PMC4188436/> (PMC4188436) | S |
| — | Nasrini et al. 2020, *Front. Physiol.*, DOI 10.3389/fphys.2020.00394 (Cognition battery in HERA) | 4 | Named instrument for `behavioral.self_report_score`-style data | Aggregate | <https://www.frontiersin.org/article/10.3389/fphys.2020.00394> | S |

**Gap:** no public individual sleep or mood series found. HERA standard measures are the best lead. The open question is
whether the data downloads publicly or needs a request.

## 5. How to acquire (applies to every source)

1. Write a download script in `backend/scripts/` (or `data/` if the team creates it). Raw files are not committed until
   redistribution rights are confirmed. Record the URL, retrieval time (UTC), SHA-256, licence and version or release.
2. Put each download in its own empty directory and treat it as untrusted. Parse it with a reader written for that format.
3. Before mapping, write a source entry in NASA_SOURCES.md that lists the verified field names and units.
4. Map to observations with `data_origin=measured` and `source_ref` set to an accession, DOI or URL. Environmental data waits
   for the P-2 decision. Animal data needs its own population and subject namespace.
5. Run `medvital.analysis.analyze(..., registry=build_registry())`. Rejections show up in `report.excluded`, and coverage and
   gaps show up per series.

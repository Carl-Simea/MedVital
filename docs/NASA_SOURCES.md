# NASA Sources

**Status (research pass 1, 2026-11-14, ~08:30–09:30 ET):** sources below were read live from their primary hosts. **No dataset has been
downloaded to disk, ingested, or used by MEDVITAL**; all data in the running system is still *simulated*. Everything marked
**VERIFIED** was observed in a response during this pass; **NOT VERIFIED** means it came only from a search-result summary or memory
and must be read at source before use. Nothing here is a scientific result.

Origin labels follow `CLAUDE.md` rule 2: *measured*, *simulated*, *modeled*.

---

## 1. NASA DONKI (space weather) — via NASA Open APIs

| Field | Entry |
|---|---|
| Name | Space Weather Database Of Notifications, Knowledge, Information (DONKI) |
| Source URLs | Catalog/docs: <https://api.nasa.gov/> (content loaded from <https://api.nasa.gov/assets/json/apis.json>); event viewer links in responses are under <https://ccmc.gsfc.nasa.gov/DONKI/> |
| Research purpose | Environmental space-weather *context* for the Radiation module (event timeline, hazard flags). **Not** an astronaut dose source. |
| Origin | External *measured/analysed* space-weather records: the catalog describes DONKI as "daily interpretations of space weather observations, analysis, models, forecasts, and notifications" by the Space Weather Research Center — i.e. a mix of observation-derived events, forecaster analysis and model output. Treat as **environmental event data**, never as individual exposure. |
| Auth & rate limits | VERIFIED (docs): no auth needed to explore; a free key from api.data.gov raises limits. Default 1,000 requests/hour per key. `DEMO_KEY`: 30/hour and 50/day per IP (documented). **Observed discrepancy:** live responses with `DEMO_KEY` carried `X-RateLimit-Limit: 10`, and 10 requests exhausted the quota (`Remaining: 0`). Plan for a real key supplied by the team; do not commit it. |
| Endpoints (VERIFIED in docs) | `GET https://api.nasa.gov/DONKI/{CME, CMEAnalysis, GST, IPS, FLR, SEP, MPC, RBE, HSS, WSAEnlilSimulations, notifications}`; common params `startDate`/`endDate` (`yyyy-MM-dd`, default last 30 days; WSA-Enlil 7 days). `notifications` also takes `type` = all, FLR, SEP, CME, IPS, MPC, GST, RBE, report; range limited to 30 days. `CMEAnalysis` params: `mostAccurateOnly`, `completeEntryOnly`, `speed`, `halfAngle`, `catalog` (ALL, SWRC_CATALOG, JANG_ET_AL_CATALOG), `keyword`. `IPS` params: `location`, `catalog`. |
| Live checks (this pass) | `SEP` 2024-05-10..14 → HTTP 200, 12 records. `CMEAnalysis` 2024-05-10..12 → HTTP 200, 13 records. `notifications` 2024-05-10..12 → HTTP 200, 38 records (FLR 12, CME 6, SEP 8, IPS 2, MPC 3, GST 7). **`FLR` returned HTTP 404 on two attempts** (2024-05-10..14 and 2024-05-09..11) while the other endpoints worked; cause not determined (quota was also exhausted by then). Flares were reachable through `notifications?type=FLR`. |
| Variables (VERIFIED from live JSON) | **SEP:** `sepID, eventTime, instruments[{displayName}], link, linkedEvents[{activityID}], sentNotifications, submissionTime, versionId`. **CMEAnalysis:** `catalog, isMostAccurate, time21_5, latitude, longitude, halfAngle, speed, type, associatedCMEID, associatedCMEstartTime, associatedCMELink, featureCode, dataLevel, measurementTechnique, imageType, tilt, minorHalfWidth, speedMeasuredAtHeight, note, link, submissionTime, versionId`. **notifications:** `messageType, messageID, messageURL, messageIssueTime, messageBody` (free text). **FLR fields: NOT VERIFIED** (endpoint 404). |
| Units | **NOT VERIFIED.** Responses carry bare numbers (e.g. CME `speed`, `halfAngle`); the catalog text read does not state units. Confirm in the DONKI/CCMC documentation before use. |
| Timestamps | VERIFIED: UTC strings, minute precision, `Z` suffix (e.g. `2024-05-10T12:59Z`). |
| Collection methodology | Event entries created/updated by SWRC forecasters with linked events (e.g. an SEP lists linked flare `activityID`s); notifications include auto-generated messages (e.g. "Flare intensity has crossed the threshold of M5.0" — a NASA alert threshold, not a health threshold). |
| Population | None (space environment). |
| Time coverage | Not verified beyond the 2024-05 window queried. |
| Limitations | Reports events, **not dose absorbed by a person**; never derive astronaut dose from an event without a validated physical model. Sparse (minute-resolution event records). Records are versioned (`versionId`) and can be revised. Rate limits are tight for `DEMO_KEY`. |

## 2. NASA Open Science Data Repository (OSDR)

| Field | Entry |
|---|---|
| Name | NASA Open Science Data Repository |
| Source URLs | Portal <https://osdr.nasa.gov/>; API docs (VERIFIED) in the NASA API catalog <https://api.nasa.gov/assets/json/apis.json> ("Open Science Data Repository" entry); controlled-access process <https://www.nasa.gov/reference/osdr-tutorials-requesting-controlled-access-datasets/> (page read, HTTP 200) |
| API (VERIFIED, no key used) | Search `https://osdr.nasa.gov/osdr/data/search?term=…&ffield=organism&fvalue=Homo%20sapiens&type=cgene&size=…&from=…` (Elasticsearch-style JSON); Metadata `https://osdr.nasa.gov/osdr/data/osd/meta/{N}` (ISA-style JSON); Files `https://osdr.nasa.gov/osdr/data/osd/files/{N}` (file list with `restricted` flag; page size ≤ 25; download via `https://osdr.nasa.gov` + `remote_url`). |
| Research purpose | Identify real human spaceflight data usable for the four modules. |
| Key finding | OSDR's human spaceflight holdings I reviewed are **molecular** (blood/plasma transcriptomics, epigenomics, proteomics, microbiome, plus one complete-blood-count table). **I found no human bone-density, continuous heart-rate/ECG, blood-pressure, sleep or mood time series.** `term=bone` returned 9 studies (cell/gene-expression, e.g. stem-cell osteoblast differentiation OSD-546, astronaut blood OSD-903/943); `cardiovascular OR heart` returned 11 (cultured cardiac/vascular cells, ground unilateral lower-limb suspension OSD-540). Records tagged *Homo sapiens* (116 in this search) are mostly cultured cells or ground/irradiation studies, **not astronaut data**. |
| Access | VERIFIED: public per file for studies reviewed below (`restricted=false`). NASA's tutorial page states controlled-access studies show a "Request Access to Restricted Files" button and lock icons; a request needs an IRB document and agreement to a Data User Agreement, is reviewed by NASA, and multi-institution teams each file separately. Access control level differs per study. **Licence/terms of use for public files: NOT VERIFIED.** Controlled-access data is not obtainable within a two-day hackathon. |

### 2a. Studies inspected via metadata API (VERIFIED)

| Study | Title | Population / design | Variables & assay | Time coverage | Release | Notes |
|---|---|---|---|---|---|---|
| **OSD-569** | Whole Blood Measurements from the SpaceX Inspiration4 Mission (RNA-seq, epitranscriptome, WGS, clonal hematopoiesis, CBC) | 4 private astronauts (metadata: 4 sources, 81 samples); ~3-day LEO mission, Sept 2021 | Complete Blood Count (hematology analyser), long-read RNA-seq, WGS, targeted sequencing. Files include `LSDS-7_Complete_Blood_Count_CBC.upload_SUBMITTED.csv` and `…_TRANSFORMED.csv` (each <0.1 MB); 11 files, none restricted | Blood collected L-92, L-44, L-3 (pre-flight) and R+1, R+45, R+82, R+194 (post-flight) | 14-May-2024 | Only clinical-lab-style table found; CBC column names/units **not yet read** (files not downloaded). Publications: doi:10.1038/s41586-024-07639-y, 10.1038/s41467-024-48929-3, 10.1038/s41467-024-48806-z, 10.1093/pcmedi/pbae007 |
| **OSD-53** | Spaceflight Modulates Gene Expression in Astronauts | Astronauts, short-duration flight. Description says six astronauts; metadata lists 13 sources/samples — **discrepancy unresolved** | DNA microarray, 234 stress-response genes, whole blood | ~10 days pre-flight and 2–3 h after return | 15-Oct-2013 | doi:10.1038/npjmgrav.2016.39 |
| **OSD-903** | Longitudinal transcriptomic and epigenetic analysis in astronauts … [RNA-seq] | 2 astronauts, 6 samples | RNA-seq, whole blood | T0 two weeks pre-flight, T2 24 h post, T3 three months post | 30-Jul-2025 | doi:10.1038/s41598-025-13383-8; companion methylation study OSD-943 (title only seen) |

### 2b. Other human-related OSDR studies (title/project type only — metadata NOT inspected)
Astronaut-derived: OSD-174 (hair follicles, ISS), OSD-316 (IgM repertoire, long-term flight), OSD-359 (exhaled-breath proteome), OSD-481 and OSD-483 (blood lncRNA / plasma sEV small RNA), OSD-530 (JAXA cell-free RNA, six astronauts), OSD-570/571/574/630 (Inspiration4 PBMC, plasma, skin, stool), OSD-687 (Inspiration4 T-cell histones). Ground analogues: OSD-140 (Mars-520 confinement simulation, blood), OSD-195/540/946/942/198/51 (bed rest / limb suspension, skeletal muscle), OSD-542 (14-day confinement blood). Cell/tissue-chip flown studies (not astronaut data): OSD-258, 344, 811, 635 (cardiac/vascular cells), OSD-546, 867 (osteoblast / stem cells), others.

### 2c. Limitations
Origin: *measured* (laboratory assays on real crew samples), but **sparse, tiny-N, molecular**. Does not support continuous monitoring or longitudinal bone/cardio/behavioural indicators. Per-subject identifiers/clinical context may be controlled. Whether any study provides individual-level (not aggregated) CBC values: NOT VERIFIED.

## 3. Curiosity RAD (Mars Science Laboratory Radiation Assessment Detector)

| Field | Entry |
|---|---|
| Name | MSL Mars Radiation Assessment Detector RDR, `DATA_SET_ID = MSL-M-RAD-3-RDR-V1.0`, volume `MSLRAD_1002` |
| Source URL | <https://pds-ppi.igpp.ucla.edu/data/MSL-M-RAD-3-RDR-V1.0/> (VERIFIED: HTTP 200; dirs `CATALOG/ DATA/ DOCUMENT/ EXTRAS/ INDEX/`; files `AAREADME.TXT, CHECKSUMS.TXT, ERRATA.TXT, VOLDESC.CAT`). Docs: `CATALOG/RAD_RDR_DS.CAT`, `DOCUMENT/RAD_RDR_SIS.HTM/.PDF` |
| Research purpose | Real **environmental** radiation time series (Mars cruise + surface) for the Radiation module's environmental channel and a realistic data-format test. **Not a personal dosimeter and not human exposure.** |
| Origin | *Measured* instrument data, calibrated to physical units by the RAD team (SwRI). Level: CODMAC 3 / "NASA Level 1A" (calibrated reconstruction of raw telemetry; no higher-level dose-equivalent product was seen in what I read). |
| Time coverage | `START_TIME 2011-11-20T18:24:41` to `STOP_TIME 2026-03-22T18:01:11` (DS.CAT). Release 42 (2026-08-03) covers 2025-11-05..2026-03-22 (Sols 4710–4843); archive grows with each release. Cruise products are in `DATA/CRUISE/` (one file per Earth day); surface products in sol-range folders `SOL_00000_00089` … `SOL_04710_04843` (one file per sol). First listed cruise product is day-of-year 340 of 2011; not reconciled with the DS.CAT start time. |
| Format | PDS3. Each product = detached label `.LBL` + ASCII `.TXT`; column structures in `.FMT` files. Sample label (sol 1, `RAD_RDR_2012_220_02_25_0001_V00`) is ~128 KB, data file 9,898 records. Product holds repeated "observations", each possibly with: counters (L1/L2), histograms, **dosimetry**, and PHA (pulse-height) events. |
| Variables & units (VERIFIED) | `TOT_DOSE_B`, `TOT_DOSE_E` (total dose for detectors B and E): **microGray / hour**. Dosimetry LET arrays: **keV/µm** (energy deposit normalised by detector thickness), counts per bin; detector B thickness (µm) and B/E detector mass (g) given in the dosimetry section. Counters, histograms (stopping/penetrating/neutral), PHA events: units per `.FMT` files — **not individually checked**. |
| Collection methodology | Charged- and neutral-particle detector on the Curiosity rover; per-observation records decompressed from EDR telemetry (DS.CAT, SIS). Surface Mars environment (and cruise). |
| Population | None. |
| Limitations | Mars-environment radiation, shielded by rover/atmosphere; detector-level dose rates in µGy/h are **not** an astronaut's dose or dose equivalent; no human tissue weighting applied in the tables I read. Level 1A with non-trivial structure (hierarchical, long lines); needs a parser. `DOCUMENT/TIMING_ERRORS.TXT` exists — **not read**. Data/documents may be revised (see `ERRATA.TXT`). Files not downloaded; sizes of `.TXT` not measured. Licence/terms: NOT VERIFIED (PDS public archive). |

## 4. Spacesuit biomedical instrumentation and dosimeters (existing NASA equipment vs MEDVITAL concept)

Status key: **V** = read in a NASA primary source this pass; **S** = reported only by a search-result summary of a NASA document (source not opened) — treat as NOT VERIFIED.

| Item | Statement | Source | Status |
|---|---|---|---|
| ISS heart-rate monitoring | NASA describes heart-rate monitoring as a critical need for exploration missions; ISS uses "four separate systems" today, based on chest-strap and electrode sensors; these depend on uninterrupted skin contact and suffer drop-out and motion artefact in the suit or during exercise. NASA project sought a single robust biosensor. | [Miniature Biometric Sensor Project, NTRS 20150016028 (2015)](https://ntrs.nasa.gov/citations/20150016028) | V (abstract) |
| Personal dosimetry on ISS | Since 2020 SRAG collects time-resolved dosimetry for individual crew using **Crew Active Dosimeters**, in contrast to passive dosimetry that gives only cumulative mission dose. | [SRAG "How do we protect the astronauts from space radiation?"](https://srag.jsc.nasa.gov/SpaceRadiation/How/How.cfm) | V (excerpt) |
| Crew Personal Active Dosimeters (CPAD) | SRAG was *developing* CPADs on a commercial dosimeter base with real-time dose feedback and autonomous measurement/data transmission (2016 abstract; development status then, not current fielding). | [NTRS 20160010836](https://ntrs.nasa.gov/citations/20160010836) | V (abstract) |
| Advanced EMU sensors | An Advanced EMU was being developed/tested at JSC (2017 abstract; sensors not described in the abstract). | [Sensors and Systems for Spacesuits, NTRS 20170005909](https://ntrs.nasa.gov/citations/20170005909) | V (abstract only) |
| EMU biomedical system | ISS EMU provides chest-electrode ECG (Shuttle-era "Operational Bio-instrumentation System": three chest electrodes, signal conditioner); ECG/EVA telemetry to ground. | NASA mishap report and EVA material | S |
| EVA medical monitoring requirement | Metabolic rate (estimated), ECG, heart rate, suit pressure/CO₂, radiation exposure; heart rate, ECG and body temperature during contingency EVA. | [MEDB 6.1/6.2 EVA Medical Monitoring](https://nlsp.nasa.gov/explore/api/v1/getfiles3?id=IDP-LSDA_DOCUMENT-0000000000002705&type=lsda_document&alias=lsda); [NASA-STD-3001 technical brief: spacesuits](https://www.nasa.gov/wp-content/uploads/2025/09/ochmo-tb-050-spacesuits.pdf) | S |
| xEMU heart rate | xEMU briefing lists a wired COTS chest-strap heart-rate monitor; thermal-vac testing demonstrated xINFO Wi-Fi telemetry. | [NTRS 20220009207](https://ntrs.nasa.gov/citations/20220009207), [NTRS 20240000686](https://ntrs.nasa.gov/citations/20240000686) | S |

**Not researched yet / not claimed:** sensor models, accuracy, sampling rates, power budgets, radio technology, haptic actuators, suit placement, battery life. The MEDVITAL wearable (ECG/optical HR/temperature/dosimeter/haptic) is a **conceptual design, not existing NASA equipment**; no performance figure may be stated until sourced from component datasheets and NASA documents.

## 5. Candidates not verified this pass
- **LSAH / LSDA (astronaut health repositories):** a search result (a NASA JSC conference paper) indicates requests are access-controlled under Privacy Act/HIPAA-type constraints; **not opened or confirmed**. Not usable for the hackathon without a formal request.
- **NASA-STD-3001 (exposure limits, health standards):** exists per search results; **no limit or value has been read or copied**. Any threshold must be cited by revision and section before use (CLAUDE.md rule 3).
- NASA Open Data Portal (data.nasa.gov) and Space Apps 2026 challenge materials: not checked.

## 6. Research pass 2 (2026-11-14, 17:29–17:45 UTC): files opened and inspected

Files were downloaded to a scratch directory, checksummed and read. **Nothing is committed and nothing has been ingested.**
Licence and terms of use for public OSDR files: **still not found.**

### 6a. OSD-569: Inspiration4 complete blood count (**V**)

| Field | Entry |
|---|---|
| Population | **Human**: 4 private astronauts, C001–C004 (ISA `Organism = Homo sapiens`), 3-day LEO flight 2021-09-16..18. Weill Cornell IRB 21-05023569. Crew consented to data sharing (study description). |
| Origin | *measured*: Sysmex XN analyzer (Quest Diagnostics), 4 mL K2EDTA tubes. Raw instrument files: "Not Available". |
| Access | All 11 files have `restricted=false`. API <https://osdr.nasa.gov/osdr/data/osd/files/569>. Download `https://osdr.nasa.gov/geode-py/ws/studies/OSD-569/download?source=datamanager&file=<name>` |
| Files read | `LSDS-7_Complete_Blood_Count_CBC.upload_SUBMITTED.csv` (26,138 B, SHA-256 `10a878b009eb2ea11a13fe92ad698098858639e8ed02f5ee849431313b9457d3`); `LSDS-7_Complete_Blood_Count_CBC_TRANSFORMED.csv` (9,317 B, `32e4f9c97d3b636b5d5c2e72dab8c4d3319dee64c437508b092dad04603b2b8f`); ISA zip (123,512 B, `5b3c19c5079816b283125caf4009db8e39d48377d92763e9e61e86e3e1b4c159`) |
| SUBMITTED columns | `ANALYTE, VALUE, RANGE_MIN, RANGE_MAX, UNITS, TEST_TYPE, SUBJECT_ID, SEX, TEST_DATE`. 553 rows. |
| Variables and units | WBC, platelets: Thousand/uL. RBC: Million/uL. Hemoglobin, MCHC: g/dL. Hematocrit, RDW, differential percentages: %. Absolute differential counts: cells/uL. MCV, MPV: fL. MCH: pg. |
| Time | **Relative only**: L-92, L-44, L-3, R+1, R+45, R+82, R+194. No calendar dates. |
| Missingness | 19–20 analytes per draw. MCHC is in 24 of 28 draws, MCH in 26. Hemoglobin, hematocrit and RBC appear once each under a separate `(FEMALE)` analyte name. |
| Defects / cautions | The TRANSFORMED file labels hemoglobin `percent` (the SUBMITTED file says g/dL). `RANGE_MIN`/`RANGE_MAX` are the **lab's clinical reference intervals**: never use them as thresholds (rule 3). |

### 6b. OSD-804: Rodent Research-1 bone microCT (**V**)

| Field | Entry |
|---|---|
| Population | **Mouse, not human**: 40 female C57BL/6J, 16 weeks old. Groups basal, vivarium, ground control, flight (37 days on ISS, SpaceX-4, launched 2014-09-21). |
| Origin | *measured*: Bruker SkyScan 1272, 60 kV, voxels 3×3×3 or 4×4×4 µm, frame averaging 3, saline, manual segmentation (CTAn). Raw images: "Not Available". |
| Access | All 4 files have `restricted=false`. <https://osdr.nasa.gov/bio/repo/data/studies/OSD-804>. Released 2025-01-29. No publication DOI in the ISA file. |
| Files read | SUBMITTED xlsx (22,940 B, `2c47f8cf9a1cea2ea9e41c9b309eb756b2f282f61a0f2765f3e15b37df0cae5b`); TRANSFORMED csv (13,052 B, `499541f23b4c3afcd39762456d98cb3046e1f56467fdf8ec5987f684534ccf0c`); data dictionary (1,664 B, `48435279f43e902280ce22ccb7025226b90a396f61b46458ab1c0323528012b8`); ISA zip (254,504 B, `62269d2cca516af7f75843b836b77422b21921ee5183acdb17601815c49ad372`) |
| Variables | Cortical sites (femur, femoral neck): BA/TA, Ct.Th (mm), endosteal and periosteal perimeter (mm). Trabecular sites (distal femur, femoral head, vertebrae): BV/TV, Tb.Th and Tb.Sp (mm), Tb.N (1/mm), Conn.D (1/mm³), DA, Tb.Pf. 170 rows (animal × site). Uneven n for femoral head and neck. |
| Defects | TRANSFORMED gives the ratios BA/TA and BV/TV the units mm² and mm³; the original workbook gives no unit. **BMD and Cort.TMD are defined in the dictionary but absent from all data.** |
| Fit | Cannot populate `bone.areal_bmd`. Animal data must never use astronaut `subject_id`s. |

### 6c. NLSP / LSDA Standard Measures (**V**, metadata only)

Catalogue: <https://nlsp.nasa.gov/resources/standard-measures>. The legacy `explore/home/lsda_sm_hera` URL now loads an
empty JavaScript application. Records: `https://nlsp.nasa.gov/api/v1/data/lsda_experiment/{id}/full`.
There are 26 measures across HERA, ISS, NEK and :envihab. :envihab lists bone mineral density, tilt test and VO2max.

**Every record inspected says: "Data collection is ongoing. Available datasets are accessible via data request."**
Every record lists 0 related datasets. The data cannot be downloaded directly.

| Record | Status | Variables (verbatim) and schedule |
|---|---|---|
| HERA PANAS, DOI 10.83263/whe7-1e26 | V | Positive affect, Negative affect. 20 items. L-13, L-1, weekly in mission, R+1, R+13. |
| HERA GHQ, DOI 10.83263/j6g2-kj21 | V | Anxiety, Insomnia, Severe depression, Social dysfunction, Somatic symptoms. Same schedule. |
| ISS Actigraphy, DOI 10.83263/ct85-fz22 | V | Sleep time total, Time in bed, Sleep efficiency, Sleep onset latency, Wake after sleep onset, Awakenings number, Bedtime, Wake time. Actiwatch Spectrum, non-dominant wrist. |
| ISS Sleep Quality/Team, DOI 10.83263/cznc-8459 | V | Sleep quality and quantity, tiredness, sleepiness, stress, workload, team cohesion, group living, vehicle design. |
| ISS Cognition, DOI 10.83263/nsjh-ec07 | V | Cognition battery (PVT, N-back, DSST, BART, VOLT, and others), plus pre-test state items. |
| ISS Personality, DOI 10.83263/fe3k-4225 | V | Big-Five domains and facets. 120 items, preflight. |

No units or score ranges are given. Variable names and schedules may shape *simulated* designs only (rule 8).

## 7. Live acquisition through the MEDVITAL pipeline (2026-11-14, backend M3)

Run with `backend/scripts/acquire.py` into a scratch store and a scratch station database, using NASA's public
`DEMO_KEY`. The key was absent from every stored manifest and from the database (checked).

| Source | URL (key removed) | SHA-256 (prefix) | Size | Ingest result |
|---|---|---|---|---|
| DONKI SEP 2024-05-10..14 | `https://api.nasa.gov/DONKI/SEP?startDate=2024-05-10&endDate=2024-05-14` | `1c92899e7dc0724d` | 8,594 B | 12 `EnvironmentalEvent`s, 0 skipped (matches the 12 records seen in pass 1) |
| DONKI notifications 2024-05-10..12 | `https://api.nasa.gov/DONKI/notifications?startDate=2024-05-10&endDate=2024-05-12` | `c40fb041c3704f94` | 142,933 B | 38 events, 0 skipped (matches pass 1) |
| OSD-804 data dictionary | OSDR geode download URL | `48435279f43e9022` | 1,664 B | Artifact registered. The checksum equals the one recorded in pass 2, so the download is reproducible. |
| MSL RAD `AAREADME.TXT` | `https://pds-ppi.igpp.ucla.edu/data/MSL-M-RAD-3-RDR-V1.0/AAREADME.TXT` | `1fea5073924df190` | 11,753 B | Artifact registered (no parser) |

What is imported:
* **DONKI:** SEP, CMEAnalysis (without numeric fields, whose units are unverified) and notifications.
* **Not imported:** FLR, GST and the other DONKI types, whose fields are unverified; MSL RAD product parsing (`.FMT`
  not inspected); OSDR tables as records (no matching metric, or animal data).

Licence and terms of use for OSDR and PDS files: **still not verified**. Raw files therefore stay git-ignored under
`data/raw/`.

## Rules for adding a source
1. Record exact URL/DOI/accession, retrieval date, licence and any access agreement.
2. Confirm redistribution rights before committing files; prefer a download script + checksum.
3. Human-subject data: use the source's official process, never commit it, never mix with simulated profiles.
4. Ingested observations are `measured` with `source_ref` pointing at the row above, or `modeled` with `method`.
5. A needed limit/coefficient must be cited (document, revision, section) and injected as a reference object carrying that citation.

## Gaps blocking real-data use
* **No source found for human bone density, continuous heart rate/ECG, blood pressure, sleep or mood time series.** Modules 2–4 will rely on *simulated* data unless another primary source is found.
* DONKI: units of numeric fields, FLR endpoint failure, a real API key.
* OSD-569 CBC: columns and units resolved (§6a). Remaining: licence/terms of use; relative-only timepoints.
* Standard Measures (HERA/ISS/:envihab): data only via formal LSDA request (§6c).
* Curiosity RAD: per-product sizes, `.FMT` units, `TIMING_ERRORS`, and whether any dose-equivalent product exists elsewhere.
* No documented clinical or regulatory threshold has been sourced; none may be used.

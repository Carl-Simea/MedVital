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

## Rules for adding a source
1. Record exact URL/DOI/accession, retrieval date, licence and any access agreement.
2. Confirm redistribution rights before committing files; prefer a download script + checksum.
3. Human-subject data: use the source's official process, never commit it, never mix with simulated profiles.
4. Ingested observations are `measured` with `source_ref` pointing at the row above, or `modeled` with `method`.
5. A needed limit/coefficient must be cited (document, revision, section) and injected as a reference object carrying that citation.

## Gaps blocking real-data use
* **No source found for human bone density, continuous heart rate/ECG, blood pressure, sleep or mood time series.** Modules 2–4 will rely on *simulated* data unless another primary source is found.
* DONKI: units of numeric fields, FLR endpoint failure, a real API key.
* OSD-569 CBC: column names/units and per-subject availability.
* Curiosity RAD: per-product sizes, `.FMT` units, `TIMING_ERRORS`, and whether any dose-equivalent product exists elsewhere.
* No documented clinical or regulatory threshold has been sourced; none may be used.

# NASA sources

**Status: no NASA dataset is ingested, bundled or imitated in this repository.** Everything the
software shows is simulated (see `SCIENTIFIC_METHODOLOGY.md`). Test fixtures for the import
pipeline are synthetic and labelled as such.

Verification levels used below:

- **Read**: a page was opened and read on 2026-11-14.
- **Snippet**: seen only in a web-search summary; the page itself was not opened.
- **Unverified**: written from general knowledge; nothing was checked.

Do not cite a row as evidence beyond its verification level.

## Sources checked

### NASA Open Science Data Repository (OSDR)

- Page: https://science.nasa.gov/biological-physical/data/osdr (**Read**, page dated Oct 23, 2026).
- Says OSDR holds data from humans, animals, model organisms, tissue chips, plants and microbes,
  including biomedical and physiological data; it expanded from GeneLab in 2021 by integrating the
  Ames Life Sciences Data Archive (ALSDA); ALSDA is described as the official repository for
  **non-human** life-sciences data.
- Says OSDR data is available through S3 and a CLI on the AWS Registry of Open Data (a "getting
  started" page exists; **not read**).
- A "Data Repository Terms and Conditions" page exists
  (https://science.nasa.gov/reference/osdr-help-terms-and-conditions/, **not read**). **No license,
  reuse terms or citation rule has been read yet.** Read it before ingesting anything.
- Whether a given human dataset is public or controlled is **not stated** on the page read.
- **Snippet only**: a search summary reports a June 2024 release of human omics and clinical-assay
  data from the 2021 Inspiration4 mission, with programmatic access via "GLOpenAPI". Not
  confirmed by opening a page; those assays are not obviously our eight metrics.

### OSDR Environmental Data Application

- Page: https://visualization.osdr.nasa.gov/eda (**Read**; reached via a redirect from
  https://www.nasa.gov/reference/osdr-environmental-data).
- Covers ISS cabin and hardware telemetry for several spaceflight experiments (for example
  RR-1 to RR-28, APEX-03-1, APEX-03-2, APEX-04, VEG-01C): temperature, relative humidity, CO2 and a
  radiation view (GCR, SAA, total and accumulated dose). Raw and summary data are downloadable
  from a "Data Tables" tab.
- Units, time spans and terms are **not stated** on the page read.

### RadLab portal and data API (inside OSDR)

- Description comes from a **secondary** article dated 2024-03-03
  (https://astrobiology.com/2024/03/03/nasa-open-science-for-life-in-space-the-radlab-portal-radlab-data-api/,
  **Read**). The RadLab pages themselves were **not opened**.
- Described as one access point for ISS radiation telemetry from several agencies' databases, with
  a web interface (query, visualise, download) and a programmatic API. Named detector groups:
  DORELI (DOSTEL1, DOSTEL2, Lidal, REM), three Liulin-5 detectors, and RAD/REM/TEPC detectors from
  SRAG data.
- Two different RadLab URLs appear (`.../radlab/gui/data-overview/` in the article,
  `.../radlab/gui/overview/` on the OSDR page); neither has been confirmed.
- Quantities, **units**, time coverage, whether registration is needed, and RadLab terms are
  **not stated** anywhere read so far.
- Relevance: the only candidate found that could supply real values for a radiation dose-rate
  metric. Not yet mapped to `absorbed_dose_rate` (unit and meaning of "total dose rate" unknown).

### NASA Life Sciences Data Archive (LSDA) and astronaut health data

- **Snippet only**: a search summary points to an LSDA Data Request Form
  (https://lsda.jsc.nasa.gov/explore/lsdahome/datarequest) and says astronaut clinical and research
  data release is reviewed by NASA boards under privacy rules (Privacy Act, HIPAA), citing NASA papers
  from 2012 to 2016. The pages and papers were **not opened**; the process may have changed.
- Implication (unconfirmed): individual astronaut bone, heart-rate, blood-pressure, sleep or mood
  time series are **not openly downloadable**; access is by request and approval.

### NASA Space Apps Challenge 2026 (event rules)

- The official site (https://www.spaceappschallenge.org/2026/) **failed to load** here (TLS
  certificate error), so no challenge text, resources or rules were read.
- **Snippet only** (third-party news and event pages): the event runs Nov 14-15, 2026 and judging
  starts Nov 16. No clock time for the start was found, and nothing was found about rules for
  pre-existing work. **Read the official rules yourself** before relying on this.

## Candidates not yet checked (Unverified)

| Source | Possible relevance | Link to verify |
| --- | --- | --- |
| NASA Human Research Program (Human Research Roadmap) | Risks and research gaps for human spaceflight health; a map of questions, not a data source | https://humanresearchroadmap.nasa.gov |
| NASA Open Data Portal | General NASA open datasets | https://data.nasa.gov |
| NASA Space Radiation Laboratory (NSRL, Brookhaven) | Ground-based space-radiation research | search "NASA Space Radiation Laboratory" |
| NASA-STD-3001 (human spaceflight standards) | May define limits. Reading it is not a licence to copy limits into MEDVITAL (rule 6 below) | search "NASA-STD-3001" |

## Findings so far

- **Radiation** is the only module with a plausible open real-data path (ISS telemetry via OSDR
  RadLab / Environmental Data Application), pending verification of units, terms and access.
- **Bone, cardiovascular and behavioral** metrics: no open individual-level astronaut time series
  was found. These modules continue to run on simulated data. This is "not found so far", not a
  proof that none exists.

## Rules for adding a source

1. Open it. Record the exact title, URL, access date, license or terms of use, and whether
   registration or approval is needed.
2. Describe what the dataset contains in your own words. Do not paste text from it.
3. Write an import spec (`docs/ARCHITECTURE.md`, "Source import pipeline") mapping each field to a
   MEDVITAL metric, with the source unit. Conversions must be exact unit definitions.
4. Imported values get `provenance.origin = measured` and a `source_ref` pointing at the record.
5. Record the terms in the spec's `terms_note`. Do not import without it.
6. Thresholds or limits from a standard may be used only with the standard's exact citation,
   reviewed by a domain expert, and recorded in `DECISIONS.md`. Never paraphrase a limit from memory.

## Open questions

- Which RadLab or Environmental Data Application tables map to `absorbed_dose_rate`, in what units,
  and what are the reuse terms?
- Are the OSDR terms compatible with redistributing data in a hackathon submission?
- Does the event allow pre-existing code or data, and when may work begin? (Official rules.)
- Is there any open analogue-study dataset (bed rest, isolation) for bone, cardiovascular or
  behavioral measures?

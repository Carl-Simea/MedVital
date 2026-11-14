# NASA Sources

**Current status: no NASA dataset has been downloaded, ingested, or used in MEDVITAL.** All data in the running
system is *simulated* (see SCIENTIFIC_METHODOLOGY §1).

This file is the register of sources the team intends to evaluate. Entries are **candidates**. The names below are
known NASA programmes and repositories; the "verification" column is deliberately empty — **nobody has yet
confirmed the exact URL, licence, access terms, schema or suitability** for any of them. Do not cite an entry in
a result until its row is filled in and reviewed.

## Candidate sources (unverified)

| Candidate | Likely relevance | Expected access (to verify) | Verified? |
|---|---|---|---|
| NASA Open Science Data Repository (OSDR; formerly GeneLab / Ames Life Sciences Data Archive) | spaceflight biology and some human-relevant studies | public portal; per-study licences/terms | no |
| NASA Life Sciences Data Archive (LSDA) | historical human-research data | portal; **human subject data is generally access-controlled and requires a request** | no |
| Lifetime Surveillance of Astronaut Health (LSAH) | longitudinal astronaut health | **restricted; not open data** | no |
| NASA Human Research Program (HRP) — Human Research Roadmap | risk/gap descriptions for radiation, bone, cardiovascular, behavioral health | public documents | no |
| NASA-STD-3001 (Space Flight Human-System Standard) | official health/medical standards, including exposure limits | public standard; **check current revision** | no |
| Space Radiation Analysis Group / ISS dosimetry publications | radiation environment and dose context | publications / data requests | no |
| NASA Open Data Portal (data.nasa.gov) | miscellaneous open datasets | public | no |
| Space Apps 2026 challenge materials | scope and any provided datasets | challenge page | no |

## Rules for adding a source

1. Record the exact URL / DOI / accession, retrieval date, licence, and any access agreement.
2. Confirm redistribution rights **before** committing any file; prefer a download script plus a checksum over committing data.
3. Human-subject data: obtain it through the source's official process; do not commit it; follow the data-use agreement;
   never mix with simulated profiles.
4. Ingested observations must be `measured` (raw) with `source_ref` pointing at the row above, or `modeled` with `method`.
5. If a number (limit, coefficient, reference range) is needed, cite the exact document, revision and section here; implement it
   as an injected reference object carrying that citation (CLAUDE.md rule 3).

## Gaps blocking real-data use

* Which datasets contain per-subject, time-resolved observations matching our metric set — unknown.
* Whether any can be redistributed or used in a hackathon demo — unknown.
* Dosimetry quantities, units and conventions used by the sources vs our `mGy` / `mSv` daily metrics — unknown.
* Bone: DXA protocol, sites, devices and precision in the sources — unknown.

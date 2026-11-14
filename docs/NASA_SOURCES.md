# NASA sources

**Status: no NASA dataset is ingested, bundled or imitated in this repository.** Everything
the software shows is simulated (see `SCIENTIFIC_METHODOLOGY.md`).

This file lists *candidate* sources to investigate. The entries were written from general
knowledge on 2026-11-14 **without** browsing, downloading or reading the sources, so every row
below is **unverified**. Do not cite a row as evidence until someone has opened the source, read
its terms and recorded what it actually contains.

## Candidates

| Source | Possible relevance | Link to verify | Verified? |
| --- | --- | --- | --- |
| NASA Open Science Data Repository (OSDR) | Space-biology and life-science experiment data; may relate to radiation or bone biology in model organisms | https://osdr.nasa.gov | No |
| NASA Life Sciences Data Archive (LSDA) | Archived spaceflight life-science data. Human-subject data is likely access-controlled | https://lsda.jsc.nasa.gov | No |
| NASA Human Research Program (Human Research Roadmap) | Describes known risks and research gaps for human health in spaceflight; a map of questions, not a data source | https://humanresearchroadmap.nasa.gov | No |
| NASA Open Data Portal | General NASA open datasets; search for relevant health or radiation sets | https://data.nasa.gov | No |
| NASA Space Radiation Laboratory (NSRL, Brookhaven) | Ground-based space-radiation research; may publish results relevant to the Radiation module | https://www.nasa.gov (search "NSRL") | No |
| NASA-STD-3001 (human spaceflight health standards) | Published standards that may define limits. **Reading it is not a licence to copy limits into MEDVITAL**; see rule below | https://www.nasa.gov (search "NASA-STD-3001") | No |

## Findings so far

- Human individual-level data (bone density, heart rate, blood pressure, sleep, mood) from
  astronauts is, as far as we know, **not openly published at individual level** because of
  privacy. This is an assumption to confirm, not a finding. The Cardiovascular, Bone and
  Behavioral modules therefore run on simulated data.
- No source above has been confirmed to provide a ready-to-use, openly licensed time series for
  any of our eight base metrics.

## Rules for adding a source

1. Open it. Record the exact title, URL, access date, license or terms of use, and whether
   registration or approval is needed.
2. Describe what the dataset contains in your own words. Do not paste text from it.
3. Map each field to a MEDVITAL metric and unit; note any conversion.
4. Ingest only with `provenance.origin = measured` and a `source_ref` pointing at the record.
5. Mark the row **Verified: Yes** with the date and who checked.
6. Thresholds or limits from a standard may be used only with the standard's exact citation,
   reviewed by a domain expert, and recorded in `DECISIONS.md`. Never paraphrase a limit from memory.

## Open questions

- Which of these sources, if any, allow redistribution inside a hackathon submission?
- Is there any open dataset with astronaut-level or analogue (e.g. bed-rest, isolation study)
  time series for bone, cardiovascular or behavioral measures?
- Which radiation quantities are published in a form that maps to `absorbed_dose_rate`
  (units, detector, shielding context)?

# MEDVITAL Roadmap and Milestone Log

Canonical working branch: `feat/telemetry-pipeline` (local only; nothing is pushed without explicit approval).

| Milestone | Scope | Status |
|---|---|---|
| M0 | Consolidate the two checkouts, all tests green | **Done** |
| M1 | Scientific verification, modeling gap analysis, `PublishedReference` decision | **Done** |
| M1b | Five pure calculations with hand-worked tests | **Done** |
| M2 | Storage, measurement schedules, API contracts | **Done** |
| M3 | Complete ingestion and analysis pipeline (backend) | **Implemented, uncommitted, awaiting human review** |
| M4 | Deterministic non-clinical rule engine (D-021) and DONKI event replay | Planned. Starts only after M3 review |
| M5 | Auth0 identity and access | Planned |
| M6 | Cloudflare synchronization (Workers, D1, R2, Queues) (D-023) | Planned. Deployment needs approval |
| M7 | Gemini mission intelligence (D-022) | Planned |
| M8 | Astronaut, spacecraft and NASA ground-station interfaces | Planned |
| M9 | 3D anatomical explorer (D-024) | Deferred to here |
| M10 | Final testing and demonstration preparation | Planned |

Renumbered 2026-11-14 to the unified sponsor-integration plan. The earlier "M3 radiation/behavioral, M5 dashboard"
numbering is superseded. Its content is now spread across M3, M4 and M8.

Every entry below records: changes, files, tests run, results, assumptions, limitations, next steps.

---

## M0: Consolidation (2026-11-14)

**Starting state:**
- Two divergent git repositories.
- `MEDVITAL/` (branch `feat/telemetry-pipeline`) held uncommitted telemetry, SQLite, device and live-dashboard work.
- The nested clone `MEDVITAL/Medvital/` held the uncommitted analysis engine and research plan.

**Safeguards taken before any change:**
- Full `git bundle --all` of both repositories (both verified).
- Working-tree tarballs, which include the uncommitted files.
- Logs of status and history, with SHA256SUMS.
- All of the above stored in `Documents/MEDVITAL_backups/2026-11-14_pre-consolidation/`, outside both repos.
- Preservation branches `preserve/outer-pre-consolidation-2be7b4f` and `preserve/clone-pre-consolidation-d82b43b`.

**Changes (all new commits; no rewrite, amend, squash or force):**

| Commit | What |
|---|---|
| `ade66c2` | Outer folder's uncommitted work, committed exactly as found |
| `229ad32` | Clone's analysis engine and docs (on clone branch `feat/analysis-engine`) |
| `33eb7c1` | `--no-ff` merge of the clone branch. Overlap check: only `docs/DECISIONS.md` was changed on both sides; resolved by keeping D-016, D-017 and D-018 |
| `b5fe4cf` | Regenerated `openapi.json`; fixed ruff E501; analysis engine uses `quality`/`device_id` directly |

**Pre-existing commits:** `ee2ffbd`, `d82b43b` and `2be7b4f` are unchanged (same hashes and timestamps).

**Incident caught:** on Windows (case-insensitive), the local exclude pattern `Medvital/` also matched
`backend/medvital/`. Anchoring it to `/Medvital/` fixed this before anything was committed.

**Tests run on `b5fe4cf`:**
- pytest: 199 passed.
- ruff: clean.
- vitest: 41 passed.
- tsc: clean.
- vite build: OK.

**Not tested:** PostgreSQL. No server or Docker on this machine, and the repository is a skeleton. Repository contract tests
run against memory and SQLite.

---

## M1: Scientific verification (2026-11-14)

**Changes:**
- New `docs/MODELING_GAP_ANALYSIS.md`: review of 10 formulas, 13 unsourced assumptions (G-1 to G-13), domain coverage
  gaps, and source defects.
- DECISIONS D-019: `PublishedReference` with a `REF-` identifier. No fourth `DataOrigin`.
- NASA_SOURCES §6: pass-2 inspection of OSD-569, OSD-804 and the NLSP Standard Measures, with checksums.
- RESEARCH_ACQUISITION_PLAN: resolved rows updated.

**Sources opened this milestone:**

| Source | Result |
|---|---|
| Hand & Siengsukon 2025 (sleep efficiency, TIB dispute) | **Verified** |
| StatPearls MAP page | Blocked by a bot check. **Not verified** |
| GUM JCGM 100:2008 PDF | Fetched, but not parseable without a PDF tool. **Not verified**. The propagation formula is derived algebraically instead |

**Assumptions:** none added. Every unsourced quantity is listed as a gap with its allowed handling.

**Limitations:** the MAP, GUM and Iglewicz–Hoaglin citations remain unverified (G-7 to G-9).

**Tests:** docs only. No code changed.

**Next:** M1b.

---

## M1b — Five pure calculations (2026-11-14)

**Changes:** `core/stats.py` (`PercentChange`, `percent_change` with first-order uncertainty);
`modules/cardiovascular/calculations.py` (`cardiac_output`, `mean_arterial_pressure_estimate`);
`modules/behavioral/calculations.py` (`sleep_efficiency`); `modules/radiation/calculations.py`
(`dose_from_constant_rate`). Tests: new `tests/test_core_stats.py`; additions to `test_module_cardiovascular.py`,
`test_module_behavioral.py`, `test_module_radiation.py` (each still imports only its own module). Docs:
SCIENTIFIC_METHODOLOGY §10.
**Design rules applied:** explicit unit arguments without defaults; unsupported units rejected, never converted;
unknown uncertainty → `None`; Gy and Sv never converted into each other; no labels or cut-offs.
**Tests run:** pytest 229 passed (30 new); ruff clean. (No frontend change.)
**Assumptions:** F2 assumes independent inputs (conservative when same-scanner correlation exists); F4 is an uncited
approximation; F6 assumes a constant rate.
**Limitations:** functions are not yet called by module summaries or the API (needs stroke-volume, time-in-bed and
paired-BP metrics — M3); observations still carry no uncertainty field (M2).
**Next:** M2.

---

## M2 — Measurement schedules, storage and API contracts (2026-11-14)

**Changes:** `core/schedule.py` (schedule model, mission window, resolution to modeled planned times, coverage per data
origin); `db/repository.py` (`ScheduleRepository` protocol, in-memory implementation); `db/sqlite.py` (additive
`measurement_schedules` table with append-only triggers); `db/schema.sql` (PostgreSQL table design); `core/module_spec.py`
(`metric_definition` lookup); `schedules.py` (single write path: metric/context/supersedes validation, conflict handling);
`api/deps.py`, `api/routes.py` (5 schedule endpoints); `frontend/src/domain/schedule.ts` (type mirror only);
`docs/api/openapi.json` regenerated; docs: ARCHITECTURE §4, DATA_DICTIONARY, DECISIONS D-020.
**Tests run:** pytest **253 passed** (24 new in `tests/test_schedule.py`: model validation, hand-computed L±/R± resolution,
recurring schedules, phase boundaries, coverage per origin without imputation, context matching, memory + SQLite contract
incl. restart persistence and append-only triggers, API lifecycle and semantic rejections); ruff clean; vitest 41 passed;
tsc clean; vite build OK.
**Not tested:** PostgreSQL (no server/Docker here; the repository class is still a skeleton and `schema.sql` additions are
unexecuted design).
**Assumptions:** planned day = 24 h from the planned time (anchor time-of-day + whole-day offset); mission phases have
no `recovery` sub-phase yet.
**Limitations:** schedules are not in offline sync push/pull; no UI; observations still have no uncertainty field; the
analysis engine does not yet consume schedules for its coverage measure (it infers or is configured with intervals).
**Next (proposed):** M3 radiation and behavioral modelling — wire M1b calculations into summaries via new metrics
(time in bed with `tib_definition`, stroke volume, paired BP), environmental-radiation entity (P-2), optional observation
`uncertainty` field (schema version bump).

---

## M3: Backend and data-engineering foundation (2026-11-14). UNCOMMITTED, awaiting review

Commits `e50d775`, `1916e6f` and `1bfb073` (M3.1 to M3.3) were made before the "no commits" instruction. Everything
after them is in the working tree only.

**Changes:**
* Generic append-only document store and accepted-write audit.
* Record types: missions, references, environmental events, source artifacts, RETURN_NOW commands and status events,
  rule findings, AI explanations.
* Acquisition: checksummed downloads with manifests; DONKI parsers; OSDR and RAD acquisition.
* M1b calculations wired into the module summaries through three new metrics and the pairing helper.
* Non-clinical rule engine.
* Authorization policy with `jwt` mode failing closed.
* Station-to-station document push and pull.
* 20 new API endpoints (43 in total), including device assignments.
* Security fix D-032: write authorization and device ownership at every boundary, with 17 regression tests.
* Grok MCP server and `.mcp.json`.

Decisions D-021 to D-031.

**Documents:**
* BACKEND_ARCHITECTURE
* SECURITY
* RISK_ENGINE
* CLOUDFLARE_ARCHITECTURE
* GROK_REVIEW_REPORT
* BACKEND_TEST_REPORT
* updated DATA_DICTIONARY, SCIENTIFIC_METHODOLOGY and NASA_SOURCES

**Tests:**
* pytest: 370 passed
* ruff: clean
* Grok MCP: 23 passed
* frontend: 42 passed; tsc and build OK
* PostgreSQL: not run

**Blocked:**
* Grok reviews (no xAI credits)
* Auth0 validation (dependency approval)

**Next:** human review of M3, then commit and push to `friend/feat/foundation` once authorised. Note that a `friend`
remote does not exist yet. M4 follows the review.

# MEDVITAL Roadmap and Milestone Log

Canonical working branch: `feat/telemetry-pipeline` (local only; nothing is pushed without explicit approval).

| Milestone | Scope | Status |
|---|---|---|
| M0 | Consolidate the two checkouts, all tests green | **Done** |
| M1 | Scientific verification, modeling gap analysis, `PublishedReference` decision | **Done** |
| M1b | Five pure calculations with hand-worked tests | **Done** |
| M2 | Persist measurement schedules; storage and API contract tests | Next |
| M3 | Radiation and behavioral modelling | Planned |
| M4 | Mission engine (profiles, time model, four domains, reproducible scenarios) | Planned |
| M5 | Standard dashboard on top of the analysis engine | Planned |
| M6 | 3D anatomical explorer | **On hold** (decision 2026-11-14: foundation first) |
| M7 | Cloudflare | **On hold** (decision 2026-11-14) |
| M8 | Integration, 180-day demonstration | Planned |

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

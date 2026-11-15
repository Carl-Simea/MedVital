# CLAUDE.md — MEDVITAL

Offline-first astronaut health observation platform (NASA Space Apps 2026). Monorepo:
`backend/` (Python/FastAPI, incl. `medvital/hub/` = the spacecraft), `nasa/` (Flask NASA receiver),
`apps/` (Astronaut + Cloudflare web apps), `body-dashboard/` (3D body), `frontend/` (React, optional), `docs/`.
Run everything: `python start.py` at the repo root.
Read `docs/ARCHITECTURE.md` before structural changes and `docs/DECISIONS.md` before
reversing a decision.

## Non-negotiable rules

1. **Never fabricate NASA data or scientific findings.** No invented datasets, citations,
   URLs, statistics or "typical astronaut values". If a number needs a source and you
   have none, leave it out and record the gap in `docs/NASA_SOURCES.md`.
2. **Every value carries provenance** and is exactly one of `simulated`, `measured`,
   `modeled`. Never pool or average across origins. UI must show origin as text.
3. **No clinical thresholds, no diagnosis, no risk labels** ("normal", "abnormal", "at risk")
   in `modules/`. Metric definitions may carry physical-plausibility rules only (e.g. dose ≥ 0).
   The only alert logic is `backend/medvital/hub/rules.py` (D-033): every limit it uses lives in
   `hub/settings.py` with either a NASA citation or `source="demo"`.
4. **Scientific calculations are pure and separate from presentation.**
   `modules/<m>/calculations.py` takes arrays/numbers only: no `medvital` imports, no
   pydantic, no I/O. `service.py` adapts observations → `ModuleSummary`. React components
   never compute science.
5. **The four modules are independent.** A module imports only `medvital.core` and itself.
   Cross-module composition happens in `registry.py` only. `tests/test_architecture.py`
   enforces this.
6. **Offline-first.** Reads and writes must work with no network. Observations are
   immutable and append-only; corrections use `supersedes`. Never add last-writer-wins.
7. **Minimal dependencies.** Justify any new package in `docs/DECISIONS.md`.
8. **Simulated data is labelled and arbitrary.** Generator magnitudes are test signals,
   not science. Do not tune them to look realistic.

## Commands

Windows PowerShell (macOS/Linux: `.venv/bin/python`).

```powershell
python start.py --fresh                     # NASA receiver + spacecraft hub + apps, clean mission
.\.venv\Scripts\python.exe -m pytest backend nasa   # all Python tests (after start.py created .venv)
node --test body-dashboard/tests/*.mjs      # 3D body tests
```

```powershell
# backend (from backend/)
python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m uvicorn medvital.main:app --reload --port 8000
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe scripts\export_openapi.py        # regenerate docs/api/openapi.json

# frontend (from frontend/)
npm install; npm run dev; npm test; npm run typecheck; npm run build
```

## Conventions

* Backend: Python ≥ 3.11, type hints, Pydantic v2 models `frozen=True, extra="forbid"`,
  ruff (line length 110). New route or schema change ⇒ regenerate `docs/api/openapi.json`
  (a test fails otherwise) and update `frontend/src/domain/*` mirrors by hand.
* Adding a metric: define it in `modules/<m>/metrics.py` (canonical UCUM-style unit),
  add calculation + tests, update `docs/DATA_DICTIONARY.md` and
  `docs/SCIENTIFIC_METHODOLOGY.md`.
* Adding a module: new subpackage exposing `SPEC`, register in `registry.py`, add
  `ModuleId` in core + frontend `MODULES`, per-module tests, docs.
* Tests: each module has its own `test_module_<name>.py` that imports nothing from the other
  three. Calculation tests use hand-computed expected values.
* Frontend: strict TS; pure logic in `domain/` and `offline/`; components stay thin.
  IndexedDB multi-store changes happen in one transaction. Schema changes bump `DB_VERSION`
  and add a migration block (never edit old blocks).
* Do not commit `.env`, credentials or real personal health data. No real astronaut data
  belongs in this repo.

## Known gaps (see docs/DECISIONS.md "Open questions")

PostgreSQL repository is skeleton only · no auth · no offline computation of summaries ·
no real NASA data ingested · scientific review by domain experts not yet done.

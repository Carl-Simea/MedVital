# CLAUDE.md: MEDVITAL

Offline-first astronaut health observation platform for NASA Space Apps 2026. Research
prototype, not a medical device.

## Non-negotiable rules

1. **Never fabricate NASA data or scientific findings.** No invented datasets, citations,
   statistics, dose numbers or "findings". If a source is unverified, say so in
   `docs/NASA_SOURCES.md`.
2. **Provenance is mandatory.** Every observation is `simulated`, `measured` or `modeled`
   (`backend/medvital/core/provenance.py`). Never average or combine origins. `measured`
   requires a `source_ref`; `simulated` requires `method` + `seed`; `modeled` requires
   `method` + `derived_from`.
3. **No clinical thresholds, no diagnosis.** Do not add normal ranges, risk cut-offs, alert
   levels or "healthy/unhealthy" labels. `physical_min/max` on a metric are scale bounds only.
4. **Science stays out of presentation.** Calculations live in `backend/` (`core/stats.py`,
   `modules/*/calculations.py`). The frontend stores and displays; it never computes results.
5. **Modules are independent.** `modules/<name>/` may import `medvital.core` only: not other
   modules, not `api`, `db`, `sync`, `registry`. `modules/*/calculations.py` are pure numerics
   (no pydantic, no observation types). `tests/test_architecture.py` enforces this.
6. **Offline-first.** The browser works from IndexedDB; the network is an optimisation.
   Observations are immutable and idempotent by UUID.
7. **Minimal dependencies.** Ask before adding one. Pydantic settings, ORMs and state libraries
   were deliberately left out.
8. **Do not push, force-push, delete branches or rewrite history without explicit approval.**
   Never commit tokens or `.env` files.

## Commands

```powershell
cd backend;  .\.venv\Scripts\python -m pytest; .\.venv\Scripts\ruff check .
cd backend;  .\.venv\Scripts\uvicorn medvital.main:app --reload
cd backend;  .\.venv\Scripts\python scripts\export_contracts.py   # after changing HealthObservation
cd frontend; npm test; npm run typecheck; npm run build; npm run dev
```

## Where things go

| Task | Location |
| --- | --- |
| New metric | the module's `module.py` (`MetricSpec`), then `docs/DATA_DICTIONARY.md` |
| New calculation | the module's `calculations.py` + a test with hand-computed expected values |
| New health module | new `modules/<name>/` package, register in `registry.py`, extend `ModuleId`, `schema.sql` CHECK, frontend `types.ts`/`presentation.ts` |
| API change | `api/contracts.py`, `api/routes.py`, `tests/test_api.py`, `docs/ARCHITECTURE.md` |
| Schema change | `core/observation.py`, regenerate `contracts/`, update `frontend/src/domain/types.ts` |
| Decision or limitation | `docs/DECISIONS.md` |

## Testing expectations

Every calculation needs a test whose expected value is computed by hand, not by calling the
function under test. Every module must stay testable without importing any other module.

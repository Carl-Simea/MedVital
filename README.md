# MEDVITAL

Offline-first astronaut health observation platform. NASA Space Apps 2026 project.

> **Research prototype. Not a medical device.** MEDVITAL does not diagnose anything and applies
> no clinical thresholds. All data in this repository is **simulated**. No NASA dataset is
> bundled or imitated.

## What exists today

A runnable foundation, not a dashboard:

- **Four independent health modules**: Radiation, Bone health, Cardiovascular health, Behavioral health.
- **One shared observation schema** with mandatory **data provenance**: every value is labelled
  `simulated`, `measured` or `modeled`, and the three are never mixed in a calculation.
- **Seeded simulator** and four simulated astronaut profiles (parameters are illustrative, not NASA data).
- **FastAPI backend** (Pydantic v2, NumPy, SciPy, Pandas, scikit-learn) with a versioned HTTP contract.
- **Offline-first design**: IndexedDB store + outbox in the browser, idempotent push/pull sync.
- **PostgreSQL architecture** (schema + repository). The default store is in-memory; the
  PostgreSQL repository is an unverified skeleton (see `docs/DECISIONS.md`).
- **React + TypeScript + Tailwind** frontend shell. Pytest and Vitest suites.

## Repository layout

```
backend/     FastAPI app, health modules, scientific core, tests (pytest)
frontend/    React + TypeScript + Tailwind client, IndexedDB offline layer, tests (Vitest)
contracts/   Shared JSON contract (generated schema + example) used by both test suites
docs/        Architecture, methodology, data dictionary, sources, decisions
```

## Run it (Windows PowerShell)

Backend (Python 3.11+):

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
uvicorn medvital.main:app --reload        # http://127.0.0.1:8000/docs
```

Frontend (Node 20+):

```powershell
cd frontend
npm install
npm run dev                               # http://localhost:5173, proxies /api to port 8000
```

## Test it

```powershell
cd backend;  python -m pytest             # backend tests
cd frontend; npm test                     # frontend tests (Vitest)
cd frontend; npm run typecheck; npm run build
cd backend;  ruff check .
```

Regenerate the shared contract after changing the observation model:
`cd backend; python scripts/export_contracts.py` (a test fails if it is stale).

## Optional: PostgreSQL

```powershell
docker compose up -d postgres
pip install -e ".[postgres]"
$env:MEDVITAL_DATABASE_URL = "postgresql://medvital:medvital@localhost:5432/medvital"
uvicorn medvital.main:app --reload
```

This path has not been tested against a live database yet.

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): layers, module independence, sync design, API contract
- [docs/SCIENTIFIC_METHODOLOGY.md](docs/SCIENTIFIC_METHODOLOGY.md): what is computed, how, and what is not claimed
- [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md): every field and metric
- [docs/NASA_SOURCES.md](docs/NASA_SOURCES.md): candidate NASA sources (none ingested yet)
- [docs/DECISIONS.md](docs/DECISIONS.md): decisions, open questions and known limitations
- [CLAUDE.md](CLAUDE.md): rules for AI-assisted development in this repo

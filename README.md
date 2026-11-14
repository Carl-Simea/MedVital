# MEDVITAL

Offline-first astronaut health observation platform — NASA Space Apps 2026 project.

MEDVITAL records health observations across four independent modules —
**Radiation**, **Bone health**, **Cardiovascular health**, **Behavioral health** — and
keeps every value labelled by origin: **simulated**, **measured** or **modeled**.

> **Status: v0.1 foundation.** Schema, provenance, API contract, sync design, four module
> skeletons with documented calculations, simulated astronaut profiles, and test
> infrastructure. There is **no dashboard** and **no AI engine** yet.

## Read this first

* **No real data ships with this repository.** Every number in the running system today
  is *simulated* test signal with arbitrary magnitudes. None is derived from NASA data.
* MEDVITAL is **not a medical device**. It gives **no diagnosis**, **no medical advice**,
  and applies **no clinical thresholds**.
* NASA sources are catalogued in [docs/NASA_SOURCES.md](docs/NASA_SOURCES.md) as
  *candidates, unverified*. Nothing has been ingested.

## Stack

| Layer | Technology |
|---|---|
| Frontend | React 19, TypeScript, Tailwind CSS 4, Vite, Vitest |
| Offline | IndexedDB (raw API wrapper), outbox + cursor sync |
| Backend | Python, FastAPI, Pydantic v2 |
| Science | NumPy, SciPy, pandas, scikit-learn |
| Database | PostgreSQL (schema + architecture only; in-memory store runs today) |
| Tests | pytest (backend), Vitest + fake-indexeddb (frontend) |

## Quick start (Windows PowerShell)

Prerequisites: Python ≥ 3.11 and a current Node.js with npm (built and tested with Python 3.13 and Node 26).

**Backend** (terminal 1)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m uvicorn medvital.main:app --reload --port 8000
```

API docs: <http://localhost:8000/docs> · health: <http://localhost:8000/api/v1/health>

**Frontend** (terminal 2)

```powershell
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173> (Vite proxies `/api` to the backend on port 8000).

macOS/Linux: replace `.\.venv\Scripts\python.exe` with `.venv/bin/python`.

## Tests

```powershell
# backend
cd backend; .\.venv\Scripts\python.exe -m pytest
cd backend; .\.venv\Scripts\python.exe -m ruff check .

# frontend
cd frontend; npm test
cd frontend; npm run typecheck
```

After changing any API route or schema, regenerate the committed contract
(a test fails if it is stale):

```powershell
cd backend; .\.venv\Scripts\python.exe scripts\export_openapi.py
```

## Repository layout

```
backend/
  medvital/
    core/          shared schema, provenance, stats helpers, module contract, sync wire types
    modules/       radiation/ bone/ cardiovascular/ behavioral/  (independent; depend only on core)
    simulation/    simulated astronaut profiles + deterministic generator
    db/            repository protocol, in-memory store, PostgreSQL schema + skeleton
    api/           FastAPI routes (thin)
    registry.py    composition root: the only place all four modules are imported together
  scripts/         export_openapi.py
  tests/           pytest (per-module, architecture, API, contract)
frontend/
  src/domain/      types + validation (no React, no storage)
  src/offline/     IndexedDB schema, LocalStore, sync engine
  src/api/         HTTP transport
  src/components/  presentation
docs/              ARCHITECTURE, SCIENTIFIC_METHODOLOGY, DATA_DICTIONARY, NASA_SOURCES, DECISIONS, api/openapi.json
```

## Documentation

* [CLAUDE.md](CLAUDE.md) — rules and conventions for contributors and AI assistants
* [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
* [docs/SCIENTIFIC_METHODOLOGY.md](docs/SCIENTIFIC_METHODOLOGY.md)
* [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md)
* [docs/NASA_SOURCES.md](docs/NASA_SOURCES.md)
* [docs/DECISIONS.md](docs/DECISIONS.md)

# Decisions, open questions and known limitations

Format: ID, decision, reason, consequence. Newest decisions are appended.

## Decisions

**D-001. Monorepo with three top-level areas** (`backend/`, `frontend/`, `contracts/`).
One repository keeps the contract, both test suites and the docs in step. `contracts/` is shared
so neither side can drift silently.

**D-002. Provenance is part of the schema, not metadata.** Every observation has an `origin`
(`simulated`, `measured`, `modeled`) with required fields per origin, enforced by validators.
Summaries group by origin so the three are never mixed. Cost: slightly heavier payloads.

**D-003. Observations are immutable and identified by client-generated UUID.** This makes ingest
idempotent and offline sync conflict-free. Corrections are new observations, not edits.

**D-004. Only one write path (`/sync/push`).** There is no separate `POST /observations`. One
validation route means one behaviour to test. The simulate endpoint reuses the same ingest.

**D-005. Per-item validation on push.** One bad observation never blocks an offline client's
batch. Rejected items stay on the device with a reason (never silently dropped).

**D-006. Modules depend on `core` only, enforced by a test.** Each module is a `HealthModule`
(specs + `derive`). `registry.py` is the only file that imports all four.

**D-007. Calculations are pure and separate.** `modules/*/calculations.py` take numbers, return
numbers; no pydantic, no observation types, no web. The frontend never computes results.

**D-008. In-memory repository by default, PostgreSQL behind a protocol.** The app and all tests
run with no infrastructure. PostgreSQL is an optional extra (`psycopg`) selected by
`MEDVITAL_DATABASE_URL`. Docker Compose provides a local dev database.

**D-010. Derived metrics are computed on demand and are modeled-only.** Summaries return them
without persisting. Their ids are deterministic (UUIDv5 of method + inputs), so persisting them
later is idempotent. Method ids are versioned (`_v1`).

**D-012. No clinical thresholds, no diagnosis, anywhere.** `physical_min/max` are scale bounds
only. Any future threshold requires a verified citation and domain-expert review (see
`NASA_SOURCES.md` rule 6).

**D-013. Simulator assumes no spaceflight effect.** `drift_per_day` is 0 for all profiles so we
do not encode unverified claims. Parameter values are illustrative and documented as such.

**D-014. Minimal dependencies.** Backend: FastAPI, uvicorn, pydantic, numpy, scipy, pandas,
scikit-learn (+ pytest, httpx, ruff for dev; psycopg optional). Frontend: React, Tailwind v4 via
its Vite plugin, Vite, Vitest, Testing Library, jsdom, fake-indexeddb (test only). Deliberately
omitted: pydantic-settings (env var read directly), an ORM, a state library, an IndexedDB wrapper
(a thin ~150-line wrapper is clearer and testable), a router.

**D-015. Hand-written TypeScript types plus a shared contract.** Types in
`frontend/src/domain/types.ts` mirror the backend. A committed JSON Schema (freshness tested) and
an example object (validated by both suites) catch drift. Generating types from the schema is a
possible later step.

**D-016. Vite dev proxy instead of CORS.** `/api` is proxied to port 8000 in development.
Production deployment topology is undecided (D-017).

## Open questions

**D-009. PostgreSQL sync cursor under concurrent writers.** `server_seq` is assigned at insert,
but transactions can commit out of order, so a pull could skip a row that commits late. Options:
a transaction-snapshot based cursor, a short "settle" delay, or serialising writes. Not an issue
with the in-memory repository.

**D-011. Authentication and authorisation.** None exists. Required before any non-simulated or
personal data is accepted. Decide on identity model, device registration, and per-astronaut access.

**D-017. Deployment and hosting.** Static frontend plus API behind one origin, or separate
origins with CORS? Service worker / PWA install for true offline loading of the app shell is not
implemented yet (only data is offline today).

**D-018. Schema migrations.** `schema.sql` uses `CREATE TABLE IF NOT EXISTS`. A migration tool
(for example Alembic or plain SQL files) is needed before the schema changes.

**D-019. `derived_from` size.** A modeled value lists every input id (up to hundreds for a long
series). Consider storing a range reference instead.

**D-020. Wiring `baseline_z_scores` and `multivariate_outlier_scores`.** They exist and are
tested but no endpoint uses them. Decide, with a domain reviewer, whether and how to expose them
without implying clinical meaning.

**D-021. Real data and licensing.** See `NASA_SOURCES.md`. No source is verified.

## Known limitations

- The PostgreSQL repository (`db/postgres.py`) and `schema.sql` have **not** been run against a
  live database. Only static checks exist (`tests/test_db_layer.py`).
- No end-to-end test of browser plus server. Frontend sync is tested against a fake API client;
  backend sync is tested through the HTTP test client.
- No service worker, so the app shell itself does not load offline yet.
- No authentication (D-011).
- Metric definitions have had no domain-expert review.
- The in-memory repository loses data on restart.

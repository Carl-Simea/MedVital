# Architecture

## Goals

1. Four health modules that can be developed and tested in isolation.
2. Honest data: every value says whether it was simulated, measured or modeled.
3. Offline-first: the client is fully usable without a network and converges when one returns.
4. Scientific code separated from presentation and transport.

## Backend layers (dependencies point downward only)

```
api/  ->  ingest, registry, db, sync, simulated_profiles
importers/  ->  core, registry (never api, db, sync)
registry.py  ->  modules/*   (the only file that sees all four modules)
modules/<name>/  ->  core     (never other modules, api, db, sync)
db/  ->  core                 (never api or modules)
core/  ->  stdlib, pydantic, numpy, scipy, pandas, scikit-learn
```

`backend/tests/test_architecture.py` parses imports and fails the build if a rule is broken.

| Package | Responsibility |
| --- | --- |
| `core/observation.py` | The shared `HealthObservation` schema and `ModuleId` |
| `core/provenance.py` | `DataOrigin` and `Provenance` validation rules |
| `core/stats.py` | Generic statistics: series stats and trend (SciPy), baseline z-score, IsolationForest outlier score (scikit-learn), trapezoid integral |
| `core/frames.py` | Observations to pandas DataFrame |
| `core/simulation.py` | Seeded, reproducible simulator; always labelled `simulated` |
| `core/analysis.py` | Per `(metric, origin)` descriptive summaries |
| `core/module.py` | The `HealthModule` contract |
| `modules/<name>/calculations.py` | Pure numerics for that module (no pydantic, no observation types) |
| `modules/<name>/module.py` | Metric specs and the `derive` function that builds modeled observations |
| `registry.py` | Lists the modules; validates observations against metric specs |
| `ingest.py` | The single write path: validate, then store |
| `db/` | Repository protocol, in-memory implementation, PostgreSQL implementation, `schema.sql` |
| `sync/protocol.py` | Wire models for push/pull |
| `api/` | Thin HTTP layer |

### The HealthModule contract

A module supplies metric specs (`MetricSpec`), a `derive` function (base observations in,
modeled observations out) and optional simulation context. Simulation and summaries are provided
generically by `core`, so all four modules behave uniformly. Adding a module means adding one
package and one line in `registry.py`.

### Base vs derived metrics

A **base** metric (e.g. `heart_rate`) may be `simulated` or `measured`. A **derived** metric
(e.g. `mean_arterial_pressure`) is `modeled` only and carries `derived_from` ids of its inputs.
Derived values are computed on demand from stored base observations and are not persisted by the
summary endpoint. Their ids are deterministic (UUIDv5 of method + inputs), so storing them later
is idempotent.

## Provenance

| Origin | Meaning | Required fields |
| --- | --- | --- |
| `simulated` | Produced by MEDVITAL's simulator | `method`, `seed` |
| `measured` | Recorded by an instrument or taken from a cited dataset | `source_ref` |
| `modeled` | Computed from other observations | `method`, `derived_from` |

Summaries group by `(metric, origin)`. Derived values are computed per input origin, recorded in
`context.input_origin`. Simulated and measured values never feed the same calculation.

## Source import pipeline

`backend/medvital/importers/` turns an external table (CSV) into validated `measured`
observations. It depends only on `core` and `registry`. **No NASA data ships with it**; a source is
described by an `ImportSpec` that someone writes after reading that source's terms.

An `ImportSpec` (JSON, loaded with `load_spec`) holds:

| Field | Meaning |
| --- | --- |
| `source` | Producer: instrument or archive name |
| `source_ref` | Citation, dataset id or URL; becomes `provenance.source_ref` |
| `terms_note` | The source's reuse terms in the importer's own words (required, 10+ chars) |
| `astronaut_id` or `astronaut_id_column` | Exactly one: a constant id, or the column holding it |
| `time_column`, `assume_utc` | Naive timestamps are rejected unless `assume_utc` is set |
| `columns[]` | `column`, `module`, `metric`, `source_unit` for each mapped column |

Rules enforced by `validate_spec` and `import_frame`:

- Each mapped metric must exist in the registry and accept `measured` data (derived metrics do not).
- `source_unit` must equal the metric's unit or have an **exact** conversion in
  `importers/units.py` (unit definitions only; each has a hand-computed test). Otherwise: refused.
- Everything is read as text; bad cells are rejected one by one with a short reason, empty cells are
  counted and skipped, and the rest of the file still imports.
- Ids are UUIDv5 of `(source_ref, astronaut, observed_at, metric)`: re-importing the same file, or
  the same rows in another order, produces the same ids, so storing twice is harmless.
- Imported observations then go through the normal `ingest` path like any other write.

Status: library and tests only. There is no CLI or HTTP endpoint for importing yet (D-022).

## HTTP API contract (v1)

| Method and path | Purpose |
| --- | --- |
| `GET /api/v1/health` | Liveness, app version, observation schema version |
| `GET /api/v1/modules` | Modules, their metrics, units and allowed origins |
| `GET /api/v1/profiles` | Simulated astronaut profiles |
| `POST /api/v1/simulate` | Generate simulated (and derived) observations; `store: true` persists them |
| `GET /api/v1/observations` | Filter by `astronaut_id`, `module`, `metric`, `origin`, `limit` |
| `GET /api/v1/modules/{module}/summary?astronaut_id=` | Descriptive summary plus derived observations |
| `POST /api/v1/sync/push` | Upload a batch (max 500) from an offline client |
| `GET /api/v1/sync/pull?cursor=&limit=` | Download changes after a cursor |

`sync/push` is the only way clients write data. Interactive docs: `/docs` when the server runs.
The observation JSON Schema is committed at `contracts/observation.schema.json` and regenerated
from the Pydantic model; a test fails if it drifts.

## Offline-first synchronisation

### Why it is simple

Observations are **immutable and append-only**, identified by a **client-generated UUID**. That
removes update/update conflicts: a client can retry any request any number of times.

### Client (browser)

IndexedDB database `medvital`, version 1:

| Store | Key | Content |
| --- | --- | --- |
| `observations` | `id` | Every observation known locally, indexed by `astronaut_id` and `module` |
| `outbox` | `id` | Observations not yet confirmed by the server, status `pending` or `rejected` |
| `meta` | `key` | `sync_cursor`, `device_id` |

`record()` writes the observation and its outbox entry in **one transaction**, so nothing can be
stored without also being queued. The UI reads only from IndexedDB.

### Sync cycle (`frontend/src/offline/sync.ts`)

1. **Push**: send pending outbox entries in batches. For each batch the server answers
   `accepted`, `duplicates`, `rejected`. Accepted and duplicate ids leave the outbox. Rejected ids
   stay locally, flagged with the reason, and are not retried. **Local data is never deleted.**
2. **Pull**: request `GET /sync/pull?cursor=N`, validate each observation with a structural guard,
   store the valid ones, persist the new cursor, repeat while `has_more`.
3. A network failure rejects the whole run and leaves outbox and cursor untouched; the next
   attempt resumes safely.

### Server rules

- Same id, same content: `duplicate`, harmless.
- Same id, different content: `rejected` ("id already exists with different content").
- One malformed item is rejected alone; the rest of the batch is stored.
- Rejection reasons name fields and messages, never the submitted values.

### Cursor

`changes_since(cursor)` returns observations after a monotonically increasing server sequence
(list position in memory, `server_seq` in PostgreSQL). Known limitation for PostgreSQL under
concurrent writers: see `docs/DECISIONS.md` (D-009).

## Persistence

- Default: `InMemoryObservationRepository` (tests, local demo, data is lost on restart).
- `MEDVITAL_DATABASE_URL` set: `PostgresObservationRepository` using `db/schema.sql`
  (optional extra `psycopg`). **Not yet exercised against a live database.**

## Frontend

`src/domain` (types, guards, display text), `src/api` (typed client), `src/offline` (IndexedDB
store and sync), `src/components` and `src/App.tsx` (presentation). Types are hand-written and
guarded at trust boundaries; a contract test validates the shared example against both sides.
There is intentionally no dashboard yet.

## Security and privacy status

No authentication or authorisation exists yet, and no real personal data should ever be loaded.
Adding auth is required before any non-simulated data is accepted (D-011).

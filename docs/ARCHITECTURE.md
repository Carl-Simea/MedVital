# MEDVITAL Architecture

Status: v0.1 foundation. Statements marked **[not implemented]** are design, not code.

## 1. Goals and constraints

* Offline-first: the app must read and record observations with no network (spacecraft,
  remote analogues, flaky links) and reconcile later.
* Provenance-first: every value says whether it is simulated, measured or modeled.
* Four health modules that can be developed, tested and reasoned about independently.
* Scientific calculations separate from presentation.
* Descriptive only: no diagnosis, no clinical thresholds.

## 2. System overview

```
                 ┌───────────────────────── Browser (PWA-capable SPA) ─────────────────────────┐
                 │  components (presentation only)                                              │
                 │      │ reads                                                                 │
                 │  offline/LocalStore ── IndexedDB: observations · outbox · meta               │
                 │      │ syncOnce()                                                            │
                 │  api/HttpTransport                                                           │
                 └──────┼──────────────────────────────────────────────────────────────────────┘
                        │ HTTPS  /api/v1   (push: idempotent · pull: cursor)
                 ┌──────▼───────────────── FastAPI backend ────────────────────────────────────┐
                 │  api/routes  ──►  ingest (validate + append)  ──►  db/ObservationRepository │
                 │        │                                              │ memory | postgres    │
                 │        └──► registry ──► modules/{radiation,bone,cardiovascular,behavioral}  │
                 │                              each: metrics · calculations · service          │
                 │  core/: schema · provenance · stats · summary · sync wire types              │
                 │  simulation/: profiles + deterministic generator                             │
                 └──────────────────────────────────────────────────────────────────────────────┘
```

## 3. Backend layers (`backend/medvital`)

| Layer | Responsibility | May import |
|---|---|---|
| `core/` | `HealthObservation`, `Provenance`, `ModuleId`, `DataOrigin`, stats helpers, `ModuleSummary`, module/registry contract, sync wire types | stdlib, pydantic, numpy/scipy/pandas |
| `modules/<m>/` | metric definitions, **pure calculations**, observation→summary adapter, `SPEC` | `core`, itself |
| `registry.py` | composition root; builds the registry of all four modules | `core`, `modules` |
| `simulation/` | fixed simulated profiles; seeded generator | `core` |
| `db/` | repository protocol, in-memory store, PostgreSQL schema + skeleton | `core` |
| `ingest.py` | the single write path (semantic validation + idempotent append) | `core`, `db` |
| `api/` | HTTP routes, boundary-only models | everything above |

Module anatomy (`modules/<m>/`):

* `metrics.py` — `MetricDefinition`s: canonical unit, physical-plausibility flag, allowed context keys.
* `calculations.py` — pure functions over numbers/arrays. **No `medvital`, web, or I/O imports.**
* `service.py` — groups observations into series (never mixing origins) and calls calculations; returns `ModuleSummary`.
* `__init__.py` — exports `SPEC` (`HealthModuleSpec`).

Independence is enforced by `tests/test_architecture.py` (AST import checks): modules import only
`core`; `calculations.py` imports no `medvital`/web/IO; `core` imports no modules/api/db.

## 4. API contract (v1)

Machine-readable contract: [`docs/api/openapi.json`](api/openapi.json), generated from code
by `backend/scripts/export_openapi.py` and verified by a test. Interactive docs at `/docs`.

| Method & path | Purpose |
|---|---|
| `GET /api/v1/health` | liveness, version, repository type |
| `GET /api/v1/modules` | the four modules and their metric definitions |
| `GET /api/v1/modules/{module}/summary?subject_id=` | descriptive summary (stats + derived values + warnings + notice) |
| `GET /api/v1/profiles`, `GET /api/v1/profiles/{id}` | simulated astronaut profiles |
| `POST /api/v1/profiles/{id}/simulate` | generate deterministic simulated observations (`persist` optional) |
| `POST /api/v1/observations` | batch ingest (≤ 500) with per-item results |
| `GET /api/v1/observations` | query by subject, module, origin, time window |
| `POST /api/v1/sync/push` | offline outbox upload (≤ 500 mutations), idempotent |
| `GET /api/v1/sync/pull?cursor=&limit=` | server changes after a cursor |

Error semantics: structurally invalid body → `422` for the whole request; semantically
invalid or conflicting item → `200` with that item `rejected` and a reason. Unknown module → `422`.
No authentication in v0.1 (see DECISIONS D-013).

## 5. Offline synchronisation design

### 5.1 Data model choices that make sync simple
* Observations are **immutable and append-only**. A correction is a new observation with `supersedes`.
* Ids are **client-generated UUIDs**, so records can be created offline and retried safely.
* The server assigns a monotonic **`server_seq`** per stored observation; it is the pull cursor.
* Therefore the only possible conflict is *same id, different content* → rejected (never merged).

### 5.2 Client (`frontend/src/offline`)
* IndexedDB stores: `observations` (key `id`; `sync_state` pending|synced|rejected), `outbox` (key `mutation_id`;
  status pending|failed, attempts, last_error), `meta` (cursor, client id).
* `addLocalObservation` validates, then writes the record **and** outbox entry in one transaction.
* `syncOnce(store, transport)`: (1) push outbox in batches; (2) pull pages from the stored cursor, applying
  records and advancing the cursor in one transaction.
* Failure handling:
  * network error / 5xx → entries stay pending, attempts incremented, retry later; cursor untouched;
  * per-item `rejected` → entry quarantined (`failed`), never retried automatically;
  * batch `422` → push mutations one by one to isolate the poison record so it cannot block the queue.
* `navigator.onLine` is only a hint; sync outcome is the source of truth.

### 5.3 Server
* `ingest_observation`: registry validation (known metric, canonical unit, physical bounds, required/allowed
  context) → `repo.add` → `ACCEPTED` / `DUPLICATE` (identical content, safe retry) / `REJECTED` (invalid or conflict).
* Pull reads the head sequence **before** the page so rows inserted mid-request are never skipped; at worst a row
  is re-delivered, which is harmless because client upserts are keyed by id.

### 5.4 Known sync limits
* PostgreSQL identity values are assigned at insert, not commit: concurrent long transactions can make a lower
  `server_seq` visible after a higher one. Mitigation (design): one short transaction per push batch; clients
  tolerate re-pulls. A hardening pass (e.g. advisory lock or commit-order sequencing) is **[not implemented]**.
* The outbox reads/sorts in memory; fine for thousands of entries, revisit for much larger backlogs.
* Multi-tab coordination (two tabs syncing at once) is safe (idempotent) but not optimised **[not implemented]**.
* No service worker / app-shell caching yet **[not implemented]** — the *data* layer is offline-capable; the *page
  load* is not until a service worker is added.

## 6. PostgreSQL integration architecture

* Contract: `ObservationRepository` protocol (`db/repository.py`): `add`, `get`, `query`, `changes_since`, `head_seq`.
* `InMemoryObservationRepository` is the reference implementation and runs today.
* `db/schema.sql`: `observations` table (one row per observation; `provenance` and `context` as `jsonb`,
  `data_origin` denormalised for indexing/constraint, `server_seq` identity column, `fingerprint`), indexes, and a
  trigger forbidding `UPDATE`/`DELETE` (append-only). **It has not been executed against a live server** (none was
  available); treat as reviewed design.
* `db/postgres.py` is a skeleton that raises `NotImplementedError` with an implementation checklist; the shared
  repository contract tests (`tests/test_repository.py`) are parametrised so Postgres drops in as a fixture param.
* Selection: `MEDVITAL_REPOSITORY=memory|postgres`, `MEDVITAL_DATABASE_URL`. `docker-compose.yml` provides a local server.
* Migrations tooling (Alembic or similar) is deliberately deferred until the schema stabilises (DECISIONS D-006).

## 7. Frontend structure (`frontend/src`)

* `domain/` — types mirroring the backend schema, client-side validation, module descriptors. No React, no storage.
* `offline/` — IndexedDB schema/migrations, `LocalStore`, `syncOnce`, online-status hook.
* `api/` — `HttpTransport` implementing `SyncTransport`.
* `components/` — presentation only (`ProvenanceBadge`, `SyncStatus`). `App.tsx` is a shell, not the dashboard.
* Science is **not** computed in the frontend. Consequence: module summaries need the backend (see DECISIONS Q-1).

## 8. Testing strategy

| Area | Tool | What is verified |
|---|---|---|
| Schema/provenance | pytest | origin-specific rules, UTC normalisation, immutability, fingerprints |
| Each module | pytest (`test_module_*.py`) | hand-computed calculation values; origins/sites/instruments never pooled |
| Architecture | pytest AST | module independence; pure calculations |
| Simulation | pytest | determinism, all-simulated labelling, passes registry validation |
| Repository | pytest contract tests | idempotence, conflict, cursor ordering |
| API | pytest + TestClient | endpoints, per-item results, sync push/pull semantics |
| Contract | pytest | committed OpenAPI equals code |
| Offline store | Vitest + fake-indexeddb | atomic writes, persistence across reopen, FIFO, idempotent upserts |
| Sync engine | Vitest | offline→reconnect, rejection quarantine, poison isolation, 5xx, pagination |
| UI | Vitest + Testing Library | four modules, disclaimer, origin legend |

Not covered yet: real browsers (Playwright), real PostgreSQL, performance, accessibility audits.

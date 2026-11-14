# MEDVITAL Backend Architecture Report

Status: backend milestone M3, 2026-11-14, on branch `feat/telemetry-pipeline`. **All changes are uncommitted and awaiting
human review.**

Companion documents:
* [SECURITY.md](SECURITY.md)
* [RISK_ENGINE.md](RISK_ENGINE.md)
* [CLOUDFLARE_ARCHITECTURE.md](CLOUDFLARE_ARCHITECTURE.md)
* [BACKEND_TEST_REPORT.md](BACKEND_TEST_REPORT.md)
* [GROK_REVIEW_REPORT.md](GROK_REVIEW_REPORT.md)
* [DATA_DICTIONARY.md](DATA_DICTIONARY.md)
* [SCIENTIFIC_METHODOLOGY.md](SCIENTIFIC_METHODOLOGY.md)
* [NASA_SOURCES.md](NASA_SOURCES.md)
* [DECISIONS.md](DECISIONS.md) (D-016 to D-031)

## 1. Pipeline: what implements each stage

| Stage | Implementation | Status |
|---|---|---|
| Sources | Wearable simulator (`device/`); simulated profiles (`simulation/`); NASA DONKI, OSDR and MSL RAD acquisition (`acquisition/`, `scripts/acquire.py`) | Implemented. RAD and OSDR files are acquired but **not parsed** (§8) |
| Ingestion | `telemetry.py` (wearable events), `ingest.py` (API, sync, simulation), `acquisition/ingest.py` (DONKI), `records_service.py` (all other records) | Implemented and tested |
| Validation | Pydantic models with `extra="forbid"`; registry checks for metric, canonical unit, physical bounds and context; telemetry clock-skew guard; mission and crew checks; command transition rules; D-022 citation boundary | Implemented and tested |
| Normalization | Canonical units plus declared aliases for telemetry; UTC timestamps; deterministic ids (uuid5) for telemetry, events, artifacts and findings | Implemented |
| Provenance | `Provenance` (exactly measured, simulated or modeled); `SourceArtifact` manifests with checksum, URL and processing history; `PublishedReference` (`REF-…`); explicit marker fields on records | Implemented |
| Persistence | SQLite (authoritative per station) and an in-memory twin, append-only by trigger; PostgreSQL design only | Implemented. PostgreSQL deferred |
| Analysis | Four module summaries plus the cross-domain analysis engine (`analysis/`); paired derived values (`core/pairing.py`) | Implemented and tested |
| Non-clinical rules | `rules.py` (6 rules, D-021) | Implemented and tested |
| API | 43 endpoints (§5), contract in `docs/api/openapi.json` | Implemented and tested |
| Offline sync | Browser outbox and cursor sync (unchanged); station-to-station observation and document replication (`upstream.py`) | Implemented and tested |
| Cloud sync | Design only ([CLOUDFLARE_ARCHITECTURE.md](CLOUDFLARE_ARCHITECTURE.md)); the Worker implements the same contracts | **Not implemented** (no deployment authorised) |

## 2. Modules and dependency rules

```
core/            schema, provenance, records, reference, schedule, pairing, stats, frame, summary, sync, telemetry, module_spec
modules/<4>/     metrics · calculations (pure) · service          -> import only core (tested)
analysis/        calculations (pure) · engine · models           -> imports only core (tested)
db/              repository (protocols + memory), sqlite, postgres (skeleton), schema.sql
acquisition/     download (checksum/manifest), donki (parsers), ingest
authz.py         roles, permissions, scope (pure)
records_service  single write/read path for non-observation records + replication
rules.py         non-clinical rule engine (reads; never writes commands)
upstream.py      station -> upstream delivery; station <- source document pull
api/             routes.py (observations, sync, telemetry, schedules), records_routes.py (everything new)
```

`tests/test_architecture.py` and `tests/test_analysis_architecture.py` enforce module independence and pure
calculations. `test_rules.py` statically asserts that the rule engine imports no command function.

## 3. Three-station data contracts

| Station | Role | Local store | Contracts used |
|---|---|---|---|
| **Astronaut** | Wearable ingest, own records, local review flags | SQLite (authoritative) | `POST /telemetry` (device → gateway); `push_upstream` and `push_documents_upstream` → spacecraft |
| **Spacecraft** | Crew aggregation, mission records, DONKI ingest and replay, mission-level analysis and rules | SQLite (authoritative) | Receives `/sync/push` and `/sync/documents/push`; pushes to the ground or cloud mirror; **pulls** `/sync/documents/pull` from ground (RETURN_NOW) |
| **Ground** | Authorized mission access, history, findings, reports, human-issued commands | SQLite now; D1 mirror later (D-023) | Same endpoints, scoped by role (D-029) |

Topology and guarantees (D-026, D-030):
* **Direction.** Observations and records flow *up* by push. Commands and other ground-issued records flow *down* by
  pull.
* **Cursors.** Every link keeps its own persisted cursor: `<dest>`, `<dest>#documents`, `<source>#documents-pull`.
* **Idempotency.** Deterministic ids make retries duplicates, never doubles.
* **Refusals.** Refused items are kept locally and audited in `upstream_failures`, which is append-only.
* **Outages.** Leave cursors unchanged. Local monitoring never depends on a link.

Tested end to end with real FastAPI apps in `tests/test_three_station.py` and `tests/test_upstream.py`. Those tests cover
link-down with local writes continuing, full interruption with restart, lost replies, refusal audit, batch-422
isolation, auth refusal and protocol errors.

## 4. Storage and migrations

SQLite tables, all created with `IF NOT EXISTS`. The schema change is therefore **additive**, and an older gateway file
gains the new tables the next time it is opened. No existing table was altered.

| Table | Purpose | Mutability |
|---|---|---|
| `observations` | Health observations (payload JSON, indexed columns) | Append-only (triggers) |
| `rejected_events` | Rejection log for every channel (telemetry, api, sync, simulation) | Insert-only in code |
| `measurement_schedules` | Measurement plans (M2) | Append-only (triggers) |
| `upstream_cursors` | Per-destination delivery cursors | Updated; monotonic in code |
| `upstream_failures` | Upstream refusals | Append-only (triggers) |
| `documents` | Missions, references, environmental events, artifacts, commands, command events, findings, AI explanations | Append-only (triggers) |
| `write_audit` | Accepted-write audit (channel, client, device) | Append-only (triggers) |

Device ownership (`DeviceAssignment`, D-032) is stored as a document of kind `device_assignment`.

Compatibility rules (D-025):
* **Additive fields.** Optional fields with defaults keep `schema_version` 1.
* **Duplicate detection.** Duplicate vs conflict is decided by re-fingerprinting the *stored* payload with the current
  model. This fixed a demonstrated false-conflict bug.
* **Mixed versions.** Upstream payloads omit `None` fields so older stations still accept them.
* **Upgrade order.** Stations should be upgraded together.

PostgreSQL: `db/schema.sql` documents the observation and schedule tables, but it has never been run against a server.
The `documents`, `write_audit` and `upstream_*` tables are not yet in it.

Migration compatibility is tested in two places:
* `tests/test_migration.py` opens a database built with the **exact previous-release schema** (commit `1bfb073`),
  with data and a cursor, under the current code;
* `test_sqlite_retry_of_pre_upgrade_row_is_duplicate_not_conflict`.
`test_documents_persist_and_are_append_only` and the schedule and upstream restart tests cover persistence across
restart.

## 5. API reference (v1)

The machine-readable contract is `docs/api/openapi.json`; a test fails when it is stale.

| Area | Endpoints |
|---|---|
| System | `GET /health` |
| Modules | `GET /modules`, `GET /modules/{module}/summary` *(scoped)* |
| Observations | `POST /observations`, `GET /observations` *(scoped; restricted principals must name an allowed subject)* |
| Telemetry | `POST /telemetry`, `GET /telemetry/schema`, `GET /telemetry/rejections` (whole rejection log), `GET /live` |
| Profiles | `GET /profiles`, `GET /profiles/{id}`, `POST /profiles/{id}/simulate` |
| Schedules | `POST /schedules`, `GET /schedules`, `GET /schedules/{id}`, `GET /schedules/{id}/resolve`, `GET /schedules/{id}/coverage` |
| Missions | `POST /missions`, `GET /missions`, `GET /missions/{id}` |
| References | `POST /references`, `GET /references`, `GET /references/{id}` |
| Environment | `POST /environment/events`, `GET /environment/events` (time-ordered replay), `GET /sources/artifacts` |
| Analysis | `POST /analysis` (subject, optional module, metric and time window, plus `AnalysisConfig`) |
| Rules | `POST /rules/evaluate` (`persist` optional), `GET /rules/findings` |
| Commands | `POST /commands/return-now` (human only), `POST /commands/{id}/status`, `GET /commands`, `GET /commands/{id}` |
| AI | `POST /ai/explanations`, `GET /ai/explanations` |
| Audit | `GET /audit/writes`, `GET /audit/upstream-failures` |
| Devices | `POST /devices/assignments`, `GET /devices/assignments` (D-032) |
| Sync | `POST /sync/push`, `GET /sync/pull` (scoped), `POST /sync/documents/push` and `GET /sync/documents/pull` (station only) |

Error semantics are unchanged:
* a structurally invalid body returns 422;
* an item that is semantically invalid or conflicting returns 200 with `rejected` and a reason;
* scope or permission failures return 403;
* a missing record returns 404.

## 6. Data provenance

* **Observation origin.** Every observation carries `Provenance` with exactly one of measured, simulated or modeled,
  plus origin-specific required fields. The full chain is source → `SourceArtifact` (URL with the key removed, SHA-256,
  size, retrieval time, method, processing steps) → record `source_artifact_id` and `provenance.source_ref`.
* **Original files are never modified.** They are stored at `data/raw/<sha256>/<filename>` (git-ignored). Ingest
  re-verifies the checksum and refuses a file that has been tampered with.
* **Derived values** are always `modeled`. They name their method (with a version), input metric, input origin, input
  count and context. Uncertainty is propagated only when it is known.
* **Published values** are `PublishedReference` records (`REF-…`), never observations, with a mandatory citation,
  source identifier, verification state, population and limitations.
* **AI and rule outputs** are separate record types with marker fields. They are never evidence and never
  observations.

## 7. Gemini preparation (M7)

There is no Gemini code yet. Prepared so far:
* the `AIExplanation` record, which requires citations and has `evidence`, `missing_information` and `uncertainty`
  sections plus `input_data_classes`;
* the storage path, which enforces D-022: cited observations must exist, and measured data must come from a listed
  public NASA source prefix;
* the `WRITE_AI_EXPLANATION` permission;
* the D-022 rule that Gemini never reads the database. A future caller must assemble evidence from authorized,
  validated reports and records.

## 8. Not implemented, partial or blocked (summary; full list in BACKEND_TEST_REPORT.md §4)

| Item | Status | Reason |
|---|---|---|
| MSL RAD parsing into `EnvironmentalEvent` | Not implemented | `.FMT` column structure not yet inspected; acquisition and manifest work |
| OSDR ingestion into records | Partial: acquisition only | No matching MEDVITAL metric (OSD-569 haematology); OSD-804 is a mouse study |
| Auth0 token validation | **Blocked** | Needs an approved JWT library (D-029) |
| Cloudflare Worker, D1, R2, Queues | Not implemented | Design only; deployment not authorised |
| Gemini calls | Not implemented | M7; boundary and storage prepared |
| Grok reviews | **Blocked** | The xAI team has no credits (GROK_REVIEW_REPORT.md) |
| PostgreSQL repository | Deferred | D-006 and D-023 |
| Frontend type mirrors for new schemas | Not done | This assignment excluded frontend work; flagged as drift |

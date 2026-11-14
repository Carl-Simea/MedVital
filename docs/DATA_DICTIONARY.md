# Data Dictionary (schema version 1)

Source of truth: `backend/medvital/core/schema.py` (+ `docs/api/openapi.json`). Frontend mirror:
`frontend/src/domain/observation.ts`. All timestamps are timezone-aware and normalised to UTC.

## HealthObservation

| Field | Type | Required | Notes |
|---|---|---|---|
| `schema_version` | int | default 1 | other values rejected |
| `id` | UUID | yes | **client-generated**; idempotency key |
| `subject_id` | string | yes | `^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$`; simulated subjects are `SIM-…` |
| `module` | enum | yes | `radiation` · `bone` · `cardiovascular` · `behavioral` |
| `metric` | string | yes | `<module>.<name>`; prefix must equal `module` |
| `value` | float | yes | finite only (no NaN/Inf) |
| `unit` | string | yes | must equal the metric's canonical unit |
| `observed_at` | datetime | yes | when the phenomenon occurred |
| `recorded_at` | datetime | yes | when the client recorded it |
| `context` | map<string,string> | no | ≤ 16 keys; key `^[a-z][a-z0-9_]*$`; value 1–128 chars; allowed keys defined per metric |
| `provenance` | Provenance | **yes** | see below |
| `supersedes` | UUID | no | id of the observation this corrects; never self |

Observations are immutable. Same `id` + identical content = duplicate (safe); same `id` + different content = conflict (rejected).

## Provenance

| Field | Type | Notes |
|---|---|---|
| `data_origin` | enum | `simulated` · `measured` · `modeled` |
| `source` | string | system / instrument / dataset family |
| `source_ref` | string? | resolvable reference (accession, DOI, URL, instrument id). **Required for measured** |
| `method` | string? | model/algorithm + version. **Required for modeled** |
| `generator_version`, `seed` | string?, int? | **Required for simulated**; forbidden for measured; `generator_version` forbidden for modeled |
| `derived_from` | UUID[] | input observation ids (modeled) |
| `license`, `retrieved_at`, `notes` | optional | licence of external data; retrieval time; free text (≤ 2000) |

## Metrics (v0.1)

| Metric | Unit (UCUM-style) | Context keys | Physical rule |
|---|---|---|---|
| `radiation.absorbed_dose_daily` | `mGy` | optional `instrument` | ≥ 0 |
| `radiation.dose_equivalent_daily` | `mSv` | optional `instrument` | ≥ 0 |
| `bone.areal_bmd` | `g/cm2` | optional `site`, `device` | ≥ 0 |
| `cardiovascular.resting_heart_rate` | `{beats}/min` | optional `device` | ≥ 0 |
| `cardiovascular.rr_interval` | `ms` | optional `session_id`, `device` | ≥ 0 |
| `cardiovascular.systolic_bp` | `mm[Hg]` | optional `device`, `posture` | ≥ 0 |
| `cardiovascular.diastolic_bp` | `mm[Hg]` | optional `device`, `posture` | ≥ 0 |
| `behavioral.sleep_duration` | `h` | optional `device` | ≥ 0 |
| `behavioral.self_report_score` | `{score}` | **required `instrument`** | none (scale unknown) |

"Physical rule" is plausibility (a dose cannot be negative), **not** a clinical threshold. The metric list is an initial set,
pending scientific review. Only canonical units are accepted; there is no unit conversion yet.

## TelemetryEvent (wearable → gateway, `POST /api/v1/telemetry`)

Contract fields (all required): `event_id`, `device_id`, `crew_id`, `timestamp` (timezone-aware), `domain`, `indicator`, `value` (finite), `unit`, `source`, `quality` (`valid|suspect|invalid`, provisional), `synthetic` (bool). Optional provenance extensions: `generator_version` + `seed` (required if `synthetic`), `source_ref` (required if not `synthetic`). Unknown fields are rejected. Example (synthetic):

```json
{"event_id":"EVT-20300101T120000-000001","device_id":"MEDVITAL-WEARABLE-001","crew_id":"CREW-001",
 "timestamp":"2030-01-01T12:00:00.000Z","domain":"cardiovascular","indicator":"heart_rate","value":61.3,
 "unit":"bpm","source":"simulated_sensor","quality":"valid","synthetic":true,
 "generator_version":"device-sim-0.1.0","seed":1}
```

Mapping to `HealthObservation`: `crew_id→subject_id`, `domain→module`, `domain.indicator→metric`, `timestamp→observed_at/recorded_at`, plus `device_id`, `quality`, provenance. The stored `id` is a UUIDv5 of `device_id|event_id`, so retries are idempotent. Response: one result per event (`accepted|duplicate|rejected`); rejected events go to the audit log (`GET /api/v1/telemetry/rejections`).

New wearable metrics: `cardiovascular.heart_rate` (`{beats}/min`; alias `bpm`), `radiation.dose_rate` (`uGy/h`; alias `µGy/h`), `bone.countermeasure_exercise_duration` (`min`). `behavioral.sleep_duration` (`h`) is reused.

`GET /api/v1/live`: newest reading per device and indicator with `quality`, `data_origin`, totals (stored, rejected) and the gateway's `server_time` (the dashboard computes reading age against it, not the browser clock).

## ModuleSummary (response of `GET /modules/{module}/summary`)

| Field | Notes |
|---|---|
| `module`, `subject_id`, `observation_count` | |
| `metric_summaries[]` | per (metric, origin, unit, context): `count`, `first/last_observed_at`, `mean`, `std` (null if n<2), `minimum`, `maximum` |
| `derived_values[]` | `name`, `description`, `value`, `unit`, `data_origin` (always `modeled`), `method`, `input_metric`, `input_origin`, `input_count`, `context` |
| `warnings[]` | computations skipped or caveated (insufficient points, duplicate days, …) |
| `notice` | fixed non-diagnostic statement |

Derived values: radiation `cumulative_dose_over_observed_days`, `mean_daily_dose`; bone `percent_change_from_first_observation`,
`trend_slope_per_day`; cardiovascular `rmssd`; behavioral `latest_deviation_from_own_baseline`.

## SimulatedAstronautProfile

`profile_id` (`SIM-A01…A04`), `label`, `age_years`, `planned_duration_days`, placeholder baselines
(`bone_bmd_baseline_g_cm2`, `resting_hr_baseline_bpm`, `rr_mean_ms`, `sleep_hours_baseline`, `self_report_baseline`),
`data_origin` (always `simulated`), `disclaimer`. Baselines are arbitrary signal centres, not physiological references.

## Sync wire types

* `SyncPushRequest { client_id, mutations[≤500]: { mutation_id, observation } }`
* `MutationResult { mutation_id, observation_id, status: accepted|duplicate|rejected, server_seq?, error? }`
* `SyncPushResponse { results[], server_cursor }`
* `SyncPullResponse { changes[]: { server_seq, observation }, next_cursor, has_more }` (`limit` ≤ 1000)

## IndexedDB (database `medvital`, version 1)

| Store | Key | Contents |
|---|---|---|
| `observations` | `id` | `{id, subject_id, module, observed_at, observation, sync_state: pending|synced|rejected, server_seq|null}`; indexes `by_subject_module`, `by_sync_state` |
| `outbox` | `mutation_id` | `{mutation_id, observation_id, observation, status: pending|failed, attempts, last_error, queued_at}` |
| `meta` | string | `sync_cursor` (number), `client_id` (string) |

## PostgreSQL (`backend/medvital/db/schema.sql`, not yet run against a server)

Table `observations`: `id uuid PK`, `server_seq bigint identity unique`, `schema_version`, `subject_id`, `module`, `metric`, `value`,
`unit`, `observed_at`, `recorded_at`, `received_at`, `context jsonb`, `data_origin` (denormalised), `provenance jsonb`,
`supersedes uuid`, `fingerprint text`; check constraints for module/metric namespace, finite values, origin consistency;
trigger blocks `UPDATE`/`DELETE`.

## Measurement schedule (`core/schedule.py`, schema version 1, M2)

A plan, not a measurement. Never contains values.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | Client-generated; immutable record |
| `subject_id`, `metric` | as observations | Metric must be registered; `context` keys must be allowed for that metric |
| `method` | text | e.g. `DXA`, `QCT`, `actigraphy`, `questionnaire` — different methods are separate schedules |
| `events[]` | `single` (`anchor` launch/return, `offset_days`, `window_days`) or `recurring` (start/end anchor+offset, `every_days`, `window_days`) | `L-13` = launch − 13 d; `R+1` = return + 1 d |
| `basis` | `protocol` \| `simulated` | `protocol` requires `source_ref` |
| `source`, `source_ref`, `notes`, `created_at`, `supersedes` | | Revisions via `supersedes` (same subject and metric) |

Resolved event: `planned_at`, `window_start` (inclusive), `window_end` (exclusive), `phase`
(`preflight` < launch ≤ `inflight` < return ≤ `postflight`), `time_origin = modeled`.

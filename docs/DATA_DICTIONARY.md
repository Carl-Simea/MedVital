# Data dictionary

Source of truth: `backend/medvital/core/observation.py`, `core/provenance.py`, and each module's
`module.py`. The JSON Schema is generated at `contracts/observation.schema.json`.

## HealthObservation

One value of one metric for one astronaut at one instant. Immutable; unknown fields are rejected.

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `schema_version` | integer | yes (default 1) | Must be `1` |
| `id` | UUID | yes | Client-generated; the idempotency key |
| `astronaut_id` | string | yes | `^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$`. Simulated profiles use `SIM-nnn` |
| `module` | enum | yes | `radiation`, `bone`, `cardiovascular`, `behavioral` |
| `metric` | string | yes | `^[a-z][a-z0-9_]{0,63}$`; must exist in the module's metric specs |
| `value` | number | yes | Finite (NaN and infinity rejected) |
| `unit` | string | yes | 1-32 chars; must equal the metric's declared unit |
| `observed_at` | datetime | yes | Timezone-aware; normalised to UTC; naive values rejected |
| `provenance` | object | yes | See below |
| `context` | map string to string | no | At most 16 entries; keys 1-64 chars, values at most 200. Short tags only, never free-text clinical notes |
| `device_id` | string | no | 1-64 chars; the device that first recorded it |

## Provenance

| Field | Type | Meaning |
| --- | --- | --- |
| `origin` | enum | `simulated`, `measured` or `modeled` |
| `source` | string | Producer: simulator name, instrument, or model name |
| `source_ref` | string or null | Citation, dataset id or URL. **Required for `measured`** |
| `method` | string or null | Algorithm and version. **Required for `simulated` and `modeled`** |
| `seed` | integer or null | RNG seed. **Required for `simulated`**; forbidden for `measured` |
| `derived_from` | list of UUID | Input observation ids. **Required (non-empty) for `modeled`**; forbidden for `simulated` and `measured` |

## Metrics

"Origins" lists which `provenance.origin` values the registry accepts for the metric.

### Radiation

| Metric | Unit | Origins | Notes |
| --- | --- | --- | --- |
| `absorbed_dose_rate` | `uGy/day` | simulated, measured | Scale bound: >= 0 |
| `cumulative_absorbed_dose` | `uGy` | modeled | Trapezoidal integral of dose rate; context `input_origin` |

### Bone health

| Metric | Unit | Origins | Notes |
| --- | --- | --- | --- |
| `bmd_areal` | `g/cm2` | simulated, measured | Context `site` names the skeleton site. Scale bound: >= 0. Simulated every 30 days |
| `bmd_percent_change_from_baseline` | `percent` | modeled | From the person's own first observation at the same `site` |

### Cardiovascular health

| Metric | Unit | Origins | Notes |
| --- | --- | --- | --- |
| `heart_rate` | `bpm` | simulated, measured | Scale bound: >= 0 |
| `systolic_bp` | `mmHg` | simulated, measured | Scale bound: >= 0 |
| `diastolic_bp` | `mmHg` | simulated, measured | Scale bound: >= 0 |
| `hrv_rmssd` | `ms` | simulated, measured | RMSSD of successive RR intervals. Accepted as supplied; not computed here |
| `mean_arterial_pressure` | `mmHg` | modeled | `DBP + (SBP - DBP)/3`, for SBP and DBP at the same `observed_at` |

### Behavioral health

| Metric | Unit | Origins | Notes |
| --- | --- | --- | --- |
| `sleep_duration` | `h` | simulated, measured | Scale bound: 0-24 |
| `self_reported_stress` | `score_0_10` | simulated, measured | Plain 0-10 placeholder scale. **Not a validated instrument** |
| `sleep_duration_7d_mean` | `h` | modeled | Mean of the last 7 samples |

Scale bounds (`physical_min` / `physical_max`) keep simulated values on a valid scale. They are
**not** clinical thresholds.

## Simulated profiles

`SIM-001` to `SIM-004` (`backend/medvital/simulated_profiles.py`). Each defines `mean` and `sd`
for every base metric and `drift_per_day = 0`. Values are illustrative and not from any dataset.
Profiles are not real people.

## Sync wire models

| Model | Fields |
| --- | --- |
| `SyncPushRequest` | `device_id`, `observations` (list of raw objects, max 500) |
| `SyncPushResponse` | `accepted` (ids), `duplicates` (ids), `rejected` (`{id, reason}`) |
| `SyncPullResponse` | `observations`, `next_cursor`, `has_more` |

## Client storage (IndexedDB `medvital` v1)

| Store | Key | Value |
| --- | --- | --- |
| `observations` | `id` | `HealthObservation`; indexes `astronaut_id`, `module` |
| `outbox` | `id` | `{id, observation, queued_at, status: pending or rejected, reason?}` |
| `meta` | `key` | `{key, value}`: `sync_cursor` (number), `device_id` (string) |

## PostgreSQL table `health_observations`

`server_seq` (identity, sync cursor), `id` (PK), `schema_version`, `astronaut_id`, `module`
(CHECK), `metric`, `value`, `unit`, `observed_at`, `origin` (CHECK), `provenance` (JSONB),
`context` (JSONB), `device_id`, `payload` (canonical JSON used to tell duplicates from conflicts),
`received_at`. Not yet verified against a live database.

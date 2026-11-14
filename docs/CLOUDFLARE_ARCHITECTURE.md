# Cloudflare Integration Design (not deployed)

Decision D-023: D1 is the cloud synchronization mirror, local SQLite stays authoritative at each station, R2 holds
large artifacts, and PostgreSQL is deferred.

**Nothing in this document has been implemented or deployed.** Product behaviour must be checked against current
Cloudflare documentation before M6 begins.

## Principles

1. **The cloud is never required for local operation.** Stations write to SQLite first and deliver afterwards
   (D-026, D-030).
2. **Keep the contracts.** The Worker implements the existing endpoints: `POST /api/v1/sync/push`,
   `GET /api/v1/sync/pull`, `POST /api/v1/sync/documents/push` and `GET /api/v1/sync/documents/pull`. A station
   cannot tell a Worker upstream from a MEDVITAL gateway upstream.
3. **No science in the Worker.** It performs structural validation and idempotent storage only. Analysis, rules and
   module summaries run in Python at the stations (rule 4).
4. **No last-writer-wins.** Same id with different content is rejected and audited, as everywhere else.

## Components

| Component | Responsibility | Notes |
|---|---|---|
| Worker (TypeScript) | Sync endpoints; Auth0 JWT validation at the edge (M5); per-item results | Validates against JSON Schema generated from `docs/api/openapi.json`. Must not compute derived values. |
| D1 | Tables `observations`, `documents`, `rejected_events`, `write_audit` and `upstream_failures`, mirroring the SQLite schema (§4 of BACKEND_ARCHITECTURE) | `server_seq` and `doc_seq` from autoincrement serve as pull cursors. Append-only enforced with triggers if D1 supports them, otherwise in Worker code (to verify). |
| R2 | Source archives (`data/raw/<sha256>/…`), generated reports, larger datasets | Keyed by SHA-256, so it is idempotent and tamper-evident. Manifests (`SourceArtifact`) stay in D1. |
| Queues | Asynchronous report generation and Gemini explanation jobs (M7), so ingest never waits | Only for work that is not on the sync path. |
| Durable Objects | **Not used** | No documented requirement. The cursor protocol already orders writes. Revisit only if live coordination between stations needs it. |

## Open items to verify before M6

* D1 support for triggers, `RETURNING` and batch limits, and how D1 behaves when a large push arrives.
* Worker request size and CPU limits, compared with `MAX_PUSH_BATCH = 500`.
* Account, plan and cost. Deployment requires explicit approval.
* GoDaddy DNS delegation to Cloudflare. Purchasing or changing the domain requires approval.

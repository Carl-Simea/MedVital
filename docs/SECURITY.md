# MEDVITAL Security

Scope: the backend as of M3, 2026-11-14. Decisions D-013, D-022, D-027 and D-029 apply.

## 1. Identity and authorization

| Role | Permissions (summary) | Scope |
|---|---|---|
| `astronaut` | Read their own observations, analysis, records and commands. Write their **own** observations, only with devices assigned to them. Sync their own outbox. Update the status of a command (acknowledge it) in their own name. **Cannot** create missions or device assignments. | Their own `subject_id` |
| `spacecraft_operator` | Read and write observations; read and write records; evaluate rules; sync; read audit; update command status. **Cannot issue RETURN_NOW.** | Crews of assigned missions |
| `ground_control` | Read observations and analysis; write records; evaluate rules; **issue and update RETURN_NOW**; write AI explanations; read audit; sync | Crews of assigned missions |
| `flight_surgeon` | Read observations and analysis; **issue and update RETURN_NOW**; write AI explanations | Crews of assigned missions |
| `local_station` | Everything (trusted gateway process on the station LAN) | Unrestricted |

The source of truth is `backend/medvital/authz.py`: pure functions, tested in `tests/test_authz_and_api.py`.

* **Scope enforcement happens at the API boundary.** It applies to:
  * `GET /observations` (restricted principals must name an allowed subject);
  * module summaries and `POST /analysis`;
  * mission, command and findings listings;
  * command status changes (the caller's mission scope, in their own name).
* **RETURN_NOW** requires:
  * a human principal;
  * permission to issue it;
  * assignment to the mission;
  * that the issuer named in the body is the caller.

  Non-human principals (AI, rules, services) are refused even if they have the role. The record model also rejects
  any `issuer_type` other than `human`.
* **Auth modes:**
  * `MEDVITAL_AUTH_MODE=local` is the default. Every request acts as `local_station`. This preserves offline local
    monitoring with no internet authentication.
  * `jwt` mode **refuses to start**. Auth0 RS256 validation (JWKS, `iss`, `aud`, `exp`, then mapping a role claim to
    `Role`) needs an approved library. It is deliberately not hand-written.
* **Write paths (fixed in D-032).** `POST /observations`, `/sync/push` and `/telemetry` check every item against the
  caller.
  * The subject must be in scope (astronauts: only themselves).
  * Any `device_id` must currently be assigned to that subject (`DeviceAssignment`, latest assignment wins).
  * Failures are per-item rejections in the rejection log. Client-supplied identifiers never override ownership.
* **Station-only:** persisting simulations, and `/sync/documents/push` and `/pull`.
* **Scoped or permissioned reads:** missions and device assignments, `/live`, `/sync/pull` (restricted principals must
  name an allowed subject), schedules, and the rejection log (`read:audit`).
* **AI explanations** must name the caller as `requested_by` and may cite only in-scope observations.
* **Regression tests:** `tests/test_write_authorization.py` (17).

### Planned Auth0 mapping (M5, not implemented)

| Auth0 item | MEDVITAL mapping |
|---|---|
| `sub` | `Principal.principal_id` |
| Custom claims: roles, `missions[]`, and for astronauts `subject_id` | Corresponding `Principal` fields |
| API audience | The station or cloud API |

Offline behaviour: the station caches the JWKS and accepts unexpired tokens offline. Login and token refresh need the
network, while LAN monitoring keeps working through `local_station` service credentials.

## 2. Secrets

* No secret has a default or is stored in code or config (`config.py`). `.env*` files are ignored by git.
* The NASA API key (`NASA_API_KEY`, default `DEMO_KEY`) is removed from every stored URL (`acquisition/download.py`,
  tested).
* The xAI key is read only from `XAI_API_KEY`. It is redacted from errors and never logged (`tools/grok_mcp`, tested).
  `.mcp.json` holds only a `${XAI_API_KEY}` placeholder.
* The upstream bearer token, if one is set, is held in memory only and never logged.

## 3. Data boundaries for AI

* **Gemini (D-022):** only simulated and public NASA data. `AIExplanation` storage rejects any citation of a measured
  observation unless its `source_ref` starts with a listed public NASA source prefix (`records_service.py`). This is
  tested both locally and through replication. Gemini has no database access.
* **Grok (D-027):** a development reviewer only. It is used through MCP for source code, documentation and simulated
  or public data. Measured-origin records and secret-like strings are refused before any network call. Its output is
  never stored as MEDVITAL data.

## 4. Integrity controls

* **Append-only storage,** enforced by SQLite triggers on observations, schedules, documents, write audit and upstream
  failures. Tests confirm that UPDATE and DELETE fail.
* **Idempotent writes:** content fingerprints and deterministic ids.
* **Conflicts are rejected and audited,** never merged.
* **Every rejection is logged:** api, sync, telemetry and simulation channels. Every accepted write is audited.
* **Downloads:** HTTPS only, with SHA-256 manifests. Files are never overwritten, and ingest refuses a tampered file.
* **Clock-skew guard** on telemetry: future timestamps are rejected.

## 5. Not covered yet

* Transport security: TLS termination, and CORS beyond the dev origin.
* Encryption at rest of SQLite files and IndexedDB (Q-5).
* Rate limiting on the API.
* Secrets management for a deployed cloud tier.
* A formal threat model.
* Penetration testing.

# Backend Test Report (M3, 2026-11-14)

All commands below were executed during this milestone against the uncommitted working tree on
`feat/telemetry-pipeline` (HEAD `1bfb073`). External services were mocked in the automated tests. The only API credit
spent was one failed Grok call (§3).

## 1. Results

| Suite | Command | Result |
|---|---|---|
| Backend (pytest) | `backend/.venv/Scripts/python.exe -m pytest` | **390 passed**, 0 failed. 1 warning: Starlette recommends `httpx2` (Q-9). |
| Security regression | `tests/test_write_authorization.py` (D-032) | **17 passed** |
| Migration from previous release | `tests/test_migration.py` (exact schema of commit `1bfb073`) | **2 passed** |
| Python type check | none configured (mypy would be a new dependency) | **Not run** |
| Lint and format | `ruff check .`; `ruff format --check` on all new M3 files | **Clean** / 20 files formatted |
| API contract | `test_contract_and_config.py` (OpenAPI regenerated and compared) | Passed |
| Architecture rules | `test_architecture.py`, `test_analysis_architecture.py` | Passed |
| Grok MCP server | `python -m unittest discover -s tools/grok_mcp/tests` | **23 passed** (mocked xAI) |
| Frontend (unchanged) | `npx vitest run` / `tsc --noEmit` / `npm run build` | **42 passed** / clean / built |
| PostgreSQL | none | **Not run**: no server or Docker on this machine; the repository is a skeleton |

Backend tests by file (390 in total). Since the previous count: `test_write_authorization` 17,
`test_migration` 2, `test_module_cardiovascular` +1 (HRV never from heart rate).
* `test_records` 35
* `test_schedule` 24
* `test_upstream` 22
* `test_telemetry` 22
* `test_schema` 21
* `test_module_radiation` 21
* `test_module_cardiovascular` 21
* `test_module_behavioral` 18
* `test_api` 18
* `test_analysis_engine` 18
* `test_device` 15
* `test_repository` 14
* `test_simulation` 12
* `test_rules` 11
* `test_module_bone` 10
* `test_architecture` 10
* `test_three_station` 9
* `test_acquisition` 9
* `test_uncertainty_and_compat` 8
* `test_registry_validation` 8
* `test_core_stats` 8
* `test_authz_and_api` 8
* `test_analysis_calculations` 8
* `test_gateway_pipeline` 7
* `test_contract_and_config` 6
* `test_rejection_audit` 4
* `test_analysis_architecture` 3

## 2. Coverage of the required test areas

| Required area | Where |
|---|---|
| Unit and integration | Module tests, `test_api`, `test_gateway_pipeline`, `test_three_station` |
| Schema migration | `test_uncertainty_and_compat` (pre-upgrade row retried as a duplicate); additive tables created on open (`test_records`, `test_schedule`) |
| API contract | `test_contract_and_config` |
| SQLite persistence | `test_repository`, `test_records`, `test_schedule`, `test_upstream` (restart), append-only trigger tests |
| Sync, idempotency, offline recovery | `test_upstream` (link down, restart, lost reply, 422 isolation, refusal, protocol error, partial batches, monotonic cursors); `test_three_station` (push and pull, outage, ordering, paging) |
| Provenance | `test_records` (markers, artifact id derivation, D-022); `test_acquisition` (checksums, redaction, processing history) |
| Unit validation | Registry tests; calculation unit tests; reference unit checks |
| Analysis calculations | `test_analysis_calculations`, `test_core_stats`, module wiring tests (hand-computed) |
| Environmental events | `test_records`, `test_acquisition`, `test_rules` |
| PublishedReference | `test_records` (validation, unit and metric checks, supersedes, never ingestible as an observation) |
| Risk rules | `test_rules` (every rule, determinism, no command path) |
| Security | `test_write_authorization` (every write boundary: subject, device and mission ownership, station-only endpoints, scoped reads, local and `jwt` modes); `test_authz_and_api` (role and scope matrix, RETURN_NOW rules); redaction tests |
| Error handling | Rejection-audit tests; per-item results; HTTP error mapping (`test_upstream`, Grok tests) |

## 3. External calls made during this milestone

| Call | Purpose | Result |
|---|---|---|
| NASA DONKI SEP and notifications (`DEMO_KEY`), OSDR file, PDS `AAREADME.TXT` | Live verification of acquisition | Succeeded (NASA_SOURCES §7). Public data, stored in scratch only. |
| xAI Responses API, 2 calls (checkpoint 1, then one small diagnostic) | Grok review | Both HTTP 403: no credits (GROK_REVIEW_REPORT.md) |
| Web pages (StatPearls, PMC, BIPM, docs.x.ai, Claude Code docs) | Source verification in M1 and the Grok setup | As recorded in the respective docs |

## 4. Outstanding limitations and unresolved assumptions

**Implemented and tested, with known limits**
* **Pairing** requires exact timestamp equality.
* **Dose-rate integration** uses a 2× median gap rule (an engineering default) and gives a lower bound.
* **SQLite** is safe for one gateway process per file. A race between two processes on the same file can raise an
  uncaught `IntegrityError`.
* **Document replication** permanently skips (but audits) a record whose parent originated at a third station and has
  not yet arrived.
* **Concurrent command status changes** at two stations are both kept, in feed order.
* **DONKI revisions** (a new `versionId`) appear as separate events.
* **The deviation rule** scans up to 100,000 observations. Listings default to 10,000 documents.

**Partially implemented**
* **OSDR:** acquisition and manifests only. Records are not ingested: OSD-569 is haematology with no metric, and
  OSD-804 is mouse data.
* **MSL RAD:** acquisition and manifests only. No product parser (`.FMT` not inspected).
* **Authorization:** policy, scope, write-path ownership (D-032) and fail-closed `jwt` mode exist. Auth0 token
  validation is blocked, so there is no authenticated mode to test beyond fail-closed behaviour.
* **Gemini:** storage and boundary are prepared. There are no calls (M7).
* **Cloudflare:** design only (CLOUDFLARE_ARCHITECTURE.md).

**Not implemented**
* Gemini integration, the Cloudflare Worker, D1, R2 and Queues, the PostgreSQL repository, and SQLite encryption at
  rest.
* API rate limiting, a TLS deployment, and the frontend type mirrors for the new schemas (frontend work was excluded).

**Blocked**
* Grok independent reviews (no xAI credits).
* Auth0 JWT validation (needs an approved JWT library).
* PostgreSQL integration tests (no server).

**Unresolved scientific assumptions**
* G-1 to G-6: bone-loss and recovery rates, countermeasure effects, scan precision, SPE magnitudes, dose conversion
  (all unsourced, none coded).
* G-7: MAP citation.
* G-8: GUM citation.
* G-9: Iglewicz–Hoaglin citation.
* G-10: definition of time in bed.
* G-11: mission time model for relative timepoints.
* G-12: HRV suitability checks.
* G-13: no verified `PublishedReference` exists yet.
* The 2× median gap rule for rate integration.
* Licence and terms for OSDR and PDS files.

# Grok Independent Review Report

Status: **BLOCKED.** No independent Grok review took place during backend M3 (2026-11-14).

## What happened

The review client sent checkpoint 1 (schema and persistence, 92,029 characters of source code, classified
`source_code`) through the project's Grok MCP server (`tools/grok_mcp/server.py`). This Claude Code session started
before the MCP server existed, so its tools were not loaded and the client spoke the MCP stdio protocol directly.
`XAI_API_KEY` was injected from the User environment into that one process and was never printed.

xAI answered **HTTP 403** `permission-denied`:

> "Your team … has either used all available credits or reached its monthly spending limit. To continue making API
> requests, please purchase more credits or raise your spending limit."

The integration works: the request authenticated and reached xAI's billing check. Buying credits is the owner's
decision, so the remaining checkpoints were not attempted, and the failed call was not retried. While diagnosing this,
the server was changed to include the redacted API error body in auth failures. Without it, the reason for the 403 was
invisible. The key is still redacted, and all 23 server tests pass.

## Substitute: self-review by Claude (NOT independent)

This is the implementing engineer reviewing their own work. It does **not** satisfy the requirement for independent
review. Each checkpoint should be re-run with Grok once credits are available, using the same client and the
questions recorded below.

| # | Checkpoint | What was checked | Findings (severity) | Resolution |
|---|---|---|---|---|
| 1 | Data schema and persistence | Append-only triggers, idempotency, re-fingerprinting, marker fields, restart persistence | (medium) Two *processes* writing the same SQLite file can race between "check" and "insert" and hit an uncaught `IntegrityError`; the in-process lock covers one process only. (low) `list_documents` truncates at a default limit of 10,000 without saying so. (low) The PostgreSQL design lacks the new tables. | Documented (BACKEND_TEST_REPORT §4). One gateway process per database file is the supported deployment. |
| 2 | Scientific calculations | Hand-computed tests; units; pairing; uncertainty semantics | (high, **fixed**) Dose-rate integration was 1000× too small: the code assumed nanosecond timestamps, but pandas stored microseconds. A test caught it, and elapsed time now comes from `days`. (medium) Exact-timestamp pairing misses devices that stamp two quantities milliseconds apart. (info) MAP, GUM and Iglewicz–Hoaglin citations are still unverified. | The fix is tested. The other items are documented as limitations and gaps G-7 to G-10. |
| 3 | Ingestion and provenance | Checksums, key redaction, tamper refusal, skip reporting, live DONKI and OSDR runs | (medium) A DONKI revision with a new `versionId` produces a new event alongside the old one, so a replay can show both versions. (info) RAD and OSDR are acquisition-only. | Documented. Both versions are kept deliberately (append-only); de-duplication for display is future work. |
| 4 | Sync and offline recovery | Cursor semantics, outages, restart, lost reply, 422 isolation, three-station flows | (medium) If a record's parent was created at a *third* station and has not arrived yet, the record is refused, audited and skipped for good, because the cursor moves past it. (low) Concurrent status changes to one command at two stations are both kept, in feed order. | Documented in D-030. Proposed fix: hold refused-for-missing-parent items for retry instead of skipping them. |
| 5 | Risk engine | Non-clinical outputs, determinism, no command path (static and dynamic tests) | (low) The deviation rule scans up to 100,000 observations per run. (low) Unavailability is not a finding, only refusals are. | Documented in RISK_ENGINE.md. |
| 6 | Security and API boundaries | Role and scope matrix, RETURN_NOW human and own-name rule, `jwt` mode fail-closed, secret redaction | (**high**, **fixed** in D-032) Write paths accepted observations under another subject's or device's identity; several reads were unscoped. (medium) `local` mode trusts the whole LAN. (info) Auth0 validation is blocked on a dependency. | Fixed and covered by 17 regression tests (`test_write_authorization.py`). Other items documented in SECURITY.md. |
| 7 | Final architecture | Dependency rules, contract drift test, frontend unaffected | (medium) The frontend TypeScript mirrors are not updated for the new schemas, which the assignment excluded. | Documented as drift to fix when frontend work is authorised. |

## How to run the real reviews later

1. Add credits for the xAI team, or raise its spending limit.
2. Restart Claude Code in `Documents/MEDVITAL` so the `grok_*` tools load, or reuse the stdio client.
3. Run checkpoints 1–7 with `grok_review_architecture` or `grok_review_code` and `data_classification=source_code`.
   Send only code, docs and test fixtures, never health data.
4. Record each finding in the table above, separately from the self-review rows, with severity, evidence, and an
   accept or disagree decision.

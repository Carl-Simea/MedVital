# Contributing to MEDVITAL

Four people, one repo, one weekend. These rules keep us from overwriting each other.
Read [CLAUDE.md](CLAUDE.md) first: its non-negotiable rules (no invented NASA data or
thresholds, mandatory provenance, no diagnosis) apply to every contributor and every AI
assistant.

## 1. Ownership (proposed — the team should confirm)

Each area has one owner. Anyone can propose changes to another area through a pull
request, but the owner reviews it.

| Person | Area | Primary paths |
|---|---|---|
| 1 — Data engineering | NASA research, ingestion, units, provenance, scientific docs | `docs/NASA_SOURCES.md`, `docs/SCIENTIFIC_METHODOLOGY.md`, `docs/DATA_DICTIONARY.md`, future `data/` scripts |
| 2 — Backend and AI | API, validation, baselines, the four modules, calculations, tests | `backend/` |
| 3 — Networking and Cloudflare | Wearable↔gateway↔ground sync, Workers/D1/R2/Queues/Durable Objects, Twilio | `frontend/src/offline/`, `frontend/src/api/`, future `cloud/` (not created yet) |
| 4 — Frontend | Dashboard, profiles, charts, alerts, connectivity and sync status | `frontend/src/components/`, `frontend/src/App.tsx` |

Shared files (`CLAUDE.md`, `README.md`, `docs/DECISIONS.md`, `docs/ARCHITECTURE.md`,
`docs/api/openapi.json`) need a heads-up in the team chat before you change them.

## 2. Contracts before code

Two things cut across everyone and must not change silently:

1. **The observation schema** (`backend/medvital/core/schema.py`, mirrored by hand in
   `frontend/src/domain/observation.ts`) and the sync wire types.
2. **The API contract** (`docs/api/openapi.json`, generated from the backend).

The briefing's telemetry fields differ from the current schema (see `docs/DECISIONS.md`,
P-1). Agree on that as a team and record the choice in `docs/DECISIONS.md` before anyone
builds against it.

If you change a route or schema:
1. Run `python scripts/export_openapi.py` in `backend/` and commit the regenerated file
   (a test fails if it is stale).
2. Update the TypeScript mirror in `frontend/src/domain/` by hand.
3. Tell the owners of the areas that consume it.

## 3. Git workflow

* Never commit directly to `main`. One branch per task, named `<area>/<short-description>`,
  for example `backend/radiation-baseline`, `frontend/sync-status`, `data/donki-ingest`.
* Keep branches short-lived (hours, not days) and pull often:
  ```bash
  git pull --rebase origin main
  ```
* Small commits with a clear message (what and why). Commit only files you changed.
* Open a pull request into `main`. At least one other person looks at it before merging.
  Owners review changes to their own area; for shared files, the person who owns the
  affected area reviews.
* Never force-push a shared branch. Never rewrite history that others have pulled.
* Resolve merge conflicts yourself; if you are unsure whose change wins, ask the other
  author rather than picking one.

## 4. Run and test before you push

Windows PowerShell (macOS/Linux: `.venv/bin/python`).

```powershell
# backend (from backend/)
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .

# frontend (from frontend/)
npm install
npm test
npm run typecheck
```

A pull request is ready when:
- [ ] Backend tests and `ruff` pass, and/or frontend tests and `typecheck` pass for the parts you touched.
- [ ] New logic has tests; calculation tests use hand-computed expected values.
- [ ] Every value is labelled simulated, measured or modeled, and nothing mixes origins.
- [ ] No clinical threshold, diagnosis, risk label or "typical astronaut value" was added without a cited source.
- [ ] Any new dependency is justified in `docs/DECISIONS.md`.
- [ ] Docs updated (`DATA_DICTIONARY`, `SCIENTIFIC_METHODOLOGY`, `NASA_SOURCES`) if you changed metrics, methods or sources.
- [ ] No secrets in the diff.

## 5. Science and data rules in practice

* **Cite or leave it out.** A number, limit or coefficient needs a primary NASA source
  recorded in `docs/NASA_SOURCES.md` (URL, revision, section). If you do not have one,
  do not write the number — note the gap instead.
* **Simulated is not real.** The generator's magnitudes are arbitrary test signals. Do not
  tune them to look realistic, and never present simulated values as astronaut data.
* **Environmental is not personal.** Space-weather events (DONKI) and Mars measurements
  (Curiosity RAD) describe the environment, not an astronaut's dose.
* **Respect the architecture.** The four modules import only `medvital.core`; pure
  calculations stay in `calculations.py`; the frontend never computes science.
  `backend/tests/test_architecture.py` enforces this.

## 6. Secrets and personal data

* Never commit API keys, tokens, `.env` files, or Twilio/Cloudflare/NASA credentials.
  `.gitignore` excludes `.env`; put placeholders in `.env.example` only.
* Never paste a real key into chat, an issue or a pull request, including into an AI
  assistant. If one leaks, rotate it immediately and tell the team.
* No real astronaut or personal health data belongs in this repository.

## 7. Working with Claude

* Each of us runs our own Claude session. Sessions do not share memory, so anything the
  team needs to know goes into the repo (`docs/`, `docs/DECISIONS.md`) or a pull
  request description, not just a chat.
* Pull the latest `main` before you start a session, and tell Claude which area you own
  and which branch you are on.
* Claude follows `CLAUDE.md`. If an instruction there is wrong for the task, change
  `CLAUDE.md` through a pull request so everyone's assistant stays consistent; do not
  just override it in one session.
* Review what Claude changes (`git diff`) before committing. You are responsible for
  what you push.

## 8. Event rules

The competition states that no project work may happen before Saturday 10 AM and that
every member must be registered. Confirm the organizers' interpretation before doing
project work early, and do not assume earlier preparation is allowed.

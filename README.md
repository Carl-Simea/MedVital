# MedVital

Astronaut health monitoring for the NASA Space Apps Challenge 2026 (New York City). A software-simulated wearable streams
each astronaut's heart rate, blood oxygen and radiation dose to the spacecraft. The spacecraft runs on Cloudflare: it
double-checks every reading, compares it with that astronaut's own pre-flight baseline, buzzes the wearable when
something is wrong, and syncs everything to NASA over the link to Earth without losing a record when the link drops.

It focuses on four astronaut health risks: radiation, bone, heart and behavioral health (sleep and stress).

## Run it

You need Python 3.11 or newer. From the repo root:

```sh
python start.py --fresh
```

The first run creates `.venv/` and installs the backend (a few minutes, once). Then it starts the NASA receiver and the
spacecraft hub and opens the apps in your browser:

| App | URL | Who it is |
|---|---|---|
| Astronaut 1 / Astronaut 2 | <http://localhost:8000/astronaut/?id=astro-1> | The wearable plus the astronaut's MedVital station. One tab per astronaut. |
| Spacecraft hub | <http://localhost:8000/cloudflare/> | The Cloudflare side: live traffic through the private network, crew overview, database, verification. |
| NASA | <http://localhost:5000/> | The flight surgeon's mission record. |
| 3D body | <http://localhost:8000/body/?astronaut=astro-1> | The rotatable 3D body, fed live from the spacecraft. |

`Ctrl+C` stops everything. Mission data stays in `runtime/`; `--fresh` starts a clean mission.

### Three laptops (the demo setup)

All three on the same Wi-Fi:

```sh
# NASA laptop
python start.py --role nasa --lan
# Spacecraft laptop
python start.py --role spacecraft --lan --nasa-url http://<NASA-laptop-IP>:5000
# Astronaut laptop: no install, just open http://<spacecraft-laptop-IP>:8000/astronaut/ (one tab per astronaut)
```

`start.py` prints each laptop's address. Add `--tunnel` on the spacecraft laptop to publish the hub through a
Cloudflare quick tunnel (needs [`cloudflared`](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)),
so a phone can open the astronaut page and really vibrate.

## Demo script

1. In each astronaut tab press **Put on wearable**. Each tab sends a burst every 5 seconds.
2. Astronaut 1: press **4 Spacewalk**. On the hub, press **Replay solar event** (a real NASA DONKI event from
   17 Sep 2024). Within one burst Astronaut 1's screen turns red: **RETURN NOW**, three long buzzes, repeating until
   they press *Heading back inside*.
3. Astronaut 2: press **5 Heart-rate spike**. After two bursts in a row confirm it, **CHECK VITALS** (two short buzzes).
   The same heart rate would not alert for Astronaut 1, whose baseline is lower: the system adapts to each person.
4. Press **G Sensor glitch**: the impossible reading is stored and flagged, but nothing buzzes.
   Press **T Fake device**: the private network blocks it (red cross on the hub diagram).
5. On the NASA screen press **Cut the link**. Keep going: the hub's outbox grows. **Restore the link**: it drains.
   The hub's **Verify** tab shows the counts on both sides match ("Nothing lost").
6. Type onboard test results (bone loss), ask MedVital a question, press **Write today's summary now**. All of it
   reaches NASA.

Keyboard on an astronaut tab: `1` normal, `2` sleep, `3` exercise, `4` spacewalk, `5` heart-rate spike, `6` solar event,
`G` glitch, `T` fake device. Demo clock: one burst = 30 minutes of mission time, so a mission day is 48 bursts (4 minutes).

## How it fits together

```
 Astronaut tabs (wearable sim)          Spacecraft hub  (backend/medvital/hub, port 8000)               NASA (nasa/, port 5000)
 ─────────────────────────────          ─────────────────────────────────────────────────               ───────────────────────
 burst every 5 s ───────────────► private network: device key check
 {astronautId, deviceKey, time,         ├─ double-check (plausible? glitch?)
  heartRate, spo2, state,               ├─ store: runtime/spacecraft.db ("D1") + observation store
  doseRate, totalDose}                  ├─ rules vs. personal baseline ─► alert code in the reply
 ◄──── alert code (vibration) ──────────┤  Workers AI words it, onboard agent checks the numbers
                                        ├─ DONKI space weather (live pull + replay)
 MedVital station ◄── /hub/astronauts ──┤
 question box   ───► onboard agent ─────┤
                                        └─ outbox ── batches of 50 ── link to Earth ──────────► POST /batch
                                                 ◄──────────────── {"saved": [ids]} ─────────── mission.db
```

| Team plan spot | Code |
|---|---|
| 1. Astronaut (wearable, MedVital station, hub screen) | `apps/astronaut/`, `apps/cloudflare/`, `body-dashboard/` (3D body) |
| 2. Spacecraft (Cloudflare hub, rules, AI, DONKI, onboard agent) | `backend/medvital/hub/` (plus the MEDVITAL observation platform in `backend/medvital/`) |
| 3. NASA (receiver, link switch, mission record) | `nasa/` (receiver), `spacecraft-sync/sync.js` (the same outbox sync written for a real Cloudflare Worker) |

Record format shared by the hub and NASA: `nasa/record_format.py` (`reading`, `alert`, `summary`, `lab`).

### Where the numbers come from

* Normal radiation: Curiosity RAD measured 0.64 mSv/day on the surface of Mars (Hassler et al., *Science*, 2014), so the
  simulator sends about 26.7 µSv/h.
* Limits: NASA-STD-3001 Vol. 1, 600 mSv career limit [V1 4030] and 250 mSv per solar particle event [V1 4031].
* The spacewalk dose budget, the heart-rate allowance above each astronaut's baseline, and the SpO2 drop are **demo
  settings**, labelled `source="demo"` in `backend/medvital/hub/settings.py`. They are not clinical values.
* Heart rate and blood oxygen are simulated around two made-up pre-flight baselines (`astro-1` resting 58 bpm,
  `astro-2` resting 72 bpm). MedVital is not a medical device and gives no diagnosis.

### Optional AI

Without any setup, alerts and summaries use rule-written text and the onboard agent answers with rules from the
astronaut's own data. To turn on the real models:

```sh
# Workers AI (Cloudflare) words alerts and daily summaries
export CLOUDFLARE_ACCOUNT_ID=...  CLOUDFLARE_API_TOKEN=...
# a local model answers the astronauts' questions (onboard agent), via Ollama
export MEDVITAL_OLLAMA_MODEL=gemma3
python start.py
```

The rules always fire first; AI only explains, and the onboard agent rejects any AI wording that changes a number.

## Tests

```sh
.venv/bin/python -m pytest backend nasa        # Windows: .venv\Scripts\python -m pytest backend nasa
node --test body-dashboard/tests/*.mjs
```

## Repository layout

```
start.py              one command: installs, starts NASA + the hub, opens the apps
apps/                 Astronaut and Cloudflare/hub web apps (plain HTML/JS, no build step)
backend/medvital/hub/ the spacecraft hub: bursts, rules, alerts, outbox sync, DONKI, AI, verification
backend/medvital/     MEDVITAL observation platform: provenance-labelled observations, four health modules
nasa/                 NASA receiver (Flask + SQLite) and the mission record screen
spacecraft-sync/      outbox -> NASA sync for a real Cloudflare Worker (same logic as the hub's Python port)
body-dashboard/       3D body dashboard (three.js, BodyParts3D anatomy)
frontend/             earlier React live view of the gateway (optional, not started by start.py)
docs/                 architecture, decisions (D-033 covers the hub), data dictionary, NASA sources
```

More on the observation platform: [CLAUDE.md](CLAUDE.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md),
[docs/DECISIONS.md](docs/DECISIONS.md), [docs/NASA_SOURCES.md](docs/NASA_SOURCES.md).

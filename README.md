# MedVital

Astronaut health monitoring for the NASA Space Apps Challenge 2026 (New York City). Each astronaut wears a device
that streams heart rate, blood oxygen, breathing, temperature and radiation to the spacecraft every second. The
spacecraft runs on Cloudflare: it double-checks every reading against that astronaut's own pre-flight report, buzzes
the wearable when something is wrong, and sends everything to NASA at the end of each day without losing a record
when the link to Earth drops.

It covers four astronaut health risks: radiation, bone, heart and behavioral health (sleep and stress).

## Run it

You need Python 3.11 or newer. From the repo root:

```sh
python start.py --fresh
```

The first run creates `.venv/` and installs the backend (a few minutes, once). Then it starts the NASA receiver and
the spacecraft hub and opens the start page, where you pick a role:

| Role | URL | What you see |
|---|---|---|
| Start page | <http://localhost:8000/> | Astronaut, Spacecraft hub or NASA |
| Astronaut | <http://localhost:8000/astronaut/> | Log in as a crew member or sign up, then your 3D body, live |
| Spacecraft hub | <http://localhost:8000/cloudflare/> | The private network, connected wearables, mission clock, the daily send to NASA |
| NASA | <http://localhost:5000/> | Every astronaut, their pre-flight report, live vs. baseline, mission summary, upcoming events |

**Demo clock: 1 real minute = 1 mission day.** Days 1–8 are the cruise to Mars, the crew lands on day 9, and
spacewalks start on day 10. `Ctrl+C` stops everything; `--fresh` starts a new mission.

### Three laptops (same Wi-Fi)

```sh
python start.py --role nasa --lan                                                   # NASA laptop
python start.py --role spacecraft --lan --nasa-url http://<NASA-laptop-IP>:5000     # spacecraft laptop
# astronaut laptop or phone: open http://<spacecraft-laptop-IP>:8000/astronaut/
```

`--tunnel` also publishes the hub through a Cloudflare quick tunnel (needs `cloudflared`; no account), so a phone can
open the astronaut screen and really vibrate.

## Demo script

1. **Spacecraft hub.** The network as a tree: NASA above Cloudflare; inside Cloudflare the Worker + D1, DONKI and the
   checker; inside that the private network, the hub, the onboard AI agent and every wearable. Each kind of traffic
   has its own colour (legend under the drawing). The pink dot is the Cloudflare checker going round every part.
2. **Astronaut → Maya Okafor.** Her 3D body: every tile is live and the heart beats at her rate. Under the body:
   **Sleep**, **Leave the spacecraft**, **Urine test (bone loss)**, **Mood check-in**. *Upcoming* shows the space
   weather with date, time and (when NASA reports it) duration.
3. **Spacewalk.** *Leave the spacecraft*. After 20 s: "Upcoming: … Go back inside by …" with a countdown. Ignore it
   and 15 s later the screen turns red, buzzes and only offers **Go back inside**. The time outside and the dose
   received show under *Spacewalks* and go to NASA. *Demo controls → Skip to 2 h before the next solar event* first
   to make the event a real NASA one.
4. **Ask the AI.** Open the hub screen's *Onboard AI agent* box, then ask in the astronaut's *Assistant* tab: the
   yellow dot goes astronaut → hub → agent (→ Workers AI through Cloudflare) and back.
5. **Cut the link.** On the hub or NASA screen. Cloudflare turns red, a 3-2-1 retry counter runs next to it, and
   every retry lands in the link log. Records wait in Cloudflare's D1. *Restore*: they rush to NASA back to back,
   and the checker says the three databases agree.
6. **New astronaut.** Astronaut → *New astronaut* → upload a report from `reports/` or type the values.
7. **NASA.** Pick an astronaut and a day: that day's full report (vitals, sleep, tests, time outside, dose,
   alerts, summary), plus pre-flight vs. now, alerts and upcoming events. The checker's sentence is at the top.

## Where the numbers come from

| | Source | Origin label |
|---|---|---|
| Radiation dose rate | Real Curiosity RAD observations (PDS, cruise 2011–12 and surface 2012) at that point of the mission, x RAD's measured quality factor (3.82 cruise, 3.05 surface) | measured |
| Space weather | Real NASA DONKI records, May–June 2024, placed on the mission calendar (flares, CMEs, solar particle events, storms, CME arrival forecasts at Mars) | measured |
| Research behind each risk | NASA OSDR study records (links in the NASA view) | reference |
| Heart rate, SpO2, breathing, temperature, test results | Simulated around each astronaut's pre-flight report | simulated |
| Bone density | Modeled from the loss rates the 3D body cites (Sibonga et al. 2015) | modeled |
| Limits | NASA-STD-3001: 600 mSv career, 250 mSv per solar event. Spacewalk budget and heart-rate allowances are demo settings. | |

The four astronauts and their reports (`reports/`) are fictional. MedVital is not a medical device and gives no
diagnosis. Re-download the NASA data with `python tools/fetch_nasa_data.py`; rebuild the sample reports with
`python tools/make_reports.py`.

### Cloudflare: the link to Earth

`cloudflare/` is a Worker with a D1 database and Workers AI. The spacecraft sends its day-end batch and urgent
alerts to it, D1 keeps every record, and the NASA receiver pulls them down. The link switch lives in the Worker,
and Workers AI words alerts and summaries through the Worker, so no API token sits on any laptop. Every request
needs the header `x-medvital-key`, checked against the Worker secret `MEDVITAL_KEY`. Nothing in this repository
holds a Cloudflare account id, token or key, so the public repo exposes nothing.

Try it on one laptop (needs Node.js; the D1 is local and Workers AI is off):

```sh
python start.py --fresh --worker-local
```

Deploy it to your account once:

1. Cloudflare dashboard, Workers & Pages, Create, Import a repository: pick this repo, set the root directory to
   `cloudflare`, deploy. Wrangler creates the `medvital` D1 database itself (or run `npx wrangler deploy` in
   `cloudflare/`).
2. Worker, Settings, Variables and Secrets: add the secret `MEDVITAL_KEY` (a long random string).
3. On the laptops, put the Worker's URL and the key in `.env` at the repo root (gitignored) or in Codespaces
   secrets, then run `python start.py --fresh`:

```sh
MEDVITAL_CLOUDFLARE_URL=https://medvital-link.<your-subdomain>.workers.dev
MEDVITAL_CLOUDFLARE_KEY=<the same key>
```

Without these two variables the hub sends straight to the NASA receiver, as before.

What Cloudflare does while the mission runs:
* **Link to NASA.** Everything the spacecraft sends lands in D1; NASA pulls it. Cutting the link stops Cloudflare →
  NASA only: records wait in D1, NASA retries every 3 s, each retry is logged.
* **Checker.** The hub and NASA report in every 3 s (Cloudflare cannot call into a private network). The Worker marks
  silent parts as down, checks that the spacecraft, D1 and NASA agree, and Workers AI words the result.
* **Space weather.** A cron trigger fetches NASA DONKI into D1 every 30 minutes; the spacecraft reads it from there.
* **Workers AI** words alerts, summaries and the onboard agent's answers (any changed number is rejected).

The onboard agent uses a local model first when one is set (on your laptop, with Ollama running):
`MEDVITAL_OLLAMA_MODEL=gemma4` in `.env`.

Rules always fire first; AI only explains, and the onboard agent rejects any AI wording that changes a number.

## Tests

```sh
.venv/bin/python -m pytest backend nasa        # Windows: .venv\Scripts\python -m pytest backend nasa
node --test body-dashboard/tests/*.mjs
```

## Repository layout

```
start.py              one command: installs, starts NASA + the hub, opens the start page
apps/                 start page, astronaut log-in/sign-up, spacecraft hub screen (plain HTML/JS)
body-dashboard/       the astronaut screen: 3D body (three.js, BodyParts3D); hub-bridge.js feeds it live
backend/medvital/hub/ the spacecraft: mission clock, crew simulator, rules, outbox sync, schedule, AI
backend/medvital/     MEDVITAL observation platform: provenance-labelled observations, four health modules
nasa/                 NASA receiver (Flask + SQLite) and the flight surgeon's screen
data/nasa/            downloaded RAD, DONKI and OSDR data
reports/              four sample pre-flight reports (.txt + .pdf)
tools/                fetch_nasa_data.py, make_reports.py
cloudflare/           the link to Earth: Worker + D1 + Workers AI, locked with a secret key
frontend/             earlier React live view (optional, not started)
docs/                 decisions (D-033, D-034), data dictionary, NASA sources, architecture
```

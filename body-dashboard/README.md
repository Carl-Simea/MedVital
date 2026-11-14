# MEDvital

Health dashboard for astronauts, built for the NASA Space Apps Challenge 2026 ("Create health monitoring software for astronauts"). A rotatable 3D body shows the state of each bone, organ and muscle group, based on the measurements a crew member enters. Every warning cites its source and states whether it is a verified NASA figure or a general convention.

Plain HTML and JavaScript, no build step, no external services. All data stays in the browser.

**Decision support, not a diagnosis.** Average anatomy, not an X-ray.

## Run

Requires Node.js 18 or newer.

```sh
node server.mjs          # then open http://localhost:8080
```

On macOS you can double-click `MEDvital.command` instead. Open `http://localhost:8080/#sample` to start with clearly labelled sample data. Any static web server also works (`python3 -m http.server 8080 -d public`); only the feedback button needs `server.mjs`.

## What it does

- **3D body**: drag to rotate, scroll or pinch to zoom, click a part. Layers: Bones, Organs, Muscles, All (keys 1–4); X-ray look in Settings or with `x`.
- **Part card**: status, part-specific warnings, the indicators NASA tracks for that part (and whether they can be measured in flight), what spaceflight does to it and what helps, each with a source link.
- **16 vital tiles** (heart rate, blood pressure, SpO2, breathing, temperature, glucose, reaction time, sleep, back pain, hemoglobin, urine volume, body mass, radiation, hip bone density, strength, vitamin D).
- **Sleep, Exercise and Nutrition scores (1–100)** shown as rings from red to green (`public/scores.mjs`). Each component is rated on a straight-line scale between anchor points taken from NASA or peer-reviewed figures where they exist. The score itself is a MEDvital model, not a NASA scale. Missing inputs lower the shown coverage, not the score.
- **Check-in and alertness test** (`public/health.mjs`, PVT-B inspired, not validated) with triage that accounts for the radio delay to Earth, the Moon or Mars.
- **Data input** (bottom right): paste a medical report, lab results or a device export, or drop a `.txt`, `.csv`, `.tsv` or `.json` file. `public/intake.mjs` reads only values where a known label sits next to a number, converts common units (°F, mmol/L, nmol/L, mL), rejects implausible values and lists lines it could not read. Nothing changes until you press Apply. PDFs and images are not read yet; paste their text instead.
- **Crew assistant**: rule-based, not a language model. Docked next to the data input. Answers from the crew member's own data with sources and accepts values typed in plain English ("blood pressure 120/80", "slept 6 hours"). Voice input uses the browser's speech recognition, which sends audio to the browser vendor's online service.

## API (browser console or your own code)

```js
AstroBody.setMeasurements({'hr.rest': 71, 'urine.volumeL': 1.4, 'bmd.hipPct': -6, 'mission.month': 4})  // keys: AstroBody.indicators
AstroBody.getParts()      // evaluated state of every part
AstroBody.getScores()     // {sleep, exercise, nutrition}: score, coverage, components
AstroBody.setView('sleep'); AstroBody.setLayer('organ'); AstroBody.select('heart')
AstroBody.loadSample(); AstroBody.clearSample()
```

## Structure

| Path | Content |
|---|---|
| `public/index.html`, `style.css`, `app.js` | Dashboard, part card, scores, assistant panel, `window.AstroBody` API |
| `public/lobby.js` | 3D scene: body, scanner platform, orbit camera, GPU picking |
| `public/parts.mjs` | Part catalogue, indicators, rules and sources (pure, runs in Node) |
| `public/scores.mjs` | Sleep / Exercise / Nutrition scores |
| `public/engine.mjs`, `pvt.mjs`, `knowledge.mjs`, `health.mjs` | Decision logic, reaction test, check-in |
| `public/assistant.mjs` | Rule-based assistant |
| `public/intake.mjs` | Reads values from pasted reports and files |
| `public/data/` | Anatomy meshes (derived from BodyParts3D) |
| `public/vendor/` | three.js r187 |
| `server.mjs` | Local server without caching; stores feedback in `feedback/` (git-ignored) |
| `tests/` | `node --test tests/*.mjs` |
| `tools/` | Rebuild the anatomy data (`get_bodyparts3d.sh`, `build_anatomy.py`), regenerate `docs/SOURCES-parts.md` |
| `docs/` | Source registers |

Anatomy coordinates: millimetres, X = person's left, Y = up, Z = front.

## Known limits

- WebGL rendering and picking were tested mainly with a software renderer; real phones and Safari need more testing.
- Several thresholds (blood pressure, SpO2, breathing, temperature, glucose, body mass, vitamin D, urine, back pain, sleep hours) are general clinical conventions, not NASA values. The app labels each one.
- Liver, stomach, intestines, airways and tendons have no verified human spaceflight threshold; the app shows this as a gap instead of inventing one.

## Licenses

- Anatomy models: BodyParts3D, © The Database Center for Life Science, licensed under CC Attribution-Share Alike 2.1 Japan. The derived data in `public/data/` was simplified and re-aligned and is shared under the same license.
- three.js: MIT, see `public/vendor/LICENSE-three.txt`.

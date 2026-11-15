# MEDvital

Health dashboard for astronauts, built for the NASA Space Apps Challenge 2026 ("Create health monitoring software for astronauts"). A rotatable 3D body shows the state of each bone, organ and muscle group, based on the measurements a crew member enters. Every warning cites its source and states whether it is a verified NASA figure or a general convention.

Plain HTML and JavaScript, no build step, no external services. All data stays in the browser.

**Decision support, not a diagnosis.** Average anatomy, not an X-ray.

## Run

Requires Node.js 18 or newer.

```sh
node server.mjs          # then open http://localhost:8080
```

On macOS you can double-click `MEDvital.command` instead. Open `http://localhost:8080/#sample` (or `#sample=nominal`, `#sample=critical`) to start with clearly labelled test data. Any static web server also works (`python3 -m http.server 8080 -d public`); only the feedback button needs `server.mjs`.

## What it does

- **3D body**: drag to rotate, scroll or pinch to zoom, click to select. Every bone and every muscle can be selected on its own (276 bones and joints, 427 muscles, named after BodyParts3D); organs are selected as a group. Layers: Bones, Organs, Muscles, All (keys 1–4); X-ray look in Settings or with `x`. Muscles have a smooth surface with pale tendon ends. The body does not rotate on its own unless Auto-rotate is switched on in Settings.
- **Part card**: status, part-specific warnings, the indicators NASA tracks for that part (and whether they can be measured in flight), what spaceflight does to it and what helps, each with a source link. A single bone or muscle shows the status of its group, because the data entered is not specific to one bone or muscle; the card says so and links to the group.
- **16 vital tiles** (heart rate, blood pressure, SpO2, breathing, temperature, glucose, reaction time, sleep, back pain, hemoglobin, urine volume, body mass, radiation, hip bone density, strength, vitamin D).
- **Sleep, Exercise and Nutrition scores (1–100)** shown as rings from red to green (`public/scores.mjs`). Each component is rated on a straight-line scale between anchor points taken from NASA or peer-reviewed figures where they exist. The score itself is a MEDvital model, not a NASA scale. Missing inputs lower the shown coverage, not the score.
- **Check-in and alertness test** (`public/health.mjs`, PVT-B inspired, not validated) with triage that accounts for the radio delay to Earth, the Moon or Mars.
- **Assistant and data input** (bottom right, one conversation): ask a question, or paste a medical report, lab results or a device export, or drop a `.txt`, `.csv`, `.tsv` or `.json` file. `public/intake.mjs` reads only values with a known label, converts common units, rejects implausible numbers, and shows what it found; nothing changes until you press Apply. PDFs and images are not read. The assistant (`public/assistant.mjs`) is rule-based, not a language model, and answers from the crew member's own data with sources.
- **Test data** (button under the body): three invented scenarios in `public/testdata.mjs` that cover every input: *In range*, *Borderline* (some values to watch) and *Critical*. "Paste as a report" writes the borderline scenario into the message box as text, to show the reader. Loading a scenario also starts a **live test stream** (`public/live.mjs`): heart rate, breathing, blood oxygen, skin temperature, heart rate variability, skin conductance and radiation dose rate update once per second, as a wearable would send them. Nothing in the stream is measured.
- **Body** (pill next to the name): biological sex, height 150–205 cm and body mass 45–130 kg. Sex sets the reference ranges that differ (hemoglobin, hematocrit, ferritin, creatinine, urinary calcium, fluid need) and adjusts shoulders, waist and pelvis of the male reference model; it is not a female anatomy. Height and mass stretch the model. This is a rough visual aid: the model is scaled, not re-shaped. Reference: the BodyParts3D skeleton spans 164 cm, taken as a stature of 166 cm; breadth follows the body-mass index relative to 22.5 kg/m², damped. The slider range is a convenience range, not a NASA limit; NASA designs hardware for the 1st-percentile female to the 99th-percentile male of its crew population ([NASA JSC, Crew Anthropometry and Spacesuit Sizing, 2025](https://ntrs.nasa.gov/api/citations/20250003042/downloads/UMN%20Lecture%202025.pdf)).
- **Activity** (pill next to the name): resting, sleeping, working, exercising or spacewalk. The live test stream follows a compressed day, or the activity is set by hand. It is part of the rating: heart and breathing rate are only rated at rest, and not for 30 seconds after exercise.
- **Values**: 55 indicators. Besides vital signs, bone, muscle, eye and radiation values these include a blood count and chemistry (white cells, platelets, hematocrit, ferritin, sodium, potassium, creatinine, calcium, C-reactive protein, cortisol), urine citrate and pH, kidney ultrasound, retinal thickness (OCT), carotid wall thickness, sleep efficiency, cognition, mood, stress, motion sickness and balance. What NASA collects is taken from the Spaceflight Standard Measures and Artemis II pages; reference ranges for blood values are general clinical ranges, marked as convention. Ten values are tracked but not rated, because they only mean something against a personal baseline.

## API (browser console or your own code)

```js
AstroBody.setMeasurements({'hr.rest': 71, 'urine.volumeL': 1.4, 'bmd.hipPct': -6, 'mission.month': 4})  // keys: AstroBody.indicators
AstroBody.getParts()      // evaluated state of every part
AstroBody.getScores()     // {sleep, exercise, nutrition}: score, coverage, components
AstroBody.setView('sleep'); AstroBody.setLayer('organ'); AstroBody.select('heart')
AstroBody.loadSample('mixed'); AstroBody.clearSample()   // 'nominal' | 'mixed' | 'critical'
AstroBody.setBody({sex: 'f', heightCm: 178, massKg: 74}) // setBody(null) resets
AstroBody.setActivity('exercise')                       // 'rest' | 'sleep' | 'work' | 'exercise' | 'eva' | 'auto' | null
AstroBody.startLive(); AstroBody.stopLive()             // simulated wearable stream (needs test data)
```

## Structure

| Path | Content |
|---|---|
| `public/index.html`, `style.css`, `app.js` | Dashboard, part card, scores, assistant panel, `window.AstroBody` API |
| `public/lobby.js` | 3D scene: body, scanner platform, orbit camera, GPU picking of single parts, muscle and bone shading |
| `public/parts.mjs` | Part catalogue, indicators, rules and sources (pure, runs in Node) |
| `public/scores.mjs` | Sleep / Exercise / Nutrition scores |
| `public/engine.mjs`, `pvt.mjs`, `knowledge.mjs`, `health.mjs` | Decision logic, reaction test, check-in |
| `public/assistant.mjs` | Rule-based assistant |
| `public/intake.mjs` | Reads values from pasted reports and files |
| `public/testdata.mjs` | Invented test scenarios and their text report |
| `public/live.mjs` | Simulated wearable stream and activity states |
| `public/data/` | Anatomy meshes with a part index per vertex and the part list (derived from BodyParts3D) |
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

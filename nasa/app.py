"""
app.py - MedVital, Spot 3 (NASA): the NASA receiver.

Run it:   python app.py          (or python start.py at the repo root, which starts everything)

Endpoints
  POST /batch   the spacecraft sends {"records": [...]}, NASA answers {"saved": [ids]}
  GET  /stats   how many records NASA saved: total, per astronaut, per type
  POST /link    {"up": true|false} switches the link to Earth up or down
  GET  /link    the current state of the link: {"up": true|false}
  GET  /records everything the mission record screen draws, grouped per astronaut
  GET  /        the mission record screen (the view NASA's flight surgeon uses)
  GET  /api/mission          crew overview, mission clock, upcoming events, recent alerts and batches
  GET  /api/astronaut/<id>   one astronaut: pre-flight report, pre-flight vs. now, charts, alerts, summaries
  GET  /reports/<file>       the pre-flight reports NASA keeps on Earth (repo folder reports/)
"""

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone

from flask import Flask, jsonify, request, send_from_directory

import record_format as fmt   # the ONE place that knows the record shape

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
# start.py sets these; the defaults are for running this file on its own.
HOST = os.environ.get("MEDVITAL_NASA_HOST", "127.0.0.1")   # 0.0.0.0 = reachable from the other laptops
PORT = int(os.environ.get("MEDVITAL_NASA_PORT", "5000"))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# delete this file (or run start.py --fresh) to start a clean mission
DB_PATH = os.environ.get("MEDVITAL_NASA_DB", os.path.join(BASE_DIR, "mission.db"))

app = Flask(__name__)

# STEP 2 - the link-to-Earth switch. Up by default.
# It lives in memory only, so the link is up again every time the receiver starts.
link = {"up": True}

# Hide Flask's one-line-per-request log. We print our own short lines instead.
logging.getLogger("werkzeug").setLevel(logging.WARNING)


def log(message):
    """Print one line with the time, so we can follow what the receiver does."""
    print(datetime.now().strftime("[%H:%M:%S]"), message, flush=True)


# ---------------------------------------------------------------------------
# Database (SQLite): the full mission record
# ---------------------------------------------------------------------------
def open_db():
    """Open the database. One connection per request keeps things simple."""
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    """Create the table the first time the receiver runs."""
    db = open_db()
    try:
        with db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS records (
                    id           TEXT PRIMARY KEY,  -- the record id; saving the same id twice is impossible
                    type         TEXT NOT NULL,     -- reading | alert | summary
                    astronaut_id TEXT NOT NULL,
                    time         TEXT NOT NULL,     -- the record's own time (ISO 8601)
                    body         TEXT NOT NULL,     -- the whole record as JSON, as received
                    received_at  TEXT NOT NULL      -- when NASA saved it (UTC)
                )
                """
            )
            db.execute("CREATE INDEX IF NOT EXISTS records_by_astronaut ON records (astronaut_id, type)")
            db.execute("CREATE INDEX IF NOT EXISTS records_by_type ON records (type)")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# STEP 1 - receive batches
# ---------------------------------------------------------------------------
@app.post("/batch")
def receive_batch():
    """Save a batch of records and answer with the ids NASA now has."""
    # STEP 2 - while the link is down nothing gets through: answer 503, save nothing.
    if not link["up"]:
        log("batch refused: link is DOWN (503)")
        return jsonify({"error": "link down"}), 503

    payload = request.get_json(force=True, silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        log('batch refused: the body was not {"records": [...]} (400)')
        return jsonify({"error": 'expected JSON like {"records": [...]}'}), 400

    saved = []     # ids NASA has after this request (new ones AND ones it already had)
    new_count = 0  # how many of them were new
    received_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")

    db = open_db()
    try:
        with db:  # one transaction: everything is committed together, or nothing is
            for raw in payload["records"]:
                record = fmt.parse_record(raw)
                if record is None:
                    continue  # no usable id: we cannot save it, so we do not confirm it

                # INSERT OR IGNORE = idempotent. If this id is already saved,
                # nothing changes and no duplicate is created.
                cursor = db.execute(
                    "INSERT OR IGNORE INTO records (id, type, astronaut_id, time, body, received_at)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        record["id"],
                        record["type"],
                        record["astronaut_id"],
                        record["time"],
                        json.dumps(raw),
                        received_at,
                    ),
                )
                new_count += cursor.rowcount  # 1 if it was inserted, 0 if we already had it

                # Confirm the id either way, so the spacecraft stops resending it.
                if record["id"] not in saved:
                    saved.append(record["id"])
    finally:
        db.close()

    # We only get here after the commit, so every id in "saved" really is on disk.
    log(f"batch: {len(payload['records'])} received, {len(saved)} confirmed, {new_count} new")
    return jsonify({"saved": saved})


@app.get("/stats")
def stats():
    """Total records saved, plus a count per astronaut and per type."""
    db = open_db()
    try:
        # One query gives every count, so the numbers always add up.
        rows = db.execute(
            "SELECT astronaut_id, type, COUNT(*) AS n FROM records GROUP BY astronaut_id, type"
        ).fetchall()
    finally:
        db.close()

    total = 0
    by_astronaut = {}           # {"astro-1": 12, ...}
    by_type = {}                # {"reading": 20, "alert": 3, "summary": 1}
    by_astronaut_and_type = {}  # {"astro-1": {"reading": 10, "alert": 2}, ...}
    for row in rows:
        astronaut_id, record_type, n = row["astronaut_id"], row["type"], row["n"]
        total += n
        by_astronaut[astronaut_id] = by_astronaut.get(astronaut_id, 0) + n
        by_type[record_type] = by_type.get(record_type, 0) + n
        by_astronaut_and_type.setdefault(astronaut_id, {})[record_type] = n

    return jsonify(
        {
            "total": total,
            "by_astronaut": by_astronaut,
            "by_type": by_type,
            "by_astronaut_and_type": by_astronaut_and_type,
        }
    )


# ---------------------------------------------------------------------------
# STEP 2 - link down/up switch
# ---------------------------------------------------------------------------
@app.route("/link", methods=["GET", "POST"])
def link_switch():
    """POST {"up": true|false} sets the link. GET just reads it."""
    if request.method == "POST":
        payload = request.get_json(force=True, silent=True)
        if not isinstance(payload, dict) or not isinstance(payload.get("up"), bool):
            return jsonify({"error": 'expected JSON like {"up": true} or {"up": false}'}), 400
        link["up"] = payload["up"]
        log("link is now UP" if link["up"] else "link is now DOWN")
    return jsonify({"up": link["up"]})


# ---------------------------------------------------------------------------
# STEP 5 - mission record screen
# ---------------------------------------------------------------------------
@app.get("/")
def mission_record_screen():
    """The page itself. It then asks /records, /stats and /link every few seconds."""
    return send_from_directory(BASE_DIR, "mission_record.html")


@app.get("/vendor/<path:name>")
def vendor(name):
    """Chart.js, served locally so the screen works without internet."""
    return send_from_directory(os.path.join(BASE_DIR, "vendor"), name)


@app.get("/records")
def records_for_screen():
    """Every saved record, grouped per astronaut, in the form the screen draws."""
    db = open_db()
    try:
        rows = db.execute("SELECT body, received_at FROM records ORDER BY rowid").fetchall()
    finally:
        db.close()

    astronauts = {}  # astronaut id -> what the screen shows for that astronaut
    for row in rows:
        record = fmt.parse_record(json.loads(row["body"]))
        if record is None:
            continue
        # "t" = the record's time in milliseconds. If the record has no
        # readable time, fall back to the moment NASA received it.
        t = fmt.parse_time(record["time"]) or fmt.parse_time(row["received_at"])

        astronaut = astronauts.setdefault(
            record["astronaut_id"],
            {"id": record["astronaut_id"], "readings": [], "alerts": [], "summaries": [], "labs": [],
             "totalDose": None, "flagged": 0},
        )
        if record["type"] == fmt.TYPE_READING:
            reading = fmt.reading_for_screen(record["data"])
            if reading["quality"] != "valid":
                astronaut["flagged"] += 1   # the spacecraft flagged it (sensor glitch?): kept, not charted
                continue
            astronaut["readings"].append({"t": t, **reading})
        elif record["type"] == fmt.TYPE_ALERT:
            astronaut["alerts"].append({"t": t, **fmt.alert_for_screen(record["data"])})
        elif record["type"] == fmt.TYPE_SUMMARY:
            astronaut["summaries"].append({"t": t, **fmt.summary_for_screen(record["data"])})
        elif record["type"] == fmt.TYPE_LAB:
            astronaut["labs"].append({"t": t, **fmt.lab_for_screen(record["data"])})
        # any other type is still saved and counted in /stats, just not drawn

    for astronaut in astronauts.values():
        # Sort by time. Records with the same time keep their arrival order.
        for name in ("readings", "alerts", "summaries", "labs"):
            astronaut[name].sort(key=lambda item: item["t"])   # oldest first (the chart wants this)
        astronaut["alerts"].reverse()                          # newest first
        astronaut["summaries"].reverse()                       # newest first
        astronaut["labs"].reverse()                            # newest first
        # Total radiation dose = the running total in the astronaut's latest reading.
        for reading in reversed(astronaut["readings"]):
            if reading["totalDose"] is not None:
                astronaut["totalDose"] = reading["totalDose"]
                break

    return jsonify({"astronauts": sorted(astronauts.values(), key=lambda a: a["id"])})


# ---------------------------------------------------------------------------
# STEP 6 - flight surgeon's views: mission overview and one astronaut
# ---------------------------------------------------------------------------
REPORTS_DIR = os.path.join(os.path.dirname(BASE_DIR), "reports")


def load(where="", args=()):
    """Records as dicts, oldest first. ``where`` filters on the stored columns (type, astronaut_id)."""
    db = open_db()
    try:
        rows = db.execute(f"SELECT body, received_at FROM records {where} ORDER BY rowid", args).fetchall()
    finally:
        db.close()
    out = []
    for row in rows:
        raw = json.loads(row["body"])
        rec = fmt.parse_record(raw)
        if rec is None:
            continue
        rec["mission"] = raw.get("mission") if isinstance(raw.get("mission"), dict) else {}
        rec["received_at"] = row["received_at"]
        out.append(rec)
    return out


def mission_now():
    """The latest mission time NASA has heard about (NASA only knows what came over the link)."""
    db = open_db()
    try:
        row = db.execute("SELECT body FROM records ORDER BY rowid DESC LIMIT 1").fetchone()
    finally:
        db.close()
    return (json.loads(row["body"]).get("mission") or {}) if row else {}


def latest_values(records):
    """Latest value per measurement key, plus its origin, from test/lab/profile records."""
    values, origin, pre = {}, {}, {}
    for r in records:
        d = r["data"]
        if r["type"] == fmt.TYPE_PROFILE:
            prof = d.get("profile") or {}
            pre = dict(prof.get("baseline") or {})
            pre.update({"hr.rest": prof.get("resting_hr"), "spo2.pct": prof.get("spo2"),
                        "radiation.careerMsv": prof.get("prior_career_msv", 0)})
            for k in ("mass.changePct", "strength.changePct", "bmd.hipPct"):
                pre.setdefault(k, 0.0)
        elif r["type"] in (fmt.TYPE_TEST, fmt.TYPE_LAB) and isinstance(d.get("values"), dict):
            for k, v in d["values"].items():
                values[k] = v
                origin[k] = d.get("origin") or r["type"]
    return pre, values, origin


@app.get("/api/mission")
def api_mission():
    now = mission_now()
    m = now.get("minute") or 0
    profiles = {r["astronaut_id"]: r for r in load("WHERE type = ?", (fmt.TYPE_PROFILE,))}
    crew = []
    for aid, prof_rec in profiles.items():
        recs = load("WHERE astronaut_id = ? AND type IN (?, ?, ?)", (aid, fmt.TYPE_READING, fmt.TYPE_ALERT, fmt.TYPE_SUMMARY))
        readings = [r for r in recs if r["type"] == fmt.TYPE_READING and r["data"].get("quality", "valid") == "valid"]
        alerts = [r for r in recs if r["type"] == fmt.TYPE_ALERT]
        summaries = [r for r in recs if r["type"] == fmt.TYPE_SUMMARY]
        prof = prof_rec["data"].get("profile") or {}
        last = readings[-1]["data"] if readings else {}
        crew.append({
            "id": aid, "name": prof.get("name", aid), "role": prof.get("role", ""), "restingHr": prof.get("resting_hr"),
            "heartRate": last.get("heartRate"), "spo2": last.get("spo2"), "state": last.get("state"),
            "careerDose": round((prof.get("prior_career_msv") or 0) + (last.get("totalDose") or 0), 2),
            "readings": len(readings), "alerts": len([a for a in alerts if a["data"].get("code") != "INFO"]),
            "lastAlert": alerts[-1]["data"] if alerts else None,
            "lastSummary": summaries[-1]["data"].get("text") if summaries else None,
            "spark": [r["data"].get("heartRate") for r in readings[-60:]],
        })
    events = [r["data"] | {"astronaut_id": r["astronaut_id"]} for r in load("WHERE type = ?", (fmt.TYPE_EVENT,))]
    upcoming = sorted((e for e in events if (e.get("m_end") or e.get("m_start") or 0) > m), key=lambda e: e["m_start"])
    alerts = [{"astronaut_id": r["astronaut_id"], "mission": r["mission"], **r["data"]}
              for r in load("WHERE type = ?", (fmt.TYPE_ALERT,)) if r["data"].get("code") != "INFO"][-12:][::-1]
    return jsonify({"now": now, "crew": sorted(crew, key=lambda c: c["id"]), "upcoming": upcoming[:80],
                    "alerts": alerts, "link": link})


@app.get("/api/astronaut/<aid>")
def api_astronaut(aid):
    recs = load("WHERE astronaut_id = ?", (aid,))
    if not recs:
        return jsonify({"error": "no records for this astronaut yet"}), 404
    now = mission_now()
    prof_rec = next((r for r in recs if r["type"] == fmt.TYPE_PROFILE), None)
    prof = (prof_rec["data"].get("profile") if prof_rec else None) or {}
    report_text = prof_rec["data"].get("report") if prof_rec else None
    stem = prof.get("report")
    pdf = f"/reports/{stem}.pdf" if stem and os.path.exists(os.path.join(REPORTS_DIR, f"{stem}.pdf")) else None
    readings = [r for r in recs if r["type"] == fmt.TYPE_READING]
    valid = [r for r in readings if r["data"].get("quality", "valid") == "valid"]
    pre, values, origin = latest_values(recs)
    sleep_hr = [r["data"]["heartRate"] for r in valid[-120:] if r["data"].get("state") == "asleep"]
    live = {
        "sleep_hr": round(sum(sleep_hr) / len(sleep_hr)) if sleep_hr else None,
        "spo2": valid[-1]["data"].get("spo2") if valid else None,
        "resp": valid[-1]["data"].get("respRate") if valid else None,
        "dose": round((prof.get("prior_career_msv") or 0) + (valid[-1]["data"].get("totalDose") or 0), 2) if valid else None,
    }
    compare = []
    for label, unit, key, live_key in fmt.COMPARE:
        now_v = live.get(live_key) if live_key else values.get(key)
        if now_v is None:
            now_v = values.get(key)
        before = pre.get(key)
        compare.append({"label": label, "unit": unit, "preflight": before, "now": now_v,
                        "change": round(now_v - before, 2) if isinstance(now_v, (int, float)) and isinstance(before, (int, float)) else None,
                        "origin": "wearable" if live_key and live.get(live_key) is not None else origin.get(key, "")})
    m = now.get("minute") or 0
    events = [r["data"] for r in recs if r["type"] == fmt.TYPE_EVENT]
    crew_events = [r["data"] for r in load("WHERE type = ? AND astronaut_id = ?", (fmt.TYPE_EVENT, "crew"))]
    upcoming = sorted((e for e in events + crew_events if (e.get("m_end") or 0) > m), key=lambda e: e["m_start"])[:30]
    tests = [{"mission": r["mission"], "text": fmt.lab_for_screen(r["data"])["text"], "origin": r["data"].get("origin"),
              "source": r["data"].get("source")} for r in recs if r["type"] in (fmt.TYPE_TEST, fmt.TYPE_LAB)][-25:][::-1]
    return jsonify({
        "id": aid, "profile": prof, "report": report_text, "reportPdf": pdf, "now": now, "compare": compare,
        "readings": [{"m": r["data"].get("missionMinute") or (r["mission"] or {}).get("minute"), "hr": r["data"].get("heartRate"),
                      "spo2": r["data"].get("spo2"), "dose": r["data"].get("totalDose"), "state": r["data"].get("state")}
                     for r in valid[-900:]],
        "flagged": len(readings) - len(valid),
        "alerts": [{"mission": r["mission"], **r["data"]} for r in recs if r["type"] == fmt.TYPE_ALERT][::-1][:30],
        "summaries": [{"mission": r["mission"], **r["data"]} for r in recs if r["type"] == fmt.TYPE_SUMMARY][::-1][:20],
        "tests": tests, "upcoming": upcoming,
    })


OSDR_FILE = os.path.join(os.path.dirname(BASE_DIR), "data", "nasa", "osdr_studies.json")
OSDR_TOPICS = [("heart", "Heart and blood vessels"), ("bone", "Bone loss"), ("muscle", "Muscle"), ("radiation", "Radiation"),
               ("immune", "Immune system"), ("eye", "Eyes (SANS)"), ("sleep", "Sleep and circadian rhythm")]


@app.get("/api/osdr")
def api_osdr():
    """NASA OSDR study records behind each health risk (downloaded by tools/fetch_nasa_data.py)."""
    if not os.path.exists(OSDR_FILE):
        return jsonify({"topics": []})
    with open(OSDR_FILE, encoding="utf-8") as fh:
        data = json.load(fh)
    topics = []
    for key, label in OSDR_TOPICS:
        t = data["topics"].get(key) or {}
        studies = [s for s in t.get("studies", []) if s.get("accession")]
        # human studies first, then the rest, three per risk
        studies.sort(key=lambda s: 0 if "Homo sapiens" in str(s.get("organism")) else 1)
        topics.append({"key": key, "label": label, "total": t.get("total"), "studies": [
            {"accession": s["accession"], "title": s.get("title"), "organism": s.get("organism"), "link": s.get("link")}
            for s in studies[:3]]})
    return jsonify({"source": data.get("source"), "retrieved_at": data.get("retrieved_at"), "topics": topics})


@app.get("/reports/<path:name>")
def reports(name):
    return send_from_directory(REPORTS_DIR, name)


# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------
init_db()

if __name__ == "__main__":
    log(f"NASA receiver running. Mission record screen: http://localhost:{PORT}   (Ctrl+C to stop)")
    log(f"Mission record database: {DB_PATH}")
    app.run(host=HOST, port=PORT)
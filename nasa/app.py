"""
app.py - MedVital, Spot 3 (NASA): the NASA receiver.

Run it:   python app.py

Endpoints
  POST /batch   the spacecraft sends {"records": [...]}, NASA answers {"saved": [ids]}
  GET  /stats   how many records NASA saved: total, per astronaut, per type
  POST /link    {"up": true|false} switches the link to Earth up or down
  GET  /link    the current state of the link: {"up": true|false}
  GET  /records everything the mission record screen draws, grouped per astronaut
  GET  /        the mission record screen (the view NASA's flight surgeon uses)
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
HOST = "127.0.0.1"   # only this laptop; the Cloudflare Tunnel connects locally
PORT = 5000          # the tunnel command in the README points at this port
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "mission.db")   # delete this file to start a clean mission

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
            {"id": record["astronaut_id"], "readings": [], "alerts": [], "summaries": [], "totalDose": None},
        )
        if record["type"] == fmt.TYPE_READING:
            astronaut["readings"].append({"t": t, **fmt.reading_for_screen(record["data"])})
        elif record["type"] == fmt.TYPE_ALERT:
            astronaut["alerts"].append({"t": t, **fmt.alert_for_screen(record["data"])})
        elif record["type"] == fmt.TYPE_SUMMARY:
            astronaut["summaries"].append({"t": t, **fmt.summary_for_screen(record["data"])})
        # any other type is still saved and counted in /stats, just not drawn

    for astronaut in astronauts.values():
        # Sort by time. Records with the same time keep their arrival order.
        for name in ("readings", "alerts", "summaries"):
            astronaut[name].sort(key=lambda item: item["t"])   # oldest first (the chart wants this)
        astronaut["alerts"].reverse()                          # newest first
        astronaut["summaries"].reverse()                       # newest first
        # Total radiation dose = the running total in the astronaut's latest reading.
        for reading in reversed(astronaut["readings"]):
            if reading["totalDose"] is not None:
                astronaut["totalDose"] = reading["totalDose"]
                break

    return jsonify({"astronauts": sorted(astronauts.values(), key=lambda a: a["id"])})


# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------
init_db()

if __name__ == "__main__":
    log(f"NASA receiver running. Mission record screen: http://localhost:{PORT}   (Ctrl+C to stop)")
    log(f"Mission record database: {DB_PATH}")
    app.run(host=HOST, port=PORT)
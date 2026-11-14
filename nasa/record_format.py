"""
record_format.py - THE ONE PLACE that knows what a record looks like.

Shared format (confirm with the Spacecraft spot before changing anything):

    {
      "id":          "<unique string>",
      "type":        "reading" | "alert" | "summary",
      "astronautId": "...",
      "time":        "<ISO 8601>",
      "data":        { ... }
    }

The receiver, the mission record screen and the test scripts all go through
this file. If the Spacecraft spot uses different names, change them HERE and
nowhere else on the NASA side.
(sync.js only needs to know the name of the "id" field: RECORD_ID_FIELD.)
"""

from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# 1. Field names on the record itself
# ---------------------------------------------------------------------------
FIELD_ID = "id"
FIELD_TYPE = "type"
FIELD_ASTRONAUT = "astronautId"
FIELD_TIME = "time"
FIELD_DATA = "data"

# The three kinds of record NASA receives
TYPE_READING = "reading"
TYPE_ALERT = "alert"
TYPE_SUMMARY = "summary"

# ---------------------------------------------------------------------------
# 2. Field names inside "data"
# ---------------------------------------------------------------------------
# type "reading": the wearable reading fields from the shared format.
# (astronautId and time are already on the record itself.)
READING_DEVICE_KEY = "deviceKey"   # the wearable's secret key (NASA never shows it)
READING_HEART_RATE = "heartRate"   # bpm
READING_SPO2 = "spo2"              # %
READING_STATE = "state"            # awake | asleep | exercise | spacewalk
READING_DOSE_RATE = "doseRate"     # µSv/h
READING_TOTAL_DOSE = "totalDose"   # mSv, running total

# type "alert"   <-- ASSUMPTION: confirm these two names with the Spacecraft spot
ALERT_CODE = "code"                # RETURN_NOW | CHECK_VITALS | INFO
ALERT_MESSAGE = "message"          # the plain-language explanation

# type "summary" <-- ASSUMPTION: confirm this name with the Spacecraft spot
SUMMARY_TEXT = "text"              # the daily summary text

# Alert codes (shared format)
ALERT_RETURN_NOW = "RETURN_NOW"       # radiation or solar event
ALERT_CHECK_VITALS = "CHECK_VITALS"   # heart rate or blood oxygen off baseline
ALERT_INFO = "INFO"                   # daily summary or exercise reminder ready


# ---------------------------------------------------------------------------
# 3. Building and reading records
# ---------------------------------------------------------------------------
def make_record(record_id, record_type, astronaut_id, time, data):
    """Build one record in the shared shape (the fake-data scripts use this)."""
    return {
        FIELD_ID: record_id,
        FIELD_TYPE: record_type,
        FIELD_ASTRONAUT: astronaut_id,
        FIELD_TIME: time,
        FIELD_DATA: data,
    }


def parse_record(raw):
    """Read one incoming record.

    Returns a dict with OUR names (id, type, astronaut_id, time, data),
    or None if the record has no usable id (without an id we cannot save it).

    We are strict about the id only. Anything else that is missing is stored
    as "unknown" instead of being thrown away: nothing gets lost, and the odd
    record shows up in /stats where we can spot it.
    """
    if not isinstance(raw, dict):
        return None

    record_id = raw.get(FIELD_ID)
    # The id should be a string. A whole number is accepted too and turned
    # into a string. (bool is refused: in Python, True counts as an int.)
    if isinstance(record_id, bool) or not isinstance(record_id, (str, int)):
        return None
    record_id = str(record_id)
    if record_id == "":
        return None

    record_type = raw.get(FIELD_TYPE)
    astronaut_id = raw.get(FIELD_ASTRONAUT)
    time = raw.get(FIELD_TIME)
    data = raw.get(FIELD_DATA)

    return {
        "id": record_id,
        "type": record_type if isinstance(record_type, str) and record_type else "unknown",
        "astronaut_id": str(astronaut_id) if isinstance(astronaut_id, (str, int)) and astronaut_id != "" else "unknown",
        "time": time if isinstance(time, str) else "",
        "data": data if isinstance(data, dict) else {},
    }


def parse_time(text):
    """Turn an ISO 8601 time into milliseconds since 1970 (what the charts use).

    Returns None if the text is not a time we can read.
    """
    if not isinstance(text, str) or text == "":
        return None
    try:
        # "Z" means UTC. Older Python versions only understand "+00:00".
        moment = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)   # no time zone given: assume UTC
    return int(moment.timestamp() * 1000)


# ---------------------------------------------------------------------------
# 4. What the mission record screen shows for each kind of record
# ---------------------------------------------------------------------------
def _number(value):
    """Return value as a number, or None if it is not one."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def reading_for_screen(data):
    """The parts of a reading that the screen draws. The deviceKey is left out on purpose."""
    return {
        "heartRate": _number(data.get(READING_HEART_RATE)),
        "spo2": _number(data.get(READING_SPO2)),
        "totalDose": _number(data.get(READING_TOTAL_DOSE)),
    }


def alert_for_screen(data):
    """The parts of an alert that the screen shows."""
    return {
        "code": str(data.get(ALERT_CODE) or "UNKNOWN"),
        "message": str(data.get(ALERT_MESSAGE) or ""),
    }


def summary_for_screen(data):
    """The parts of a daily summary that the screen shows."""
    return {
        "text": str(data.get(SUMMARY_TEXT) or ""),
    }
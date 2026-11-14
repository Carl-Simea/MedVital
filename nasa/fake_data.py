"""
fake_data.py - fake records and two tiny HTTP helpers, shared by the test scripts.

Nothing here is used by the real receiver. It only pretends to be the
spacecraft so we can test NASA's side with fake data.
"""

import json
import random
import urllib.error
import urllib.request
from datetime import datetime, timezone

import record_format as fmt   # the ONE place that knows the record shape

# Where the NASA receiver runs. Every test script also accepts another address
# as its first argument, for example the https://....trycloudflare.com URL.
DEFAULT_NASA_URL = "http://127.0.0.1:5000"


def now_iso():
    """The current time as ISO 8601 in UTC, like JavaScript's toISOString()."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Fake astronauts
# ---------------------------------------------------------------------------
class FakeWearable:
    """Pretends to be one astronaut's wearable and makes plausible readings."""

    def __init__(self, astronaut_id, resting_heart_rate):
        self.astronaut_id = astronaut_id
        self.resting_heart_rate = resting_heart_rate
        self.total_dose = 0.0   # mSv, running total

    def reading(self, record_id):
        """One fake reading record."""
        dose_rate = random.uniform(20.0, 30.0)   # µSv/h
        # FAKE: pretend each reading covers 30 minutes of mission time,
        # so the total dose visibly climbs on the chart.
        self.total_dose += dose_rate * 0.5 / 1000.0   # µSv/h * h -> µSv, / 1000 -> mSv
        data = {
            fmt.READING_DEVICE_KEY: "fake-key-" + self.astronaut_id,
            fmt.READING_HEART_RATE: self.resting_heart_rate + random.randint(-3, 6),
            fmt.READING_SPO2: random.randint(96, 99),
            fmt.READING_STATE: "awake",
            fmt.READING_DOSE_RATE: round(dose_rate, 1),
            fmt.READING_TOTAL_DOSE: round(self.total_dose, 4),
        }
        return fmt.make_record(record_id, fmt.TYPE_READING, self.astronaut_id, now_iso(), data)

    def alert(self, record_id, code, message):
        """One fake alert record."""
        data = {fmt.ALERT_CODE: code, fmt.ALERT_MESSAGE: message}
        return fmt.make_record(record_id, fmt.TYPE_ALERT, self.astronaut_id, now_iso(), data)

    def summary(self, record_id, text):
        """One fake daily summary record."""
        data = {fmt.SUMMARY_TEXT: text}
        return fmt.make_record(record_id, fmt.TYPE_SUMMARY, self.astronaut_id, now_iso(), data)


def two_fake_astronauts():
    """Two astronauts with different baselines, like the two profiles in the team plan."""
    return [FakeWearable("astro-1", 62), FakeWearable("astro-2", 74)]


# ---------------------------------------------------------------------------
# Tiny HTTP helpers (standard library only, nothing extra to install)
# ---------------------------------------------------------------------------
def post_json(url, payload):
    """POST payload as JSON.

    Returns (status code, parsed JSON answer).
    Returns (None, None) if the server could not be reached at all.
    """
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return _send(request)


def get_json(url):
    """GET a URL. Returns the same kind of pair as post_json."""
    return _send(urllib.request.Request(url, method="GET"))


def _send(request):
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, _parse(response.read())
    except urllib.error.HTTPError as error:
        # The server answered with an error code such as 503 (link down).
        return error.code, _parse(error.read())
    except (urllib.error.URLError, OSError):
        # No answer at all: server not running, wrong address, timeout...
        return None, None


def _parse(body):
    try:
        return json.loads(body.decode("utf-8"))
    except ValueError:
        return None
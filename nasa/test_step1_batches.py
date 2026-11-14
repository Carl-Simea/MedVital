"""
test_step1_batches.py - STEP 1 test.

Posts 3 batches of fake records to the NASA receiver, including one repeated
id, and prints the responses and /stats.

Run it (with the receiver already running in another terminal):
    python test_step1_batches.py
    python test_step1_batches.py https://xxxx.trycloudflare.com   (through the tunnel)
"""

import sys
import uuid

import record_format as fmt
from fake_data import DEFAULT_NASA_URL, get_json, post_json, two_fake_astronauts

NASA_URL = (sys.argv[1] if len(sys.argv) > 1 else DEFAULT_NASA_URL).rstrip("/")

# A different random prefix on every run, so each run adds brand-new ids.
RUN = "step1-" + uuid.uuid4().hex[:8]

astro1, astro2 = two_fake_astronauts()

batch1 = [
    astro1.reading(RUN + "-001"),
    astro1.reading(RUN + "-002"),
    astro2.reading(RUN + "-003"),
]
batch2 = [
    astro1.alert(RUN + "-004", fmt.ALERT_CHECK_VITALS, "Heart rate 118 bpm, well above baseline (62 bpm)."),
    astro2.reading(RUN + "-005"),
    astro2.summary(RUN + "-006", "Slept 7.1 h. Resting heart rate 74 bpm. 45 min of exercise done."),
]
batch3 = [
    batch1[0],                        # REPEATED id: the same record sent a second time
    astro1.reading(RUN + "-007"),
    astro2.alert(RUN + "-008", fmt.ALERT_INFO, "Daily summary ready."),
]

status, before = get_json(NASA_URL + "/stats")
if status != 200:
    sys.exit(f"Could not reach the NASA receiver at {NASA_URL}. Is 'python app.py' running?")
print("/stats before:", before)
print()

all_confirmed = True
for name, batch in (("Batch 1", batch1), ("Batch 2", batch2), ("Batch 3", batch3)):
    sent_ids = [record[fmt.FIELD_ID] for record in batch]
    status, answer = post_json(NASA_URL + "/batch", {"records": batch})
    print(f"{name}: sent {len(batch)} records {sent_ids}")
    print(f"   -> HTTP {status} {answer}")
    print()
    if status != 200 or answer.get("saved") != sent_ids:
        all_confirmed = False

status, after = get_json(NASA_URL + "/stats")
print("/stats after: ", after)
print()

# 9 records were posted, but one id was posted twice, so only 8 are new.
grew_by = after["total"] - before["total"]
print("Records posted: 9   Different ids: 8   NASA total grew by:", grew_by)
print("Every batch confirmed all the ids it sent:", all_confirmed)
if all_confirmed and grew_by == 8:
    print("PASS: the repeated id was confirmed again but not saved twice.")
else:
    print("FAIL: expected every id to be confirmed and the total to grow by exactly 8.")
    sys.exit(1)
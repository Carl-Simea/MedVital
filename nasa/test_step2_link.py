"""
test_step2_link.py - STEP 2 test.

Link down -> batches fail (HTTP 503) and nothing is saved.
Link up   -> the same batch succeeds.

Run it (with the receiver already running in another terminal):
    python test_step2_link.py
    python test_step2_link.py https://xxxx.trycloudflare.com   (through the tunnel)
"""

import sys
import uuid

import record_format as fmt
from fake_data import DEFAULT_NASA_URL, get_json, post_json, two_fake_astronauts

NASA_URL = (sys.argv[1] if len(sys.argv) > 1 else DEFAULT_NASA_URL).rstrip("/")
RUN = "step2-" + uuid.uuid4().hex[:8]   # a different random prefix on every run

astro1, astro2 = two_fake_astronauts()
batch = [
    astro1.reading(RUN + "-001"),
    astro2.reading(RUN + "-002"),
    astro2.alert(RUN + "-003", fmt.ALERT_RETURN_NOW, "Solar event in progress. Head back in."),
]
sent_ids = [record[fmt.FIELD_ID] for record in batch]


def total_saved():
    status, stats = get_json(NASA_URL + "/stats")
    return stats["total"]


status, state = get_json(NASA_URL + "/link")
if status != 200:
    sys.exit(f"Could not reach the NASA receiver at {NASA_URL}. Is 'python app.py' running?")
print("Link at the start:", state)
start_total = total_saved()
print("NASA total at the start:", start_total)
print()

try:
    # --- 1. Link DOWN: the batch must fail and nothing must be saved ---------
    status, answer = post_json(NASA_URL + "/link", {"up": False})
    print("POST /link {'up': False}  -> HTTP", status, answer)

    status_down, answer = post_json(NASA_URL + "/batch", {"records": batch})
    total_down = total_saved()
    print(f"POST /batch ({len(batch)} records) -> HTTP", status_down, answer)
    print("NASA total while the link is down:", total_down, "(must still be", str(start_total) + ")")
    print()

    # --- 2. Link UP: the very same batch must now be saved -------------------
    status, answer = post_json(NASA_URL + "/link", {"up": True})
    print("POST /link {'up': True}   -> HTTP", status, answer)

    status_up, answer = post_json(NASA_URL + "/batch", {"records": batch})
    total_up = total_saved()
    print(f"POST /batch ({len(batch)} records) -> HTTP", status_up, answer)
    print("NASA total after the link is back:", total_up, "(must be", str(start_total + len(batch)) + ")")
    print()
finally:
    # Whatever happens, do not leave the link down.
    post_json(NASA_URL + "/link", {"up": True})

down_ok = status_down == 503 and total_down == start_total
up_ok = status_up == 200 and answer.get("saved") == sent_ids and total_up == start_total + len(batch)
print("Link down -> batch failed with 503 and saved nothing:", down_ok)
print("Link up   -> batch succeeded and every id was confirmed:", up_ok)
if down_ok and up_ok:
    print("PASS")
else:
    print("FAIL")
    sys.exit(1)
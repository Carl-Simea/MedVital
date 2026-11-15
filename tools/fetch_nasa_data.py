#!/usr/bin/env python3
"""Download the three NASA datasets MedVital uses and turn them into small files under data/nasa/.

    python tools/fetch_nasa_data.py            (needs internet; standard library only; ~10-20 min)

1. Curiosity RAD (NASA PDS PPI, MSL-M-RAD-3-RDR-V1.0): every observation's dosimetry
   [DOSIMETRY_TOTAL_DOSE_E] (tissue-equivalent plastic, microGray/hour) and _B (silicon), with its UTC
   time (and Mars local time on the surface). Cruise days spread over the 2011-2012 cruise, and a run
   of consecutive surface sols. Files are streamed and only the dosimetry lines are kept.
2. DONKI (NASA CCMC, https://ccmc.gsfc.nasa.gov/DONKI-API/get/...): flares, CMEs, solar energetic
   particle events, geomagnetic storms, interplanetary shocks and WSA-ENLIL arrival forecasts for one
   60-day window (DONKI's maximum per query).
3. NASA OSDR search API (https://osdr.nasa.gov/osdr/data/search): study metadata for each health
   risk MedVital covers. OSDR returns study records, not astronaut values: MedVital links to them.

Nothing is invented: every output row keeps the URL it came from.
"""

from __future__ import annotations

import csv
import gzip
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import zlib
from datetime import UTC, datetime
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "nasa"
UA = {"User-Agent": "MedVital-NASA-Space-Apps-2026 (education)", "Accept-Encoding": "gzip"}

RAD_BASE = "https://pds-ppi.igpp.ucla.edu/data/MSL-M-RAD-3-RDR-V1.0/DATA/"
RAD_CRUISE_FILES = 20  # spread evenly over the cruise
RAD_SURFACE_DIR = "SOL_00000_00089/"
RAD_SURFACE_SKIP = 10  # skip the first sols after landing (commissioning)
RAD_SURFACE_FILES = 30  # consecutive sols

DONKI_BASE = "https://ccmc.gsfc.nasa.gov/DONKI-API/get/"
DONKI_START, DONKI_END = "2024-05-01", "2024-06-29"  # 60 days near solar maximum (incl. the May 2024 storms)
DONKI_KINDS = ("FLR", "CME", "SEP", "GST", "IPS", "WSAEnlilSimulations")

OSDR_URL = "https://osdr.nasa.gov/osdr/data/search"
OSDR_TOPICS = {
    "bone": "bone loss spaceflight",
    "muscle": "muscle atrophy spaceflight",
    "heart": "cardiovascular spaceflight",
    "radiation": "space radiation",
    "sleep": "sleep circadian spaceflight",
    "immune": "immune spaceflight",
    "eye": "ocular spaceflight",
    "kidney": "kidney stone spaceflight",
}


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def get(url: str, timeout: float = 120) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (fixed NASA hosts)
                body = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
                return body
        except Exception as exc:  # noqa: BLE001
            if attempt == 3:
                raise
            log(f"  retry {url} ({exc})")
            time.sleep(3 * (attempt + 1))
    raise RuntimeError("unreachable")


def links(url: str) -> list[str]:
    html = get(url).decode("utf-8", "replace")
    return [h for h in re.findall(r'href="([^"?/][^"?]*)"', html)]


# ------------------------------------------------------------------------------------------- RAD
SECTION = re.compile(r"^\[([A-Z_]+): (\d+)\]")


def stream_lines(url: str):
    """Yield decoded lines of a (possibly gzip-encoded) remote text file without keeping it in memory."""
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=300) as r:  # noqa: S310
        dec = zlib.decompressobj(16 + zlib.MAX_WBITS) if r.headers.get("Content-Encoding") == "gzip" else None
        buf = b""
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            if dec:
                chunk = dec.decompress(chunk)
            buf += chunk
            *lines, buf = buf.split(b"\n")
            for line in lines:
                yield line.decode("ascii", "replace").rstrip("\r")
        if buf:
            yield buf.decode("ascii", "replace")


def parse_rad(url: str, phase: str, index: int) -> list[dict]:
    rows: dict[str, dict] = {}
    section, obs, want = None, None, None
    for line in stream_lines(url):
        m = SECTION.match(line)
        if m:
            section, obs = m.group(1), m.group(2)
            want = section if section in ("DOSIMETRY_TOTAL_DOSE_E", "DOSIMETRY_TOTAL_DOSE_B") else None
            if section == "OBSERVATION":
                rows.setdefault(obs, {"phase": phase, "file_index": index, "file": url.rsplit("/", 1)[1], "obs": int(obs)})
            continue
        if section == "OBSERVATION" and "=" in line:
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"')
            if k in ("START_OBS_UTC", "START_OBS_MARS", "QC"):
                rows[obs][k] = v
        elif want and line.strip():
            try:
                value = float(line.split()[0])
            except ValueError:
                continue
            rows.setdefault(obs, {"phase": phase, "file_index": index, "obs": int(obs)})
            rows[obs]["dose_e_ugy_h" if want.endswith("_E") else "dose_b_ugy_h"] = value
            want = None
    return [r for r in rows.values() if "dose_e_ugy_h" in r or "dose_b_ugy_h" in r]


def fetch_rad() -> None:
    cruise = sorted(f for f in links(RAD_BASE + "CRUISE/") if f.startswith("RAD_RDR_") and f.endswith(".TXT"))
    step = max(1, len(cruise) // RAD_CRUISE_FILES)
    picks = [("cruise", RAD_BASE + "CRUISE/" + f) for f in cruise[::step][:RAD_CRUISE_FILES]]
    surface = sorted(f for f in links(RAD_BASE + RAD_SURFACE_DIR) if f.startswith("RAD_RDR_") and f.endswith(".TXT"))
    picks += [("surface", RAD_BASE + RAD_SURFACE_DIR + f)
              for f in surface[RAD_SURFACE_SKIP:RAD_SURFACE_SKIP + RAD_SURFACE_FILES]]
    log(f"RAD: {len(cruise)} cruise files (taking {sum(p == 'cruise' for p, _ in picks)}), "
        f"{len(surface)} files in {RAD_SURFACE_DIR} (taking {sum(p == 'surface' for p, _ in picks)})")
    rows: list[dict] = []
    counters = {"cruise": 0, "surface": 0}
    for phase, url in picks:
        counters[phase] += 1
        got = parse_rad(url, phase, counters[phase])
        rows += got
        log(f"  {phase} {counters[phase]:>2}: {url.rsplit('/', 1)[1]} -> {len(got)} observations")
    cols = ["phase", "file_index", "file", "obs", "START_OBS_UTC", "START_OBS_MARS", "QC", "dose_e_ugy_h", "dose_b_ugy_h"]
    with open(OUT / "rad_dose.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    log(f"RAD: wrote {len(rows)} observations to data/nasa/rad_dose.csv")


# ----------------------------------------------------------------------------------------- DONKI
KEEP = {
    "FLR": ("flrID", "beginTime", "peakTime", "endTime", "classType", "sourceLocation", "activeRegionNum", "link", "linkedEvents"),
    "CME": ("activityID", "startTime", "sourceLocation", "activeRegionNum", "note", "link", "linkedEvents", "cmeAnalyses"),
    "SEP": ("sepID", "eventTime", "instruments", "link", "linkedEvents"),
    "GST": ("gstID", "startTime", "allKpIndex", "link", "linkedEvents"),
    "IPS": ("activityID", "location", "eventTime", "instruments", "link", "linkedEvents"),
    "WSAEnlilSimulations": ("simulationID", "modelCompletionTime", "estimatedShockArrivalTime", "impactList", "link", "cmeInputs"),
}


def slim(kind: str, rec: dict) -> dict:
    out = {k: rec.get(k) for k in KEEP[kind]}
    if kind == "CME" and out.get("cmeAnalyses"):  # keep only the most accurate analysis
        best = [a for a in out["cmeAnalyses"] if a.get("isMostAccurate")] or out["cmeAnalyses"][:1]
        out["cmeAnalyses"] = [{k: a.get(k) for k in ("time21_5", "speed", "halfAngle", "type", "isMostAccurate")}
                              for a in best]
    if kind == "WSAEnlilSimulations" and out.get("cmeInputs"):
        out["cmeInputs"] = [{k: c.get(k) for k in ("cmeStartTime", "speed", "halfAngle")} for c in out["cmeInputs"]]
    if isinstance(out.get("note"), str):
        out["note"] = out["note"][:400]
    return out


def fetch_donki() -> None:
    result = {"source": DONKI_BASE, "startDate": DONKI_START, "endDate": DONKI_END,
              "retrieved_at": datetime.now(UTC).isoformat(timespec="seconds"), "events": {}}
    for kind in DONKI_KINDS:
        url = f"{DONKI_BASE}{kind}?startDate={DONKI_START}&endDate={DONKI_END}"
        data = json.loads(get(url) or b"[]")
        result["events"][kind] = [slim(kind, r) for r in data]
        log(f"DONKI {kind}: {len(data)}")
    (OUT / "donki_2024-05-01_2024-06-29.json").write_text(json.dumps(result, indent=1))


# ------------------------------------------------------------------------------------------ OSDR
def fetch_osdr() -> None:
    out = {"source": OSDR_URL, "retrieved_at": datetime.now(UTC).isoformat(timespec="seconds"), "topics": {}}
    for topic, term in OSDR_TOPICS.items():
        url = OSDR_URL + "?" + urllib.parse.urlencode({"term": term, "type": "cgene", "size": 12})
        raw = json.loads(get(url))
        hits = (raw.get("hits") or {}).get("hits") or []
        studies = []
        for h in hits:
            s = h.get("_source") or {}
            acc = s.get("Accession") or s.get("Study Identifier") or h.get("_id")
            studies.append({
                "accession": acc,
                "title": s.get("Study Title"),
                "organism": s.get("organism") or s.get("Organism"),
                "project_type": s.get("Project Type"),
                "flight_program": s.get("Flight Program"),
                "mission": (s.get("Mission") or {}).get("Name") if isinstance(s.get("Mission"), dict) else s.get("Mission"),
                "factors": s.get("Study Factor Name"),
                "assay": s.get("Study Assay Technology Type"),
                "description": (s.get("Study Description") or "")[:600],
                "link": f"https://osdr.nasa.gov/bio/repo/data/studies/{acc}" if acc else None,
            })
        out["topics"][topic] = {"term": term, "url": url, "total": (raw.get("hits") or {}).get("total"), "studies": studies}
        if hits and topic == "bone":
            out["_field_names_seen"] = sorted((hits[0].get("_source") or {}).keys())
        log(f"OSDR {topic}: {len(studies)} studies")
    (OUT / "osdr_studies.json").write_text(json.dumps(out, indent=1))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    which = sys.argv[1:] or ["donki", "osdr", "rad"]
    if "donki" in which:
        fetch_donki()
    if "osdr" in which:
        fetch_osdr()
    if "rad" in which:
        fetch_rad()
    log("done")


if __name__ == "__main__":
    main()

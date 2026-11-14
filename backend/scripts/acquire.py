"""Acquire public NASA sources with checksums and manifests; optionally register them in a station DB.

Examples (from backend/):
  python scripts/acquire.py donki SEP 2024-05-10 2024-05-14 --db station.db
  python scripts/acquire.py osdr 569 LSDS-7_Complete_Blood_Count_CBC.upload_SUBMITTED.csv --db station.db
  python scripts/acquire.py rad AAREADME.TXT

The NASA API key is read from NASA_API_KEY (default DEMO_KEY, which is heavily rate-limited) and is
removed from every stored URL. Files are written unmodified under data/raw/<sha256>/ (git-ignored).
Network access is needed only here; nothing else in MEDVITAL requires it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from medvital.acquisition import donki  # noqa: E402
from medvital.acquisition.download import download  # noqa: E402
from medvital.acquisition.ingest import ingest_donki, osdr_download_url, rad_url, register_artifact  # noqa: E402

DEFAULT_STORE = Path(__file__).resolve().parents[2] / "data" / "raw"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--store", default=str(DEFAULT_STORE), help="Directory for unmodified source files")
    p.add_argument("--db", help="Station SQLite file to register artifacts/events in (optional)")
    sub = p.add_subparsers(dest="source", required=True)
    d = sub.add_parser("donki")
    d.add_argument("endpoint", choices=donki.SUPPORTED)
    d.add_argument("start")
    d.add_argument("end")
    o = sub.add_parser("osdr")
    o.add_argument("study", type=int)
    o.add_argument("filename")
    r = sub.add_parser("rad")
    r.add_argument("relative_path", help="Path under MSL-M-RAD-3-RDR-V1.0/, e.g. AAREADME.TXT")
    args = p.parse_args(argv)

    if args.source == "donki":
        key = os.environ.get("NASA_API_KEY", "DEMO_KEY")
        got = download(
            donki.endpoint_url(args.endpoint, args.start, args.end, key),
            args.store,
            source_system="NASA DONKI",
            dataset_id=f"DONKI/{args.endpoint}",
            original_filename=f"donki_{args.endpoint}_{args.start}_{args.end}.json",
        )
    elif args.source == "osdr":
        got = download(
            osdr_download_url(args.study, args.filename),
            args.store,
            source_system="NASA OSDR",
            dataset_id=f"OSD-{args.study}",
            original_filename=args.filename,
        )
    else:
        got = download(
            rad_url(args.relative_path),
            args.store,
            source_system="PDS PPI (MSL RAD)",
            dataset_id="MSL-M-RAD-3-RDR-V1.0",
            original_filename=Path(args.relative_path).name,
        )

    result: dict = {"path": str(got.path), "artifact": got.artifact.model_dump(mode="json")}
    if args.db:
        from medvital.db.sqlite import SqliteObservationRepository

        repo = SqliteObservationRepository(args.db)
        try:
            if args.source == "donki":
                rep = ingest_donki(repo, args.endpoint, got.path, got.artifact)
            else:
                rep = register_artifact(repo, got.artifact)
        finally:
            repo.close()
        result["ingest"] = rep.__dict__
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

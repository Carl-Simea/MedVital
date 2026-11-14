"""Register acquired artifacts and ingest parsed records (one write path, auditable outcomes)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from medvital.acquisition import donki
from medvital.acquisition.download import verify
from medvital.core.records import ProcessingStep, SourceArtifact
from medvital.db.repository import DocumentRepository
from medvital.records_service import store_artifact, store_environmental_event

OSDR_FILES_API = "https://osdr.nasa.gov/osdr/data/osd/files/{n}"
OSDR_DOWNLOAD = "https://osdr.nasa.gov/geode-py/ws/studies/OSD-{n}/download?source=datamanager&file={name}"
RAD_BASE = "https://pds-ppi.igpp.ucla.edu/data/MSL-M-RAD-3-RDR-V1.0/"


@dataclass
class IngestReport:
    artifact_id: str
    artifact_status: str
    accepted: int = 0
    duplicate: int = 0
    rejected: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def ingest_donki(
    repo: DocumentRepository,
    endpoint: str,
    path: str | Path,
    artifact: SourceArtifact,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> IngestReport:
    if not verify(path, artifact):
        raise ValueError("file does not match its manifest checksum; refusing to ingest")
    report = donki.parse(endpoint, Path(path).read_bytes(), artifact)
    step = ProcessingStep(
        at=now(),
        step=f"parse:donki_{endpoint}",
        tool=donki.PARSER,
        detail=f"{len(report.events)} events, {len(report.skipped)} skipped",
    )
    recorded = artifact.model_copy(update={"processing_history": [*artifact.processing_history, step]})
    art = store_artifact(repo, recorded)
    out = IngestReport(artifact_id=art.record_id, artifact_status=art.status, skipped=report.skipped)
    if art.status == "rejected":
        out.rejected.append(f"artifact: {art.error}")
        return out
    for event in report.events:
        event = event.model_copy(update={"source_artifact_id": recorded.artifact_id})
        r = store_environmental_event(repo, event)
        if r.status == "accepted":
            out.accepted += 1
        elif r.status == "duplicate":
            out.duplicate += 1
        else:
            out.rejected.append(f"{event.source_event_id}: {r.error}")
    return out


def register_artifact(repo: DocumentRepository, artifact: SourceArtifact) -> IngestReport:
    """For sources acquired but not parsed into records (OSDR tables, RAD products): manifest only."""
    r = store_artifact(repo, artifact)
    return IngestReport(
        artifact_id=r.record_id, artifact_status=r.status, rejected=[r.error] if r.error else []
    )


def osdr_download_url(study: int, filename: str) -> str:
    from urllib.parse import quote

    return OSDR_DOWNLOAD.format(n=study, name=quote(filename))


def rad_url(relative_path: str) -> str:
    rel = relative_path.lstrip("/")
    if ".." in rel or "://" in rel:
        raise ValueError("relative PDS path expected")
    return RAD_BASE + rel

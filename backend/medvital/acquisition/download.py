"""Checksummed, provenance-recording downloads (standard library only)."""

from __future__ import annotations

import hashlib
import os
import re
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from medvital.core.records import ProcessingStep, SourceArtifact

IMPORT_METHOD = "medvital.acquisition.download v1"
SECRET_PARAMS = ("api_key", "apikey", "key", "token")
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]")

Fetcher = Callable[[str], tuple[bytes, str | None]]  # url -> (body, content_type)


def http_fetch(url: str, timeout: float = 60.0) -> tuple[bytes, str | None]:
    if not url.startswith("https://"):
        raise ValueError("only https:// sources are fetched")
    req = urllib.request.Request(url, headers={"User-Agent": "medvital-acquisition/1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (https enforced above)
        return resp.read(), resp.headers.get("Content-Type")


def redact_url(url: str) -> str:
    """Drop secret query parameters (e.g. NASA api_key) before the URL is stored anywhere."""
    parts = urllib.parse.urlsplit(url)
    query = [
        (k, v)
        for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in SECRET_PARAMS
    ]
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))


@dataclass(frozen=True)
class Downloaded:
    path: Path
    artifact: SourceArtifact


def download(
    url: str,
    store_dir: str | os.PathLike[str],
    *,
    source_system: str,
    dataset_id: str,
    original_filename: str,
    dataset_version: str | None = None,
    license_note: str | None = None,
    fetch: Fetcher = http_fetch,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> Downloaded:
    """Fetch ``url``, store the bytes unmodified at ``store_dir/<sha256>/<filename>``, return the manifest.

    An existing file with the same checksum is reused, never overwritten.
    """
    body, content_type = fetch(url)
    retrieved = now()
    digest = hashlib.sha256(body).hexdigest()
    safe_name = _SAFE_NAME.sub("_", original_filename)[:200] or "download.bin"
    target_dir = Path(store_dir) / digest
    target = target_dir / safe_name
    if target.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise RuntimeError(f"stored file {target} does not match its checksum; refusing to overwrite")
    else:
        target_dir.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".part")
        tmp.write_bytes(body)
        os.replace(tmp, target)
    clean_url = redact_url(url)
    artifact = SourceArtifact(
        artifact_id=SourceArtifact.make_id(clean_url, digest),
        source_system=source_system,
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        source_url=clean_url,
        original_filename=original_filename,
        sha256=digest,
        size_bytes=len(body),
        content_type=content_type,
        retrieved_at=retrieved,
        import_method=IMPORT_METHOD,
        license_note=license_note,
        processing_history=[
            ProcessingStep(at=retrieved, step="download", tool=IMPORT_METHOD, detail=f"{len(body)} bytes"),
            ProcessingStep(at=retrieved, step="checksum", tool="sha256", detail=digest),
        ],
    )
    return Downloaded(path=target, artifact=artifact)


def verify(path: str | os.PathLike[str], artifact: SourceArtifact) -> bool:
    """True when the stored file still matches its manifest checksum."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest() == artifact.sha256

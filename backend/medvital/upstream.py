"""Station -> upstream delivery (M3): local SQLite stays authoritative; upstream gets a copy.

Design (docs/DECISIONS.md D-026):

* **No second queue.** Observations are append-only with a monotonic local ``server_seq``, so
  the outbox *is* "every row after the destination's acknowledged cursor". A restart loses
  nothing; the cursor is persisted per destination.
* **Existing contract.** Delivery uses ``POST /api/v1/sync/push`` (the same contract the browser
  outbox uses), so any MEDVITAL gateway — and later the Cloudflare Worker — can be the upstream.
* **Idempotent.** Mutation ids are uuid5(destination, observation id): a retried batch is a
  harmless ``duplicate`` upstream.
* **Never silent.** Upstream refusals are written to an append-only failure log and the cursor
  moves past them (they cannot succeed unchanged); network errors and 5xx leave the cursor
  untouched; a 401/403 stops delivery without advancing.
* **Mixed versions.** ``None``-valued fields are omitted from payloads so an older upstream that
  does not know an additive field still accepts the record (D-025).

Standard library only.
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Literal, Protocol
from uuid import UUID, uuid5

from medvital.db.repository import ObservationRepository, StoredObservation, UpstreamStateRepository

_NAMESPACE = UUID("3d5f0c3e-1b7a-4f2e-9d55-0b6c2b9e4a71")
MAX_BATCH = 500  # matches core.sync.MAX_PUSH_BATCH


class UpstreamUnavailable(Exception):
    """No usable answer (network error, timeout, 5xx). Retry later; nothing was acknowledged."""


class UpstreamRefused(Exception):
    """The upstream refused the caller (401/403 or another non-422 4xx). Stop; do not advance."""


class UpstreamBatchInvalid(Exception):
    """HTTP 422 for the whole batch: some record is structurally invalid for the upstream."""


class UpstreamTransport(Protocol):
    def push(self, client_id: str, mutations: list[dict[str, Any]]) -> list[dict[str, Any]]: ...


class HttpUpstreamTransport:
    def __init__(self, base_url: str, timeout: float = 10.0, bearer_token: str | None = None) -> None:
        self.url = base_url.rstrip("/") + "/api/v1/sync/push"
        self.timeout = timeout
        self._token = bearer_token  # M5 (Auth0/station credentials); never logged

    def push(self, client_id: str, mutations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        body = json.dumps({"client_id": client_id, "mutations": mutations}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        req = urllib.request.Request(self.url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 (operator-supplied URL)
                return json.loads(resp.read().decode("utf-8"))["results"]
        except urllib.error.HTTPError as exc:
            if exc.code == 422:
                raise UpstreamBatchInvalid(f"HTTP 422 from {self.url}") from exc
            if 400 <= exc.code < 500:
                raise UpstreamRefused(f"HTTP {exc.code} from {self.url}") from exc
            raise UpstreamUnavailable(f"HTTP {exc.code} from {self.url}") from exc
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError) as exc:
            raise UpstreamUnavailable(f"{type(exc).__name__}: {getattr(exc, 'reason', exc)}") from exc


class HttpDocumentTransport(HttpUpstreamTransport):
    def __init__(self, base_url: str, timeout: float = 10.0, bearer_token: str | None = None) -> None:
        super().__init__(base_url, timeout, bearer_token)
        self.url = base_url.rstrip("/") + "/api/v1/sync/documents/push"

    def push_documents(self, client_id: str, documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        body = json.dumps({"client_id": client_id, "documents": documents}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        req = urllib.request.Request(self.url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 (operator-supplied URL)
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if 400 <= exc.code < 500:
                raise UpstreamRefused(f"HTTP {exc.code} from {self.url}") from exc
            raise UpstreamUnavailable(f"HTTP {exc.code} from {self.url}") from exc
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise UpstreamUnavailable(f"{type(exc).__name__}: {getattr(exc, 'reason', exc)}") from exc


@dataclass
class UpstreamReport:
    destination: str
    status: Literal["complete", "unavailable", "refused", "protocol_error"] = "complete"
    sent: int = 0
    accepted: int = 0
    duplicate: int = 0
    rejected: int = 0
    cursor_before: int = 0
    cursor_after: int = 0
    error: str | None = None


class _Repo(ObservationRepository, UpstreamStateRepository, Protocol): ...


def mutation_for(destination: str, row: StoredObservation) -> dict[str, Any]:
    return {
        "mutation_id": str(uuid5(_NAMESPACE, f"{destination}|{row.observation.id}")),
        "observation": row.observation.model_dump(mode="json", exclude_none=True),
    }


def _push_isolating(
    transport: UpstreamTransport, client_id: str, destination: str, batch: list[StoredObservation]
) -> list[dict[str, Any]]:
    """Push a batch; on a batch-level 422, push one at a time so one bad record cannot block the rest."""
    mutations = [mutation_for(destination, r) for r in batch]
    try:
        return transport.push(client_id, mutations)
    except UpstreamBatchInvalid:
        results = []
        for row, m in zip(batch, mutations, strict=True):
            try:
                results.extend(transport.push(client_id, [m]))
            except UpstreamBatchInvalid as exc:
                results.append(
                    {"observation_id": str(row.observation.id), "status": "rejected", "error": str(exc)}
                )
        return results


def push_upstream(
    repo: _Repo,
    transport: UpstreamTransport,
    *,
    destination: str,
    client_id: str,
    batch_size: int = MAX_BATCH,
    max_batches: int | None = None,
) -> UpstreamReport:
    if not 1 <= batch_size <= MAX_BATCH:
        raise ValueError(f"batch_size must be 1..{MAX_BATCH}")
    cursor = repo.upstream_cursor(destination)
    report = UpstreamReport(destination=destination, cursor_before=cursor, cursor_after=cursor)
    batches = 0
    while max_batches is None or batches < max_batches:
        rows = repo.changes_since(cursor, limit=batch_size)
        if not rows:
            break
        try:
            results = _push_isolating(transport, client_id, destination, rows)
        except UpstreamUnavailable as exc:
            report.status, report.error = "unavailable", str(exc)
            break
        except UpstreamRefused as exc:
            report.status, report.error = "refused", str(exc)
            break
        by_id = {str(r.get("observation_id")): r for r in results}
        missing = [r for r in rows if str(r.observation.id) not in by_id]
        if missing:
            report.status = "protocol_error"
            report.error = (
                f"upstream returned no result for {len(missing)} observation(s); cursor not advanced"
            )
            break
        for row in rows:
            result = by_id[str(row.observation.id)]
            status = result.get("status")
            if status == "accepted":
                report.accepted += 1
            elif status == "duplicate":
                report.duplicate += 1
            else:
                report.rejected += 1
                repo.record_upstream_failure(
                    destination, row.observation.id, row.server_seq, str(result.get("error") or status)
                )
        report.sent += len(rows)
        cursor = rows[-1].server_seq
        repo.set_upstream_cursor(destination, cursor)
        report.cursor_after = cursor
        batches += 1
    return report


class DocumentTransport(Protocol):
    def push_documents(self, client_id: str, documents: list[dict[str, Any]]) -> list[dict[str, Any]]: ...


def push_documents_upstream(
    repo: Any,
    transport: DocumentTransport,
    *,
    destination: str,
    client_id: str,
    batch_size: int = MAX_BATCH,
) -> UpstreamReport:
    """Replicate non-observation records (missions, commands, events, findings, ...) upstream.

    Same semantics as observations: separate persisted cursor (``<destination>#documents``),
    refusals audited and skipped, outages leave the cursor untouched. A record refused only because
    its parent has not arrived yet (e.g. a command status before its command) is audited like any
    other refusal; the parent is earlier in the same feed, so in-order delivery avoids this case.
    """
    cursor_key = f"{destination}#documents"
    cursor = repo.upstream_cursor(cursor_key)
    report = UpstreamReport(destination=cursor_key, cursor_before=cursor, cursor_after=cursor)
    while True:
        rows = repo.document_changes_since(cursor, limit=batch_size)
        if not rows:
            break
        try:
            results = transport.push_documents(
                client_id, [{"kind": r.kind, "document": r.payload} for r in rows]
            )
        except UpstreamUnavailable as exc:
            report.status, report.error = "unavailable", str(exc)
            break
        except UpstreamRefused as exc:
            report.status, report.error = "refused", str(exc)
            break
        if len(results) != len(rows):
            report.status, report.error = "protocol_error", "result count does not match pushed documents"
            break
        for row, result in zip(rows, results, strict=True):
            status = result.get("status")
            if status == "accepted":
                report.accepted += 1
            elif status == "duplicate":
                report.duplicate += 1
            else:
                report.rejected += 1
                repo.record_upstream_failure(
                    cursor_key, _doc_uuid(row.kind, row.key), row.seq, str(result.get("error"))
                )
        report.sent += len(rows)
        cursor = rows[-1].seq
        repo.set_upstream_cursor(cursor_key, cursor)
        report.cursor_after = cursor
    return report


PageFetcher = Any  # callable(cursor:int) -> {"changes": [...], "next_cursor": int, "has_more": bool}


def http_document_page_fetcher(base_url: str, timeout: float = 10.0, bearer_token: str | None = None):
    def fetch(cursor: int) -> dict[str, Any]:
        url = f"{base_url.rstrip('/')}/api/v1/sync/documents/pull?cursor={int(cursor)}&limit=500"
        headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else {}
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (operator-supplied URL)
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if 400 <= exc.code < 500:
                raise UpstreamRefused(f"HTTP {exc.code} from {url}") from exc
            raise UpstreamUnavailable(f"HTTP {exc.code} from {url}") from exc
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise UpstreamUnavailable(f"{type(exc).__name__}: {getattr(exc, 'reason', exc)}") from exc

    return fetch


def pull_documents(
    repo: Any, fetch_page: PageFetcher, *, source: str, registry: Any = None
) -> UpstreamReport:
    """Pull records from another station (e.g. ground -> spacecraft RETURN_NOW) through validation.

    Cursor ``<source>#documents-pull`` advances only past changes that were processed; refusals are
    audited. A child arriving before its parent cannot happen within one source's ordered feed.
    """
    from medvital.records_service import replicate

    key = f"{source}#documents-pull"
    cursor = repo.upstream_cursor(key)
    report = UpstreamReport(destination=key, cursor_before=cursor, cursor_after=cursor)
    while True:
        try:
            page = fetch_page(cursor)
        except UpstreamUnavailable as exc:
            report.status, report.error = "unavailable", str(exc)
            break
        except UpstreamRefused as exc:
            report.status, report.error = "refused", str(exc)
            break
        for change in page["changes"]:
            result = replicate(repo, repo, change["kind"], change["document"], registry)
            if result.status == "accepted":
                report.accepted += 1
            elif result.status == "duplicate":
                report.duplicate += 1
            else:
                report.rejected += 1
                repo.record_upstream_failure(
                    key, _doc_uuid(change["kind"], change["key"]), change["seq"], result.error or ""
                )
            report.sent += 1
            cursor = change["seq"]
        cursor = max(cursor, int(page["next_cursor"]))
        repo.set_upstream_cursor(key, cursor)
        report.cursor_after = cursor
        if not page["has_more"]:
            break
    return report


def _doc_uuid(kind: str, key: str) -> UUID:
    try:
        return UUID(key)
    except ValueError:
        return uuid5(_NAMESPACE, f"doc|{kind}|{key}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Push this station's observations to an upstream MEDVITAL gateway."
    )
    p.add_argument("--db", required=True, help="Path to this station's SQLite store")
    p.add_argument("--upstream", required=True, help="Upstream base URL, e.g. http://spacecraft.local:8000")
    p.add_argument("--destination", required=True, help="Stable name for the upstream (cursor key)")
    p.add_argument("--client-id", required=True, help="This station's id as reported upstream")
    args = p.parse_args(argv)
    from medvital.db.sqlite import SqliteObservationRepository

    repo = SqliteObservationRepository(args.db)
    try:
        report = push_upstream(
            repo, HttpUpstreamTransport(args.upstream), destination=args.destination, client_id=args.client_id
        )
    finally:
        repo.close()
    print(json.dumps(report.__dict__))
    return 0 if report.status == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())

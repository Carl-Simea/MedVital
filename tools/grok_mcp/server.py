"""MEDVITAL Grok MCP server: xAI Grok as an *advisory* second reviewer for Claude Code.

* Transport: MCP over stdio (newline-delimited JSON-RPC 2.0). Standard library only.
* API: xAI Responses API, ``POST {XAI_BASE_URL}/responses`` (docs.x.ai, read 2026-11-14).
* Key: read only from the ``XAI_API_KEY`` environment variable; never logged, echoed or stored.
* Explicit use: tools run only when Claude calls them; nothing is sent automatically.
* Data boundary (docs/DECISIONS.md D-027): only source code, design documents, simulated data and
  public research data with a cited source. Payloads that look like measured/private health
  records are refused before any network call.

Grok's output is advice to a developer, never a MEDVITAL observation, analysis result or alert.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

SERVER_NAME = "medvital-grok"
SERVER_VERSION = "0.1.0"
SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
DEFAULT_BASE_URL = "https://api.x.ai/v1"
DEFAULT_MODEL = (
    "grok-4.7"  # docs.x.ai/docs/models: "frontier model for coding, agentic tasks, and knowledge work"
)
DEFAULT_TIMEOUT_S = 120.0
DEFAULT_MAX_OUTPUT_TOKENS = 4000
MAX_CONTENT_CHARS = 200_000
MAX_RETRIES = 2  # for 429 and 5xx
MAX_BACKOFF_S = 30.0

CLASSIFICATIONS = ("source_code", "architecture_or_docs", "simulated_data", "public_research_data")

BASE_INSTRUCTIONS = (
    "You are an independent reviewer consulted by another AI assistant working on MEDVITAL, an offline-first "
    "astronaut health observation platform. Rules: never invent data, measurements, citations or thresholds; "
    "never give a medical diagnosis or clinical threshold; keep simulated, measured and modeled data "
    "distinct; "
    "separate clearly (1) evidence you can see in the provided material, (2) missing information, and "
    "(3) uncertainty or assumptions. Be specific and concise; cite file/line or section when possible."
)

TOOL_FOCUS = {
    "grok_review_code": "Review the code for correctness bugs, security issues, error handling, test gaps.",
    "grok_review_architecture": "Review the architecture/design for risks, coupling, failure modes and gaps.",
    "grok_analyze_data": (
        "Analyse the provided simulated or public data: structure, quality, missingness, units, statistical "
        "observations. Do not interpret anything clinically."
    ),
    "grok_research_review": (
        "Review the research claims/plan against the cited sources: what is supported, what is not, and what "
        "must be verified at the primary source."
    ),
}

# Heuristics for content that must not leave the machine (D-027).
_MEASURED_RE = re.compile(r"""["']?data_origin["']?\s*[:=]\s*["']?measured\b""", re.IGNORECASE)
_SECRET_RES = (
    re.compile(r"xai-[A-Za-z0-9]{20,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)


class ToolError(Exception):
    """A failure reported back to Claude as an MCP tool error (isError: true)."""


def _log(message: str) -> None:
    # stderr only (stdout carries the protocol). Never pass request headers or the key here.
    print(f"[{SERVER_NAME}] {message}", file=sys.stderr, flush=True)


def _redact(text: str) -> str:
    key = os.environ.get("XAI_API_KEY") or ""
    if len(key) >= 8:
        text = text.replace(key, "[REDACTED]")
    for rx in _SECRET_RES:
        text = rx.sub("[REDACTED]", text)
    return text


# --------------------------------------------------------------------------- data boundary


def check_payload(arguments: dict[str, Any], tool: str) -> tuple[str, str]:
    """Validate tool arguments; return (content, classification) or raise ToolError. No network."""
    content = arguments.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ToolError("`content` (non-empty string) is required")
    if len(content) > MAX_CONTENT_CHARS:
        raise ToolError(f"`content` exceeds {MAX_CONTENT_CHARS} characters; send a smaller excerpt")
    classification = arguments.get("data_classification")
    if classification not in CLASSIFICATIONS:
        raise ToolError(f"`data_classification` must be one of {', '.join(CLASSIFICATIONS)}")
    if tool == "grok_analyze_data" and classification not in ("simulated_data", "public_research_data"):
        raise ToolError("grok_analyze_data accepts only simulated_data or public_research_data")
    if classification == "public_research_data" and not str(arguments.get("public_source") or "").strip():
        raise ToolError("public_research_data requires `public_source` (DOI, accession or URL)")
    if _MEASURED_RE.search(content) and classification != "public_research_data":
        raise ToolError(
            "content contains measured-origin records; only simulated data or public research data with a "
            "cited source may be sent to Grok (D-027)"
        )
    if any(rx.search(content) for rx in _SECRET_RES):
        raise ToolError(
            "content appears to contain a secret or private key; remove it before consulting Grok"
        )
    return content, classification


# --------------------------------------------------------------------------- xAI client


@dataclass
class GrokResult:
    text: str
    model: str
    response_id: str | None
    status: str | None
    usage: dict[str, Any]
    latency_s: float


def _api_key() -> str:
    key = os.environ.get("XAI_API_KEY", "").strip()
    if not key:
        raise ToolError("XAI_API_KEY is not set in the MCP server's environment")
    if key.startswith("${"):
        raise ToolError("XAI_API_KEY was not expanded (placeholder received); set it and restart Claude Code")
    return key


def _base_url() -> str:
    url = os.environ.get("XAI_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    if not (
        url.startswith("https://") or url.startswith("http://127.0.0.1") or url.startswith("http://localhost")
    ):
        raise ToolError("XAI_BASE_URL must be https:// (or a localhost test server)")
    return url


def _extract_text(body: dict[str, Any]) -> str:
    parts: list[str] = []
    for item in body.get("output") or []:
        contents = (item.get("content") or []) if isinstance(item, dict) else []
        for c in contents:
            if isinstance(c, dict) and c.get("type") == "output_text" and isinstance(c.get("text"), str):
                parts.append(c["text"])
    if not parts and isinstance(body.get("output_text"), str):
        parts.append(body["output_text"])
    return "\n".join(parts).strip()


def call_grok(instructions: str, user_input: str, *, sleep=time.sleep) -> GrokResult:
    key = _api_key()
    url = _base_url() + "/responses"
    model = os.environ.get("XAI_MODEL", DEFAULT_MODEL)
    timeout = float(os.environ.get("XAI_TIMEOUT_S", DEFAULT_TIMEOUT_S))
    payload = {
        "model": model,
        "instructions": instructions,
        "input": user_input,
        "max_output_tokens": int(os.environ.get("XAI_MAX_OUTPUT_TOKENS", DEFAULT_MAX_OUTPUT_TOKENS)),
        "store": False,
    }
    data = json.dumps(payload).encode("utf-8")
    started = time.monotonic()
    waited = 0.0
    for attempt in range(MAX_RETRIES + 1):
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (validated URL)
                body = json.loads(resp.read().decode("utf-8"))
            text = _extract_text(body)
            if not text:
                raise ToolError(f"Grok returned no text output (status={body.get('status')!r})")
            return GrokResult(
                text=text,
                model=str(body.get("model") or model),
                response_id=body.get("id"),
                status=body.get("status"),
                usage=body.get("usage") or {},
                latency_s=round(time.monotonic() - started, 2),
            )
        except urllib.error.HTTPError as exc:
            detail = _redact(exc.read().decode("utf-8", "replace")[:500]) if exc.fp else ""
            if exc.code in (401, 403):
                raise ToolError(
                    f"xAI authentication failed (HTTP {exc.code}); check XAI_API_KEY, team credits and "
                    f"model access. API said: {detail or '(no body)'}"
                ) from None
            if exc.code == 429 or exc.code >= 500:
                if attempt < MAX_RETRIES:
                    retry_after = exc.headers.get("Retry-After") if exc.headers else None
                    delay = (
                        float(retry_after)
                        if (retry_after or "").replace(".", "", 1).isdigit()
                        else 2.0 ** (attempt + 1)
                    )
                    delay = min(delay, MAX_BACKOFF_S - waited)
                    if delay > 0:
                        _log(
                            f"HTTP {exc.code}; retrying in {delay:.1f}s (attempt {attempt + 1}/{MAX_RETRIES})"
                        )
                        sleep(delay)
                        waited += delay
                        continue
                kind = "rate limited" if exc.code == 429 else "server error"
                raise ToolError(
                    f"xAI {kind} (HTTP {exc.code}) after {attempt + 1} attempt(s): {detail}"
                ) from None
            raise ToolError(f"xAI API error (HTTP {exc.code}): {detail}") from None
        except TimeoutError:
            raise ToolError(f"xAI request timed out after {timeout:.0f}s") from None
        except urllib.error.URLError as exc:
            raise ToolError(f"cannot reach xAI API: {_redact(str(exc.reason))}") from None
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ToolError("xAI API returned a non-JSON response") from None
    raise ToolError("xAI request failed")  # unreachable


# --------------------------------------------------------------------------- MCP tools


def _schema(extra: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "Material to review (code, design text or data)."},
            "data_classification": {
                "type": "string",
                "enum": list(CLASSIFICATIONS),
                "description": "What the content is. Real/private astronaut health data is never allowed.",
            },
            "question": {"type": "string", "description": "What you want Grok to focus on."},
            **extra,
        },
        "required": ["content", "data_classification", *required],
        "additionalProperties": False,
    }


TOOLS = [
    {
        "name": "grok_review_code",
        "description": "Ask xAI Grok for an independent code review (advisory second opinion).",
        "inputSchema": _schema({}, []),
    },
    {
        "name": "grok_review_architecture",
        "description": "Ask xAI Grok to review an architecture or design document (advisory).",
        "inputSchema": _schema({}, []),
    },
    {
        "name": "grok_analyze_data",
        "description": "Ask xAI Grok to analyse SIMULATED or PUBLIC research data only (advisory).",
        "inputSchema": _schema(
            {
                "public_source": {
                    "type": "string",
                    "description": "DOI/accession/URL; required for public data.",
                }
            },
            ["question"],
        ),
    },
    {
        "name": "grok_research_review",
        "description": "Ask xAI Grok to critique research claims or a research plan against cited sources.",
        "inputSchema": _schema(
            {
                "public_source": {
                    "type": "string",
                    "description": "DOI/accession/URL of the sources under review.",
                }
            },
            ["question"],
        ),
    },
]
TOOL_NAMES = {t["name"] for t in TOOLS}


def run_tool(name: str, arguments: dict[str, Any], *, sleep=time.sleep) -> dict[str, Any]:
    if name not in TOOL_NAMES:
        raise ToolError(f"unknown tool {name!r}")
    content, classification = check_payload(arguments, name)
    question = str(arguments.get("question") or "").strip()
    source = str(arguments.get("public_source") or "").strip()
    user_input = (
        f"Task: {TOOL_FOCUS[name]}\n"
        f"Data classification: {classification}\n"
        + (f"Public source: {source}\n" if source else "")
        + (f"Question: {question}\n" if question else "")
        + f"\n--- MATERIAL ---\n{content}"
    )
    result = call_grok(BASE_INSTRUCTIONS, user_input, sleep=sleep)
    header = (
        f"[Independent advisory review by xAI Grok, model={result.model}, response_id={result.response_id}, "
        f"status={result.status}, latency={result.latency_s}s. Not a MEDVITAL observation or result; verify "
        f"before acting.]"
    )
    metadata = {
        "provider": "xAI",
        "model": result.model,
        "response_id": result.response_id,
        "status": result.status,
        "usage": result.usage,
        "latency_s": result.latency_s,
        "data_classification": classification,
    }
    return {
        "content": [
            {"type": "text", "text": f"{header}\n\n{result.text}"},
            {"type": "text", "text": "metadata: " + json.dumps(metadata, sort_keys=True)},
        ],
        "isError": False,
    }


# --------------------------------------------------------------------------- JSON-RPC over stdio


def handle(message: dict[str, Any], *, sleep=time.sleep) -> dict[str, Any] | None:
    """Return a JSON-RPC response, or None for notifications."""
    method = message.get("method")
    msg_id = message.get("id")
    if msg_id is None:  # notification (e.g. notifications/initialized): no reply
        return None

    def ok(result: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    if method == "initialize":
        requested = (message.get("params") or {}).get("protocolVersion")
        version = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else SUPPORTED_PROTOCOL_VERSIONS[0]
        return ok(
            {
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": (
                    "Grok tools are an optional, advisory second opinion. Call them only when an independent "
                    "review adds value. Never send real or private astronaut health data."
                ),
            }
        )
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": TOOLS})
    if method == "tools/call":
        params = message.get("params") or {}
        try:
            return ok(run_tool(str(params.get("name")), params.get("arguments") or {}, sleep=sleep))
        except ToolError as exc:
            return ok(
                {
                    "content": [{"type": "text", "text": f"Grok tool error: {_redact(str(exc))}"}],
                    "isError": True,
                }
            )
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": -32601, "message": f"method not found: {method}"},
    }


def serve(stdin=sys.stdin, stdout=sys.stdout) -> None:
    _log(
        f"started (model={os.environ.get('XAI_MODEL', DEFAULT_MODEL)}, "
        f"key set={bool(os.environ.get('XAI_API_KEY'))})"
    )
    for line in stdin:
        line = line.lstrip("﻿").strip()  # tolerate a UTF-8 BOM (e.g. PowerShell pipes)
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        else:
            if not isinstance(message, dict):
                error = {"code": -32600, "message": "invalid request"}
                reply = {"jsonrpc": "2.0", "id": None, "error": error}
                stdout.write(json.dumps(reply) + "\n")
                stdout.flush()
                continue
            try:
                reply = handle(message)
            except Exception as exc:  # never crash the server; never leak internals with secrets
                _log(f"internal error: {type(exc).__name__}")
                reply = {
                    "jsonrpc": "2.0",
                    "id": message.get("id"),
                    "error": {"code": -32603, "message": "internal error"},
                }
        if reply is not None:
            stdout.write(json.dumps(reply) + "\n")
            stdout.flush()


if __name__ == "__main__":
    # MCP messages are UTF-8 JSON lines. Windows defaults stdio to the ANSI code page and "\r\n";
    # force UTF-8 and "\n" so non-ASCII content (e.g. "µGy") survives the round trip.
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    serve()

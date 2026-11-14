"""Tests for the MEDVITAL Grok MCP server. Mocked xAI API only: no real network calls.

Run: python -m unittest discover -s tools/grok_mcp/tests -v   (standard library only)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SERVER_PATH = HERE.parent / "server.py"
sys.path.insert(0, str(HERE.parent))

import server  # noqa: E402

FAKE_KEY = "test-key-NOT-REAL-0123456789"


def ok_body(text="Looks fine.", model="grok-4.7"):
    return {
        "id": "resp_test_1",
        "object": "response",
        "model": model,
        "status": "completed",
        "output": [
            {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}
        ],
        "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    }


class FakeXAI:
    """Scripted responses: list of (status, body_dict_or_str, headers, delay_s)."""

    def __init__(self):
        self.script = []
        self.requests = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length", 0))
                fake.requests.append(
                    {
                        "path": self.path,
                        "auth": self.headers.get("Authorization"),
                        "body": json.loads(self.rfile.read(length) or b"{}"),
                    }
                )
                status, body, headers, delay = fake.script.pop(0) if fake.script else (200, ok_body(), {}, 0)
                if delay:
                    time.sleep(delay)
                payload = (body if isinstance(body, str) else json.dumps(body)).encode()
                try:
                    self.send_response(status)
                    for k, v in headers.items():
                        self.send_header(k, v)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass

            def log_message(self, *args):
                pass

        self.httpd = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/v1"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class Base(unittest.TestCase):
    def setUp(self):
        self.fake = FakeXAI()
        self.env = mock.patch.dict(
            os.environ,
            {"XAI_API_KEY": FAKE_KEY, "XAI_BASE_URL": self.fake.url, "XAI_TIMEOUT_S": "5"},
            clear=False,
        )
        self.env.start()
        os.environ.pop("XAI_MODEL", None)
        self.sleeps = []

    def tearDown(self):
        self.env.stop()
        self.fake.close()

    def call(self, name="grok_review_code", **arguments):
        arguments.setdefault("content", "def add(a, b):\n    return a + b\n")
        arguments.setdefault("data_classification", "source_code")
        msg = {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        reply = server.handle(msg, sleep=self.sleeps.append)
        return reply["result"]

    def text(self, result):
        return "\n".join(c["text"] for c in result["content"])


class ProtocolTests(Base):
    def test_initialize_negotiates_version(self):
        r = server.handle(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}}
        )
        self.assertEqual(r["result"]["protocolVersion"], "2025-03-26")
        self.assertIn("tools", r["result"]["capabilities"])
        r = server.handle(
            {"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {"protocolVersion": "1999-01-01"}}
        )
        self.assertEqual(r["result"]["protocolVersion"], server.SUPPORTED_PROTOCOL_VERSIONS[0])

    def test_tools_list_and_notifications(self):
        names = [
            t["name"]
            for t in server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"]
        ]
        self.assertEqual(
            names,
            ["grok_review_code", "grok_review_architecture", "grok_analyze_data", "grok_research_review"],
        )
        self.assertIsNone(server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        self.assertEqual(server.handle({"jsonrpc": "2.0", "id": 3, "method": "ping"})["result"], {})
        self.assertEqual(
            server.handle({"jsonrpc": "2.0", "id": 4, "method": "nope"})["error"]["code"], -32601
        )

    def test_unknown_tool_is_tool_error(self):
        r = self.call(name="grok_delete_everything")
        self.assertTrue(r["isError"])
        self.assertEqual(self.fake.requests, [])


class SuccessTests(Base):
    def test_successful_review_returns_text_and_model_info(self):
        self.fake.script.append((200, ok_body("No bugs found."), {}, 0))
        r = self.call(question="check edge cases")
        self.assertFalse(r["isError"])
        out = self.text(r)
        self.assertIn("No bugs found.", out)
        self.assertIn("model=grok-4.7", out)
        meta = json.loads(r["content"][1]["text"].removeprefix("metadata: "))
        self.assertEqual(
            (meta["provider"], meta["model"], meta["response_id"]), ("xAI", "grok-4.7", "resp_test_1")
        )
        self.assertEqual(meta["usage"]["total_tokens"], 15)
        (req,) = self.fake.requests
        self.assertEqual(req["path"], "/v1/responses")
        self.assertEqual(req["auth"], f"Bearer {FAKE_KEY}")
        self.assertEqual(req["body"]["model"], "grok-4.7")
        self.assertIs(req["body"]["store"], False)
        self.assertIn("def add", req["body"]["input"])
        self.assertIn("never give a medical diagnosis", req["body"]["instructions"])

    def test_model_override(self):
        with mock.patch.dict(os.environ, {"XAI_MODEL": "grok-build-0.1"}):
            self.fake.script.append((200, ok_body(model="grok-build-0.1"), {}, 0))
            self.call()
        self.assertEqual(self.fake.requests[0]["body"]["model"], "grok-build-0.1")


class ErrorTests(Base):
    def test_auth_failure(self):
        self.fake.script.append((401, {"error": "bad key"}, {}, 0))
        r = self.call()
        self.assertTrue(r["isError"])
        self.assertIn("authentication failed", self.text(r))
        self.assertEqual(len(self.fake.requests), 1)  # no retry on auth failure

    def test_rate_limit_retries_with_retry_after_then_succeeds(self):
        self.fake.script += [(429, {"error": "slow down"}, {"Retry-After": "1"}, 0), (200, ok_body(), {}, 0)]
        r = self.call()
        self.assertFalse(r["isError"])
        self.assertEqual(self.sleeps, [1.0])
        self.assertEqual(len(self.fake.requests), 2)

    def test_rate_limit_exhausted(self):
        self.fake.script += [(429, {"error": "slow down"}, {}, 0)] * 3
        r = self.call()
        self.assertTrue(r["isError"])
        self.assertIn("rate limited", self.text(r))
        self.assertEqual(len(self.fake.requests), 3)
        self.assertEqual(self.sleeps, [2.0, 4.0])

    def test_server_error_retried(self):
        self.fake.script += [(503, "unavailable", {}, 0), (200, ok_body(), {}, 0)]
        self.assertFalse(self.call()["isError"])

    def test_bad_request_reports_api_message(self):
        self.fake.script.append((400, {"error": "unknown model"}, {}, 0))
        r = self.call()
        self.assertTrue(r["isError"])
        self.assertIn("unknown model", self.text(r))

    def test_timeout(self):
        with mock.patch.dict(os.environ, {"XAI_TIMEOUT_S": "0.3"}):
            self.fake.script.append((200, ok_body(), {}, 1.5))
            r = self.call()
        self.assertTrue(r["isError"])
        self.assertIn("timed out", self.text(r))

    def test_empty_output_is_an_error(self):
        self.fake.script.append((200, {"id": "x", "status": "incomplete", "output": []}, {}, 0))
        self.assertIn("no text output", self.text(self.call()))

    def test_missing_or_placeholder_key_makes_no_request(self):
        for value in ("", "${XAI_API_KEY}"):
            with mock.patch.dict(os.environ, {"XAI_API_KEY": value}):
                r = self.call()
            self.assertTrue(r["isError"])
        self.assertEqual(self.fake.requests, [])

    def test_insecure_base_url_rejected(self):
        with mock.patch.dict(os.environ, {"XAI_BASE_URL": "http://evil.example.com/v1"}):
            self.assertIn("must be https", self.text(self.call()))
        self.assertEqual(self.fake.requests, [])

    def test_key_is_redacted_from_echoed_errors(self):
        self.fake.script.append((400, {"error": f"invalid request for key {FAKE_KEY}"}, {}, 0))
        out = self.text(self.call())
        self.assertNotIn(FAKE_KEY, out)
        self.assertIn("[REDACTED]", out)


class DataBoundaryTests(Base):
    def assert_refused(self, needle, **arguments):
        r = self.call(**arguments)
        self.assertTrue(r["isError"], r)
        self.assertIn(needle, self.text(r))
        self.assertEqual(self.fake.requests, [], "refused payloads must never reach the network")

    def test_measured_records_refused(self):
        payload = json.dumps({"value": 61, "provenance": {"data_origin": "measured", "source_ref": "x"}})
        self.assert_refused(
            "measured-origin",
            content=payload,
            data_classification="simulated_data",
            name="grok_analyze_data",
            question="q",
        )

    def test_classification_required_and_enforced(self):
        self.assert_refused("data_classification", data_classification="astronaut_records")
        self.assert_refused(
            "accepts only", name="grok_analyze_data", data_classification="source_code", question="q"
        )

    def test_public_data_needs_a_source(self):
        self.assert_refused(
            "public_source",
            name="grok_analyze_data",
            data_classification="public_research_data",
            question="q",
            content="a,b\n1,2\n",
        )

    def test_secrets_refused(self):
        self.assert_refused("secret", content="XAI = 'xai-" + "A" * 30 + "'")

    def test_size_limit(self):
        self.assert_refused("exceeds", content="x" * (server.MAX_CONTENT_CHARS + 1))

    def test_public_data_with_source_allowed(self):
        self.fake.script.append((200, ok_body(), {}, 0))
        r = self.call(
            name="grok_analyze_data",
            data_classification="public_research_data",
            question="units?",
            public_source="https://osdr.nasa.gov/bio/repo/data/studies/OSD-804",
            content="a,b\n1,2\n",
        )
        self.assertFalse(r["isError"])
        self.assertIn("OSD-804", self.fake.requests[0]["body"]["input"])


class EndToEndStdioTests(Base):
    def test_stdio_session_and_key_never_in_stderr(self):
        self.fake.script.append((200, ok_body("E2E ok"), {}, 0))
        messages = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "0"},
                },
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "grok_review_architecture",
                    "arguments": {
                        "content": "Station A pushes to B.",
                        "data_classification": "architecture_or_docs",
                    },
                },
            },
        ]
        proc = subprocess.run(
            [sys.executable, "-I", str(SERVER_PATH)],
            input="\n".join(json.dumps(m) for m in messages) + "\nnot json\n",
            capture_output=True,
            text=True,
            timeout=30,
            env=dict(os.environ),
        )
        replies = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual([r.get("id") for r in replies], [1, 2, 3, None])
        self.assertEqual(replies[0]["result"]["serverInfo"]["name"], "medvital-grok")
        self.assertEqual(len(replies[1]["result"]["tools"]), 4)
        self.assertIn("E2E ok", replies[2]["result"]["content"][0]["text"])
        self.assertEqual(replies[3]["error"]["code"], -32700)
        self.assertNotIn(FAKE_KEY, proc.stdout)
        self.assertNotIn(FAKE_KEY, proc.stderr)

    def test_utf8_bom_and_non_object_messages_over_raw_bytes(self):
        """Windows robustness: BOM-prefixed input, non-ASCII content, and a JSON array line."""
        self.fake.script.append((200, ok_body("Einheit µGy/h ok"), {}, 0))
        call = {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "grok_review_code",
                "arguments": {"content": "RATE_UNIT = 'µGy/h'  # Δt", "data_classification": "source_code"},
            },
        }
        raw = "﻿" + json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}) + "\n[1, 2]\n"
        raw += json.dumps(call, ensure_ascii=False) + "\n"
        proc = subprocess.run(
            [sys.executable, "-I", str(SERVER_PATH)],
            input=raw.encode("utf-8"),
            capture_output=True,
            timeout=30,
            env=dict(os.environ),
        )
        lines = proc.stdout.decode("utf-8").split("\n")
        self.assertFalse(any(line.endswith("\r") for line in lines), "replies must use \\n line endings")
        replies = [json.loads(line) for line in lines if line.strip()]
        self.assertEqual([r.get("id") for r in replies], [1, None, 5])
        self.assertEqual(replies[1]["error"]["code"], -32600)
        self.assertIn("µGy/h", replies[2]["result"]["content"][0]["text"])
        self.assertIn("'µGy/h'  # Δt", self.fake.requests[0]["body"]["input"])


if __name__ == "__main__":
    unittest.main()

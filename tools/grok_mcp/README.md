# MEDVITAL Grok MCP server

This server exposes **xAI Grok** to Claude Code as an *optional, advisory* second reviewer. Claude stays the primary
model. Grok runs only when Claude explicitly calls one of its tools. Grok's answers are developer advice, never MEDVITAL
observations, analysis results or alerts.

* **No dependencies.** Python 3.11+ standard library only (MCP over stdio, HTTPS via `urllib`).
* **API.** xAI Responses API, `POST https://api.x.ai/v1/responses`. Format checked against docs.x.ai on 2026-11-14.
* **Key.** Read only from the `XAI_API_KEY` environment variable. It is never logged, returned, or written to any file.
  `.mcp.json` contains only the `${XAI_API_KEY}` placeholder.
* **Data boundary.** Defined in docs/DECISIONS.md D-027 and summarised below.

## Tools

| Tool | Use | Required arguments |
|---|---|---|
| `grok_review_code` | Independent code review | `content`, `data_classification` |
| `grok_review_architecture` | Design and architecture critique | `content`, `data_classification` |
| `grok_analyze_data` | Look at **simulated or public** data (structure, quality, units). Non-clinical. | `content`, `data_classification` (`simulated_data` or `public_research_data`), `question`; `public_source` required for public data |
| `grok_research_review` | Critique research claims or plans against cited sources | `content`, `data_classification`, `question` |

`data_classification` must be one of `source_code`, `architecture_or_docs`, `simulated_data` or
`public_research_data`.

Every result contains two text blocks:
* Grok's answer, under an attribution header (model, response id, status, latency);
* a `metadata:` JSON block with provider, model, response id, status, token usage and latency.

## Data boundary (enforced before any network call)

* Real or private astronaut health data is **never** sent. Content containing `data_origin: measured` records is refused
  unless it is declared `public_research_data` **with** a `public_source`.
* Content that looks like a secret (`xai-…`, `sk-…`, PEM private keys) is refused.
* Maximum 200,000 characters per call.
* The request asks xAI not to store the response (`store: false`).

These checks are heuristics, not a guarantee. The person or agent calling the tool is still responsible for what it sends.

## Configuration (environment variables)

| Variable | Default | Notes |
|---|---|---|
| `XAI_API_KEY` | — | Required |
| `XAI_MODEL` | `grok-4.7` | docs.x.ai describes it as the frontier model "for coding, agentic tasks, and knowledge work". Check the console for the models your key can use. |
| `XAI_TIMEOUT_S` | `120` | Per-request timeout |
| `XAI_MAX_OUTPUT_TOKENS` | `4000` | Sent as `max_output_tokens` |
| `XAI_BASE_URL` | `https://api.x.ai/v1` | Must be `https://` (localhost is allowed for tests) |

## Error handling

| Condition | Behaviour |
|---|---|
| 401/403 | Tool error saying "authentication failed". No retry, and the key is never echoed. |
| 429 and 5xx | Up to 2 retries. Honours `Retry-After` if the server sends it, otherwise waits 2 s then 4 s. Total waiting is capped at 30 s. |
| Timeout, unreachable host, non-JSON reply, empty output | Clear tool error |
| 400 | The API's message, truncated, with the key redacted |

The xAI pages read did **not** document rate-limit status codes or headers, so 429 handling is generic.

## Installation and registration

1. Set the key as a **User** environment variable (already done on this machine). Do not put it in any file.
2. **Restart VS Code / Claude Code** so the new variable is inherited. Without a restart, the server reports
   "XAI_API_KEY was not expanded".
3. Open Claude Code with the canonical repository folder `Documents/MEDVITAL` as the project. Project servers come from
   `.mcp.json` at the project root.
4. When Claude Code asks, approve the project server `medvital-grok`.
5. Check it: run `/mcp` in Claude Code. It should list `medvital-grok` with 4 tools.

Alternative without a project file (stored privately in `~/.claude.json`), if the `claude` CLI is on PATH:

```
claude mcp add --transport stdio --scope local medvital-grok -- python -I C:/Users/<you>/Documents/MEDVITAL/tools/grok_mcp/server.py
```

The server reads `XAI_API_KEY` from the environment Claude Code passes to it. Do **not** use `--env XAI_API_KEY=<key>`,
because that writes the key into `~/.claude.json`.

## Tests

```
python -m unittest discover -s tools/grok_mcp/tests -v
```

22 tests run against a local fake xAI server and never contact the real API. They cover:
* MCP protocol and stdio end to end;
* success path and request shape;
* model override;
* auth, rate-limit, 5xx, 400 and timeout handling;
* missing or placeholder key;
* insecure base URL;
* key redaction (also in stderr);
* every data-boundary refusal, with an assertion that no request was sent.

## What this does not do

* It does not replace Claude, and it does not touch `ANTHROPIC_BASE_URL`.
* It does not modify or call the MEDVITAL backend, analysis engine or data stores.
* It does not call Grok automatically.

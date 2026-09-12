# ChatGPT Web HWPX MCP

## P0 — Minimal Remote Streamable-HTTP Server, Tool-Scan Compatibility Probe, Read/Write Capability Boundary & First Custom-App Registration Test

This repository is intentionally small. **P0 does not edit HWPX yet.**

Its only job is to answer four questions:

1. Can ChatGPT Web scan a remote `/mcp` Streamable HTTP endpoint?
2. Does ChatGPT discover the read-only probe?
3. Does ChatGPT discover the deliberately side-effecting write probe?
4. On the current ChatGPT plan/account, can that write tool actually be invoked?

## Tools

| Tool | Side effect | Purpose |
|---|---:|---|
| `probe_read` | No | Connectivity/tool-call probe |
| `probe_capabilities` | No | P0 metadata |
| `probe_write` | Yes | Creates one temporary `.txt` file on the remote host |

`probe_write` is optionally guarded by `P0_WRITE_NONCE`.

## Local run

### uv

```bash
uv sync
P0_WRITE_NONCE=test-only uv run python server.py
```

Windows PowerShell:

```powershell
uv sync
$env:P0_WRITE_NONCE="test-only"
uv run python server.py
```

Health check:

```text
http://127.0.0.1:8000/health
```

MCP endpoint:

```text
http://127.0.0.1:8000/mcp
```

Optional local MCP client:

```bash
uv run python test_client.py
```

## Docker

```bash
docker build -t chatgpt-web-hwpx-mcp-p0 .
docker run --rm -p 8000:8000 \
  -e P0_WRITE_NONCE='replace-me' \
  chatgpt-web-hwpx-mcp-p0
```

Do **not** expose an unauthenticated write-capable prototype indefinitely on the public Internet.

## Remote deployment

Any host that can run a Docker container and expose HTTPS can work. The included `render.yaml` is a minimal Render blueprint.

Expected public endpoints:

```text
https://YOUR-HOST/health
https://YOUR-HOST/mcp
```

TLS should be terminated by the deployment platform/reverse proxy.

## ChatGPT Web registration

Use the custom MCP/server registration screen.

**Name**

```text
ChatGPT Web HWPX MCP
```

**Description**

```text
Experimental HWPX document MCP. P0 tests remote Streamable-HTTP connectivity and ChatGPT read/write action boundaries; real HWPX editing is added in later phases.
```

**MCP server URL**

```text
https://YOUR-HOST/mcp
```

**Authentication**

For the shortest P0 experiment, use `No authentication` only while the server is temporary and protected from abuse. `P0_WRITE_NONCE` guards the write probe at the tool level, but it is **not a substitute for real MCP authentication**.

A later phase should add OAuth or another supported MCP authentication scheme before real documents are accepted.

## Exact P0 test sequence

### T0 — health

Open:

```text
https://YOUR-HOST/health
```

Expected:

```json
{"status":"ok","project":"ChatGPT Web HWPX MCP","version":"0.1.0-p0"}
```

### T1 — Scan Tools

Register `https://YOUR-HOST/mcp`.

PASS if ChatGPT discovers:

```text
probe_read
probe_capabilities
probe_write
```

If tool scan fails, record the HTTP status/error before changing the server.

### T2 — read boundary

Ask ChatGPT:

```text
Call probe_read with message "ChatGPT Web P0 read test".
```

PASS if the tool returns `ok=true`.

### T3 — write discovery

Check whether `probe_write` is visible/eligible as an action.

This is separate from whether the account is permitted to execute it.

### T4 — write execution

Ask explicitly:

```text
Use probe_write to create a P0 test artifact containing "ChatGPT Web write boundary test".
```

If `P0_WRITE_NONCE` is configured, provide the nonce when prompted/required.

Interpretation:

- **Tool absent**: client/plan/tool-scan boundary.
- **Tool visible but blocked by ChatGPT**: account/product write-action boundary.
- **Tool executes and returns artifact_id**: write action path is working.
- **Tool reaches server but errors**: server/tool bug.

## P0 PASS matrix

| Check | Required for transport PASS? | Required for full P0 PASS? |
|---|---:|---:|
| `/health` reachable over HTTPS | Yes | Yes |
| ChatGPT tool scan succeeds | Yes | Yes |
| `probe_read` executes | Yes | Yes |
| `probe_write` is discovered | No | Yes |
| `probe_write` executes | No | Account-dependent |

Because ChatGPT plan capabilities can differ, record the final state as two independent verdicts:

```text
TRANSPORT = PASS / FAIL
WRITE-ACTION = PASS / PRODUCT-BLOCKED / SERVER-FAIL
```

## Why P0 does not accept HWPX files

A file uploaded to ChatGPT and a file path on a remote MCP host are not the same filesystem. P1 therefore needs an explicit file-transfer/document-store contract instead of pretending a local path such as `/mnt/data/foo.hwpx` exists remotely.

P1 should introduce:

```text
ingest_document
inspect_document
export_document
```

with a `document_id`, temporary object storage, validation, and a safe download/attachment handoff.

## Security notes

- Never put secrets into tool descriptions or return values.
- Keep `/health` non-sensitive.
- Do not expose `probe_write` without at least the nonce for a public P0.
- Delete the temporary deployment after the test if authentication is disabled.
- Before real HWPX documents are supported, add proper auth, per-user isolation, size limits, content-type checks, retention limits, and audit logging.

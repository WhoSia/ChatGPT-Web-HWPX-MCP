# ChatGPT Web HWPX MCP

Remote Streamable-HTTP MCP for creating and handing off HWPX documents from ChatGPT Web.

## Current phase

**P0 is closed / PASS.** ChatGPT Web successfully discovered the custom MCP, executed native read and write actions, and created a remote artifact. The full receipt is preserved in [`P0_TEST_LEDGER.md`](./P0_TEST_LEDGER.md).

**P1 is active.** The current server adds an explicit document-custody boundary:

```text
ChatGPT Web
→ remote MCP
→ create_document
→ opaque document_id
→ bounded ephemeral object store
→ HWPX structural validation
→ export_document
→ short-lived signed download URL
```

P1 intentionally does **not** accept arbitrary existing HWPX uploads yet.

## P1 tools

| Tool | Side effect | Purpose |
|---|---:|---|
| `probe_read` | No | Remote connectivity probe |
| `probe_capabilities` | No | Current capability boundary |
| `create_document` | Yes | Materialize a small HWPX and return an opaque `document_id` |
| `inspect_document` | No | Validate and inspect one stored document |
| `export_document` | No* | Return a short-lived signed download URL |
| `delete_document` | Yes | Delete the HWPX and metadata from ephemeral storage |

`export_document` does not mutate the document itself, but it creates a temporary bearer-style download capability.

## HWPX materialization

P1 uses `python-hwpx >= 6.4` for document creation. Generated files are then checked independently as ZIP/XML packages.

The validator requires at least:

```text
mimetype
version.xml
META-INF/container.xml
Contents/content.hpf
Contents/header.xml
Contents/section0.xml
```

It also verifies that `mimetype` is the first ZIP entry, is stored without compression, and equals `application/hwp+zip`.

## Storage contract

P1 never exposes server filesystem paths to the model.

Each document receives an opaque ID such as:

```text
doc_<random>
```

The default backend is a bounded **ephemeral filesystem object store** under `/tmp`. Metadata is stored separately from the HWPX bytes. Documents expire automatically; the default retention window is 30 minutes.

This backend is intentionally replaceable. A later phase can move the same `document_id` contract to S3-compatible object storage without changing the MCP-facing API.

## Download handoff

`export_document` returns a signed URL of the form:

```text
https://HOST/artifacts/<document_id>?exp=<unix-time>&sig=<hmac>
```

The link expires quickly, is capped by the document retention deadline, and responses use `Cache-Control: private, no-store`.

## Security boundary

P1 is still a prototype. The public MCP transport is not yet backed by OAuth/per-user identity.

The document tools therefore require a server-side `P1_ACCESS_TOKEN`, while download URLs use a separate `P1_DOWNLOAD_SECRET`. These are **prototype guards, not final authentication**.

Until proper MCP authentication and per-user isolation are added:

- do not ingest existing personal or confidential HWPX files;
- do not treat the ephemeral backend as durable storage;
- do not expose arbitrary filesystem paths;
- keep document size and retention bounded;
- use only opaque document IDs and signed export links.

Existing-document upload/ingest is intentionally deferred until that boundary is stronger.

## Local run

Install dependencies:

```bash
pip install -r requirements.txt
```

Run with temporary local secrets:

```bash
P1_ACCESS_TOKEN=local-access \
P1_DOWNLOAD_SECRET=local-download-secret \
P1_PUBLIC_BASE_URL=http://127.0.0.1:8000 \
python server.py
```

PowerShell:

```powershell
$env:P1_ACCESS_TOKEN="local-access"
$env:P1_DOWNLOAD_SECRET="local-download-secret"
$env:P1_PUBLIC_BASE_URL="http://127.0.0.1:8000"
python server.py
```

Endpoints:

```text
http://127.0.0.1:8000/health
http://127.0.0.1:8000/mcp
```

Run the full local P1 lifecycle smoke test:

```bash
P1_ACCESS_TOKEN=local-access RUN_P1_WRITE_TEST=1 python test_client.py
```

Unit test:

```bash
python -m unittest -v test_p1.py
```

## Docker

```bash
docker build -t chatgpt-web-hwpx-mcp .
docker run --rm -p 8000:8000 \
  -e P1_ACCESS_TOKEN='replace-me' \
  -e P1_DOWNLOAD_SECRET='replace-me-too' \
  chatgpt-web-hwpx-mcp
```

## Deployment

The repository keeps `render.yaml` as the canonical deployment description, but there is deliberately **no one-click Deploy to Render button** in this README anymore. P1 has write-capable document custody, so deployment should be deliberate and secrets must be configured correctly.

The existing canonical Render service still has the historical P0-era service slug:

```text
https://chatgpt-web-hwpx-mcp-p0.onrender.com
```

Renaming or migrating that service is deferred until P1 is stable so the already-registered ChatGPT MCP URL is not broken unnecessarily.

## CI

Two workflows are active:

- `P1 HWPX lifecycle CI`: dependency install, compile, unit validation, local MCP lifecycle (`create → inspect → export → delete`).
- `P1 Render remote MCP verification`: public `/health`, MCP handshake, tool discovery, and read probe against the deployed service.

Remote CI intentionally does not receive the P1 write secret.

## Next phases

The current direction is:

```text
P1   minimal valid HWPX + document_id + signed export
P1.x authenticated ingest + ZIP/XML safety + per-user isolation
P2   structured edits and formatting
P3   tables / images / equations
P4   renderer-oracle and Hancom fidelity validation
```

A production-grade system should add OAuth or equivalent MCP authentication, user/session isolation, persistent object storage, quotas, audit logging, and a real Hancom rendering/fidelity oracle before accepting sensitive documents.

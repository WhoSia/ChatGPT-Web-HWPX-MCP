# ChatGPT Web HWPX MCP

Remote Streamable-HTTP MCP for creating and handing off HWPX documents from ChatGPT Web.

## Current phase

**P0 is closed / PASS.** ChatGPT Web discovered the custom MCP, executed native read/write actions, and created a remote artifact. See [`P0_TEST_LEDGER.md`](./P0_TEST_LEDGER.md).

**P1 is closed at the server/lifecycle layer.** Minimal valid HWPX materialization, opaque `document_id` custody, structural validation, signed export, and deletion are implemented. See [`P1_TEST_LEDGER.md`](./P1_TEST_LEDGER.md).

**P1.1 is active.** Authentication has moved out of MCP tool arguments and onto the MCP transport:

```text
ChatGPT Web
→ OAuth 2.1 authorization-code + PKCE/DCR
→ Authorization: Bearer <short-lived access token>
→ remote MCP /mcp
→ create_document
→ caller-owned opaque document_id
→ bounded ephemeral object store
→ structural HWPX validation
→ export_document
→ short-lived signed artifact URL
```

The P1.1 receipts are tracked in [`P11_TEST_LEDGER.md`](./P11_TEST_LEDGER.md).

P1.1 intentionally does **not** accept arbitrary existing HWPX uploads yet.

## MCP tools

| Tool | Side effect | Purpose |
|---|---:|---|
| `probe_read` | No | Authenticated connectivity probe |
| `probe_capabilities` | No | Current capability/auth boundary |
| `create_document` | Yes | Materialize a small HWPX and return an opaque `document_id` |
| `inspect_document` | No | Validate and inspect one caller-owned document |
| `export_document` | No* | Return a short-lived signed download URL |
| `delete_document` | Yes | Delete the caller-owned HWPX and metadata |

There are no password, passphrase, API-key, or access-token fields in these MCP tool schemas. Authentication happens at the HTTP/MCP transport layer.

`export_document` does not mutate the HWPX bytes, but it creates a temporary bearer-style download capability.

## OAuth boundary

P1.1 co-hosts a small single-user OAuth 2.1 authorization server using the MCP Python SDK.

The flow is:

```text
401 from /mcp
→ Protected Resource Metadata discovery
→ Authorization Server Metadata discovery
→ Dynamic Client Registration
→ authorization-code + PKCE
→ browser approval page
→ short-lived access token + rotating refresh token
→ bearer-authenticated MCP request
```

The browser approval page requires `P11_OAUTH_PASSPHRASE`, which is a server-side deployment secret. It is never sent as an MCP tool argument.

Prototype token settings:

- access token: 15 minutes;
- refresh token: 30 days with rotation;
- authorization request: 5 minutes;
- required MCP scope: `hwpx`;
- refresh scope: `offline_access`.

### Current OAuth limitation

OAuth client registrations, authorization codes, access tokens, and refresh tokens are stored **in memory** in P1.1. A server restart or Render redeploy invalidates them and therefore requires ChatGPT to reconnect/re-authorize.

This is intentional for P1.1: secret-free native invocation is established before adding durable credential state.

## HWPX materialization

The server uses `python-hwpx >= 6.4` for document creation. Generated files are independently checked as ZIP/XML packages.

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

## Storage and ownership contract

The server never exposes filesystem paths to the model.

Each document receives an opaque ID such as:

```text
doc_<random>
```

Metadata includes the authenticated OAuth subject that owns the document. `inspect_document`, `export_document`, and `delete_document` reject documents not owned by the authenticated principal.

The current backend is a bounded **ephemeral filesystem object store** under `/tmp`; the default retention window is 30 minutes.

The `document_id` contract is deliberately storage-independent so a later phase can replace the filesystem backend with an S3-compatible object store without changing the MCP-facing API.

## Download handoff

`export_document` returns a signed URL of the form:

```text
https://HOST/artifacts/<document_id>?exp=<unix-time>&sig=<hmac>
```

The URL expires quickly, is capped by the document retention deadline, and uses `Cache-Control: private, no-store`.

P1.1 CI downloads the resulting HWPX bytes and verifies their SHA-256 digest against the digest sealed at materialization time.

## Local run

Install dependencies:

```bash
pip install -r requirements.txt
```

Run with local OAuth/download secrets:

```bash
P11_OAUTH_PASSPHRASE='local-oauth-passphrase' \
P1_DOWNLOAD_SECRET='local-download-secret' \
P1_PUBLIC_BASE_URL='http://127.0.0.1:8000' \
python server.py
```

PowerShell:

```powershell
$env:P11_OAUTH_PASSPHRASE="local-oauth-passphrase"
$env:P1_DOWNLOAD_SECRET="local-download-secret"
$env:P1_PUBLIC_BASE_URL="http://127.0.0.1:8000"
python server.py
```

Endpoints:

```text
http://127.0.0.1:8000/health
http://127.0.0.1:8000/mcp
http://127.0.0.1:8000/.well-known/oauth-protected-resource/mcp
http://127.0.0.1:8000/.well-known/oauth-authorization-server
```

Run the full OAuth-native lifecycle smoke test:

```bash
P11_OAUTH_PASSPHRASE='local-oauth-passphrase' \
RUN_P11_WRITE_TEST=1 \
python test_client.py
```

Unit tests:

```bash
python -m unittest -v test_p1.py
```

## Docker

```bash
docker build -t chatgpt-web-hwpx-mcp .
docker run --rm -p 8000:8000 \
  -e P11_OAUTH_PASSPHRASE='replace-me-with-a-strong-value' \
  -e P1_DOWNLOAD_SECRET='replace-me-too' \
  chatgpt-web-hwpx-mcp
```

## Deployment

`render.yaml` is the canonical deployment description. There is deliberately no one-click deploy button.

Required deployment secrets:

- `P11_OAUTH_PASSPHRASE` — manually provisioned secret (`sync: false` in the Render Blueprint);
- `P1_DOWNLOAD_SECRET` — generated by Render.

The existing canonical Render service retains the historical P0-era slug so the registered MCP endpoint does not change unnecessarily:

```text
https://chatgpt-web-hwpx-mcp-p0.onrender.com
```

## CI

Two workflows define the P1.1 court:

- `P1.1 OAuth HWPX lifecycle CI` — unit tests, unauthenticated 401, OAuth discovery, DCR, PKCE authorization, bearer MCP, secret-free tool-schema audit, `create → inspect → export → download → SHA-256 receipt → delete`.
- `P1.1 Render OAuth boundary verification` — public `/health`, OAuth metadata endpoints, and unauthenticated MCP rejection against the deployed service.

Remote CI intentionally does not receive the browser-approval passphrase.

## Security boundary

P1.1 is still a prototype. Do not yet ingest existing personal or confidential HWPX files.

Before sensitive-document ingress, the project still needs:

- durable OAuth registration/token persistence across deploys;
- stronger multi-user/session isolation;
- ingress ZIP-bomb/path-traversal/XML defenses;
- quotas and audit logging;
- persistent object storage if durable custody is needed;
- a Hancom rendering/fidelity oracle for exact visual compatibility.

## Next phases

```text
P1     minimal valid HWPX + document_id + signed export
P1.1   OAuth-native secret-free lifecycle + authenticated ownership
P1.2   durable auth state + authenticated safe ingest
P2     structured edits and formatting
P3     tables / images / equations
P4     renderer-oracle and Hancom fidelity validation
```

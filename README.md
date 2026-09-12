# ChatGPT Web HWPX MCP

Remote Streamable-HTTP MCP for authenticated HWPX document creation, custody, validation, ingress, and signed artifact delivery from ChatGPT Web.

## Current phase

**P0 is closed / PASS.** ChatGPT Web discovered the custom MCP, executed native read/write actions, and created a remote artifact. See [`P0_TEST_LEDGER.md`](./P0_TEST_LEDGER.md).

**P1 is closed at the server/lifecycle layer.** Minimal valid HWPX materialization, opaque `document_id` custody, structural validation, signed export, and deletion are implemented. See [`P1_TEST_LEDGER.md`](./P1_TEST_LEDGER.md).

**P1.1 is closed / PASS.** Native ChatGPT OAuth reauthorization and the secret-free `create → inspect → export → actual HWPX byte receipt` path were completed. See [`P11_TEST_LEDGER.md`](./P11_TEST_LEDGER.md).

**P1.2 is active at implementation/public PASS.** OAuth authority state is now durable across server-process restarts through an encrypted Postgres store, and a bounded existing-HWPX admission gate is implemented. Native ChatGPT post-redeploy token continuity remains the final P1.2 world-contact receipt. See [`P12_TEST_LEDGER.md`](./P12_TEST_LEDGER.md).

```text
ChatGPT Web
→ OAuth 2.1 authorization-code + PKCE/DCR
→ short-lived bearer access token + rotating refresh token
→ encrypted durable OAuth authority store
→ remote MCP /mcp
→ create_document / ingest_document
→ caller-owned opaque document_id
→ bounded ephemeral HWPX custody
→ validation / inspect / signed export
```

## MCP tools

| Tool | Side effect | Purpose |
|---|---:|---|
| `probe_read` | No | Authenticated connectivity probe |
| `probe_capabilities` | No | Current capability/auth boundary |
| `create_document` | Yes | Materialize a small HWPX and return an opaque `document_id` |
| `ingest_document` | Yes | Admit one bounded existing HWPX after package/XML validation |
| `inspect_document` | No | Validate and inspect one caller-owned document |
| `export_document` | No* | Return a short-lived signed download URL |
| `delete_document` | Yes | Delete the caller-owned HWPX and metadata |

There are no password, passphrase, API-key, or access-token fields in MCP tool schemas. Authentication happens at the HTTP/MCP transport layer.

`export_document` does not mutate HWPX bytes, but it creates a temporary bearer-style download capability.

## OAuth boundary

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

The browser approval page requires `P11_OAUTH_PASSPHRASE`, a server-side deployment secret that is never an MCP tool argument.

Prototype token settings:

- access token: 15 minutes;
- refresh token: 30 days with rotation;
- authorization request: 5 minutes;
- required MCP scope: `hwpx`;
- refresh scope: `offline_access`.

### Durable OAuth state

P1.2 persists OAuth clients, pending approvals, authorization codes, access tokens, refresh tokens, and revocation state in Postgres.

- lookup keys are SHA-256 fingerprints;
- state payloads are authenticated-encrypted with AES-GCM before database storage;
- authorization-code and refresh-token consumption are transactional;
- refresh tokens rotate on use;
- revocation persists across fresh server-process instances;
- MCP is pinned to `2.2.0` for the current encrypted serialization format.

Document bytes are intentionally **not** durable yet. OAuth authority durability and document custody durability are separate boundaries.

## Existing-HWPX admission gate

P1.2 opens only a small authenticated ingress path. `ingest_document` currently accepts base64 HWPX content with a 2 MB compressed limit.

The validator rejects or limits:

- path traversal, absolute/backslash/NUL ZIP paths;
- duplicate or encrypted ZIP entries;
- excessive entry count, package size, expanded size, entry size, or suspicious compression ratio;
- CRC failures;
- invalid HWPX mimetype placement/signature;
- missing required HWPX package parts;
- unparseable XML/HPF;
- DTD or ENTITY declarations.

The server does not fetch arbitrary document URLs, so this ingress path does not introduce an SSRF fetch surface.

Only admitted packages receive a caller-owned opaque `document_id`.

## HWPX validation

Generated and ingested HWPX files are independently checked as ZIP/XML packages. The validator requires at least:

```text
mimetype
version.xml
META-INF/container.xml
Contents/content.hpf
Contents/header.xml
Contents/section0.xml
```

`mimetype` must be the first ZIP entry, stored without compression, and equal `application/hwp+zip`.

## Storage and ownership contract

The server never exposes filesystem paths to the model. Each document receives an opaque ID:

```text
doc_<random>
```

Metadata records the authenticated OAuth subject. `inspect_document`, `export_document`, and `delete_document` reject documents not owned by that principal.

Current document custody uses a bounded **ephemeral filesystem object store** under `/tmp`; the default retention window is 30 minutes. The `document_id` contract is storage-independent so a later phase can replace this backend with durable object storage.

## Download handoff

`export_document` returns a short-lived signed URL:

```text
https://HOST/artifacts/<document_id>?exp=<unix-time>&sig=<hmac>
```

The link is capped by the document retention deadline and uses `Cache-Control: private, no-store`.

## Local run

Install dependencies:

```bash
pip install -r requirements.txt
```

P1.2 requires a Postgres database and server-side secrets:

```bash
P11_OAUTH_PASSPHRASE='local-oauth-passphrase' \
P1_DOWNLOAD_SECRET='local-download-secret' \
P12_AUTH_DATABASE_URL='postgresql://...' \
P12_STATE_SECRET='replace-with-at-least-32-random-characters' \
P1_PUBLIC_BASE_URL='http://127.0.0.1:8000' \
python server.py
```

Endpoints:

```text
http://127.0.0.1:8000/health
http://127.0.0.1:8000/mcp
http://127.0.0.1:8000/.well-known/oauth-protected-resource/mcp
http://127.0.0.1:8000/.well-known/oauth-authorization-server
```

## Deployment

`render.yaml` is the canonical deployment description. There is deliberately no one-click deploy button.

Required deployment secrets:

- `P11_OAUTH_PASSPHRASE` — resource-owner browser approval secret;
- `P12_AUTH_DATABASE_URL` — durable OAuth-state Postgres connection;
- `P12_STATE_SECRET` — encryption secret for durable OAuth payloads;
- `P1_DOWNLOAD_SECRET` — signed artifact-link secret.

The canonical Render service retains its historical P0-era hostname so the registered MCP endpoint does not change unnecessarily:

```text
https://chatgpt-web-hwpx-mcp-p0.onrender.com
```

## CI

Two workflows define the P1.2 implementation/public court:

- `P1.2 Durable OAuth + HWPX ingress CI` — durable encrypted state reload/revocation tests, package-admission rejection tests, OAuth discovery/DCR/PKCE, secret-free schema audit, generated HWPX export/hash receipt, known-good existing-HWPX re-ingress, inspect, and delete.
- `P1.2 Render durable OAuth boundary verification` — public durable-store health, OAuth metadata, `offline_access`, and unauthenticated MCP rejection.

Remote CI intentionally does not receive the browser-approval passphrase.

## Security boundary

P1.2 admits only small bounded HWPX packages. Sensitive production custody still requires additional work, including durable document object storage, stronger multi-user isolation, quotas/audit logging, richer ingress transport, and a native Hancom rendering/fidelity oracle.

## Next phases

```text
P1     minimal valid HWPX + document_id + signed export
P1.1   OAuth-native secret-free lifecycle + authenticated ownership
P1.2   durable auth state + bounded existing-HWPX ingress
P2     structured edits and formatting
P3     tables / images / equations
P4     renderer-oracle and Hancom fidelity validation
```

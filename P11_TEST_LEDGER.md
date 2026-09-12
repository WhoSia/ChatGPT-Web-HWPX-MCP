# P1.1 Test Ledger

Formal stage:

**ChatGPT Web HWPX MCP P1.1 — Authenticated Native Document Lifecycle, Secret-Free Tool Invocation, Signed Artifact Download Receipt & Custody-Boundary Closure**

## Canonical implementation

Server version: `0.2.1-p1.1`

P1.1 moves authentication from MCP tool arguments to the MCP HTTP transport. The document tools no longer accept an access token, passphrase, API key, or password field.

```text
unauthenticated /mcp
→ HTTP 401
→ Protected Resource Metadata
→ Authorization Server Metadata
→ Dynamic Client Registration
→ authorization-code + PKCE
→ resource-owner browser approval
→ short-lived bearer access token
→ authenticated MCP tool invocation
```

The OAuth provider is single-user in P1.1 and uses the authenticated subject `hwpx-owner` as the document owner identity.

## Local confirmatory receipt

Latest canonical GitHub Actions run after the Render packaging patch:

- workflow: `P1.1 OAuth HWPX lifecycle CI`
- run: `34710225885`
- commit under test: `3719e27a5970501ab0d607e355b40363642af4f8`
- conclusion: **SUCCESS**
- MCP protocol negotiated: `2026-07-28`

The confirmatory lifecycle completed all of the following:

| Boundary | Verdict |
|---|---|
| HWPX unit tests | PASS |
| unauthenticated `/mcp` rejection | PASS — HTTP 401 |
| Protected Resource Metadata discovery | PASS |
| Authorization Server Metadata discovery | PASS |
| Dynamic Client Registration | PASS |
| authorization-code + PKCE | PASS |
| browser-style resource-owner approval | PASS |
| token exchange | PASS |
| bearer-authenticated MCP handshake | PASS |
| six-tool discovery | PASS |
| secret-bearing tool-schema audit | PASS |
| authenticated `probe_read` | PASS |
| authenticated `create_document` | PASS |
| caller-owned `inspect_document` | PASS |
| signed `export_document` | PASS |
| artifact HTTP download | PASS |
| downloaded HWPX ZIP signature | PASS |
| downloaded SHA-256 = materialization SHA-256 | PASS |
| authenticated `delete_document` | PASS |

Observed OAuth transport path in the server receipt:

```text
POST /mcp → 401
GET /.well-known/oauth-protected-resource/mcp → 200
GET /.well-known/oauth-authorization-server → 200
POST /register → 201
GET /authorize?...code_challenge_method=S256... → 302
POST /oauth/approve?... → 303
POST /token → 200
POST /mcp with bearer credential → 200
```

No MCP tool schema contained `access_token` or `passphrase`.

## Document custody contract

P1.1 materialized documents store an authenticated owner subject in metadata. `inspect_document`, `export_document`, and `delete_document` compare that owner with the bearer-authenticated caller before operating on the object.

The object store remains bounded and ephemeral. Signed artifact URLs remain short-lived and use a server-only `P1_DOWNLOAD_SECRET`.

## Render/public deployment receipt

The canonical public service remains at the historical P0-era hostname so the registered MCP URL does not change:

`https://chatgpt-web-hwpx-mcp-p0.onrender.com`

The first P1.1 Render attempt exposed a Docker packaging defect: `server.py` imported `oauth_provider`, but the image copied only `server.py`. The defect was localized from the Render traceback and patched directly on `main` by commit:

- `3719e27a5970501ab0d607e355b40363642af4f8` — `P1.1: include OAuth provider in Render image`

The corrected image explicitly copies both `server.py` and `oauth_provider.py`.

Canonical Render receipt:

- deploy: `dep-daip9r15efls73eebujg`
- commit: `3719e27a5970501ab0d607e355b40363642af4f8`
- final status: **live**
- finished: `2026-09-12T18:08:23.641313Z`

Canonical public-boundary GitHub Actions receipt:

- workflow: `P1.1 Render OAuth boundary verification`
- run: `34710225877`
- conclusion: **SUCCESS**

That remote run independently confirmed:

| Public boundary | Verdict |
|---|---|
| Render P1.1 health endpoint | PASS |
| Protected Resource Metadata | PASS |
| Authorization Server Metadata | PASS |
| unauthenticated MCP blocked before tool execution | PASS — HTTP 401 |

Deployment secrets are server-side only. `P11_OAUTH_PASSPHRASE` and `P1_DOWNLOAD_SECRET` are configured in Render and are not placed in MCP tool schemas, repository files, or this ledger.

## Current verdict

```text
OAUTH_RESOURCE_DISCOVERY_LOCAL = PASS
OAUTH_AUTHORIZATION_SERVER_DISCOVERY_LOCAL = PASS
UNAUTHENTICATED_MCP_REJECTION_LOCAL = PASS
DCR = PASS
PKCE_AUTHORIZATION_CODE = PASS
TRANSPORT_BEARER_AUTH = PASS
SECRET_FREE_TOOL_SCHEMA = PASS
AUTHENTICATED_CREATE = PASS
OWNER_BOUND_INSPECT = PASS
SIGNED_EXPORT = PASS
ARTIFACT_DOWNLOAD_HASH_RECEIPT = PASS
AUTHENTICATED_DELETE = PASS

RENDER_P11_DEPLOYMENT = PASS
PUBLIC_OAUTH_RESOURCE_DISCOVERY = PASS
PUBLIC_OAUTH_AUTHORIZATION_SERVER_DISCOVERY = PASS
PUBLIC_UNAUTHENTICATED_MCP_REJECTION = PASS
CHATGPT_NATIVE_OAUTH_REAUTH = PENDING_NATIVE_RECEIPT
CHATGPT_NATIVE_DOCUMENT_LIFECYCLE = PENDING_NATIVE_RECEIPT

AUTH_DURABILITY_ACROSS_DEPLOY = HOLD_IN_MEMORY
EXISTING_DOCUMENT_INGEST = HOLD
```

## Deliberate hold

OAuth registrations and tokens are held in memory in P1.1. Render restart/redeploy invalidates them. Durable OAuth state is therefore not yet licensed, and arbitrary existing-document ingestion remains blocked.

The remaining P1.1 world-contact step is native ChatGPT OAuth reauthorization followed by a secret-free native document lifecycle receipt. After that receipt, the next architectural step should make authentication durable across restarts and only then open a tightly validated existing-HWPX ingress path.

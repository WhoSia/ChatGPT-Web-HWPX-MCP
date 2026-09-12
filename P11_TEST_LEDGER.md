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

## P1.1-R1 native ChatGPT receipt

Formal closure step:

**ChatGPT Web HWPX MCP P1.1-R1 — Native ChatGPT OAuth Reauthorization, Secret-Free HWPX Create–Inspect–Export Receipt & Custody-Boundary Closure**

Native ChatGPT custom-app reauthorization succeeded against the public Render OAuth deployment. The native tool surface then executed the document lifecycle without any `access_token`, passphrase, nonce, API key, or equivalent secret in MCP tool arguments.

Native document created:

- filename: `p1-1-native.hwpx`
- title: `P1.1 Native OAuth`
- body: `ChatGPT Web HWPX MCP OAuth-native document lifecycle`
- native inspect: `valid: true`
- native inspect size: `7,578 bytes`
- native SHA-256: `302c909a37cc99c3bae2ff6c4ecb5b708bf94b00452243b0376620807bb39b8f`
- native export: PASS — short-lived signed artifact URL issued

The downloaded artifact was then independently inspected outside the MCP server:

| Byte-level receipt | Verdict |
|---|---|
| File size | PASS — 7,578 bytes |
| SHA-256 | PASS — `302c909a37cc99c3bae2ff6c4ecb5b708bf94b00452243b0376620807bb39b8f` |
| ZIP container | PASS |
| HWPX mimetype | PASS — `application/hwp+zip` |
| `Contents/section0.xml` title text | PASS |
| `Contents/section0.xml` body text | PASS |
| native inspect SHA = downloaded artifact SHA | PASS |

This closes the native OAuth transport-to-byte chain:

```text
ChatGPT native custom app
→ OAuth authorization-code + PKCE
→ bearer-authenticated MCP
→ secret-free create_document
→ owner-bound inspect_document
→ signed export_document
→ public short-lived artifact receipt
→ downloaded HWPX byte verification
```

## Final P1.1 verdict

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
CHATGPT_NATIVE_OAUTH_REAUTH = PASS
CHATGPT_NATIVE_SECRET_FREE_CREATE = PASS
CHATGPT_NATIVE_OWNER_BOUND_INSPECT = PASS
CHATGPT_NATIVE_SIGNED_EXPORT = PASS
CHATGPT_NATIVE_DOWNLOADED_BYTE_MATCH = PASS
CHATGPT_NATIVE_DOCUMENT_LIFECYCLE = PASS

P1_1 = PASS / CLOSED

AUTH_DURABILITY_ACROSS_DEPLOY = HOLD_IN_MEMORY
EXISTING_DOCUMENT_INGEST = HOLD
```

## Deliberate hold and next architectural frontier

OAuth registrations and tokens are held in memory in P1.1. Render restart/redeploy invalidates them. P1.1 therefore proves correct native OAuth custody semantics but does not yet establish durable authorization state across deployment churn.

Arbitrary existing-document ingestion also remains blocked. The next architectural step should first make OAuth/client/token state durable across restarts, preserve revocation and expiration semantics, and only then admit a tightly validated existing-HWPX ingress path with ZIP/XML/OPC quarantine and opaque `document_id` custody.

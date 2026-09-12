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

Canonical GitHub Actions run:

- workflow: `P1.1 OAuth HWPX lifecycle CI`
- run: `34703290086`
- commit under test: `edfa275e3d9a9ec0a0b4db3a217e4cba26f14c3a`
- conclusion: **SUCCESS**
- MCP protocol negotiated: `2026-07-28`

The same confirmatory run completed all of the following:

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

## Render/public deployment boundary

Repository configuration has been migrated to P1.1:

- `P11_OAUTH_PASSPHRASE` is a manually provisioned deployment secret (`sync: false` in `render.yaml`);
- `P1_DOWNLOAD_SECRET` remains server-generated;
- the obsolete `P1_ACCESS_TOKEN` tool-level guard is removed from the deployment manifest;
- remote verification checks OAuth metadata and unauthenticated 401 without receiving the approval passphrase.

At the time this ledger was first sealed, the existing Render service had **not yet been redeployed to the P1.1 commit**, and the Render connector required an explicit workspace selection before either provisioning `P11_OAUTH_PASSPHRASE` or triggering the deployment. Therefore public/native closure is deliberately not promoted from the local confirmatory result alone.

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

AUTH_DURABILITY_ACROSS_DEPLOY = HOLD_IN_MEMORY
RENDER_P11_DEPLOYMENT = PENDING_WORKSPACE_CONFIRMATION
CHATGPT_NATIVE_OAUTH_REAUTH = PENDING_RENDER_P11_DEPLOYMENT
EXISTING_DOCUMENT_INGEST = HOLD
```

## Deliberate hold

OAuth registrations and tokens are held in memory in P1.1. Render restart/redeploy invalidates them. Durable OAuth state is therefore not yet licensed, and arbitrary existing-document ingestion remains blocked.

The next architectural step should make authentication durable across restarts and only then open a tightly validated existing-HWPX ingress path.

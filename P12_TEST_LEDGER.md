# P1.2 Test Ledger

Formal stage:

**ChatGPT Web HWPX MCP P1.2 — Durable OAuth State, Restart-Safe Client/Token Authority, Revocation Semantics & Existing-HWPX Ingress Admission Gate**

## Canonical implementation

Server version: `0.2.2-p1.2`

P1.2 separates durable authorization authority from short-lived document custody:

```text
ChatGPT OAuth client
→ DCR / authorization code + PKCE
→ short-lived access token + rotating refresh token
→ encrypted durable OAuth state in Postgres
→ authenticated MCP
→ ephemeral HWPX document custody
```

The document object bytes remain intentionally ephemeral in P1.2. OAuth client registrations, pending approvals, authorization codes, access tokens, refresh tokens, and revocation state use the durable authority store.

## Durable OAuth state contract

OAuth state is stored in Postgres through `DurableOAuthStore`.

- lookup keys are SHA-256 fingerprints rather than bearer/code plaintext;
- serialized provider objects are authenticated-encrypted with AES-GCM before database storage;
- authorization-code consumption and successor token issuance are transactional;
- refresh-token consumption and rotation are transactional;
- a consumed refresh token cannot be reused;
- token-family revocation is persisted by client ID and authenticated subject;
- expired non-client state is eligible for cleanup;
- the MCP SDK is pinned to `mcp==2.2.0` for the current encrypted serialization format.

The database URL, encryption secret, OAuth approval passphrase, and download signing secret are deployment secrets and are not recorded in this ledger or repository.

## Existing-HWPX admission gate

P1.2 opens only a bounded existing-HWPX ingress path. It is not a general arbitrary-file upload service.

Current admission constraints:

| Boundary | P1.2 rule |
|---|---|
| Encoded transport | authenticated MCP `ingest_document` with base64 content |
| Compressed ingress size | ≤ 2,000,000 bytes |
| Package size | ≤ 8,000,000 bytes |
| ZIP entries | ≤ 512 |
| Expanded package size | ≤ 32,000,000 bytes |
| Per-entry size | ≤ 8,000,000 bytes |
| Large-entry compression ratio | ≤ 100:1 |
| ZIP path traversal / absolute paths / backslashes / NUL | rejected |
| Duplicate ZIP entry names | rejected |
| Encrypted ZIP entries | rejected |
| CRC failure | rejected |
| HWPX mimetype position/signature | enforced |
| Required HWPX package parts | enforced |
| XML / HPF parseability | enforced |
| DTD or ENTITY declaration | rejected |
| Arbitrary remote URL fetch | not supported |

Only a package that passes the gate is promoted into an opaque `document_id` owned by the authenticated subject.

## Confirmatory CI receipt

Canonical implementation run:

- workflow: `P1.2 Durable OAuth + HWPX ingress CI`
- run: `34711423708`
- commit under test: `93afbd13ed2c905e4f572a9cfc2caaa98a3db54a`
- conclusion: **SUCCESS**

The same latest-main confirmatory run completed:

| Boundary | Verdict |
|---|---|
| Python compilation | PASS |
| known-good generated HWPX validation | PASS |
| known-good existing-HWPX admission | PASS |
| ZIP path-traversal rejection | PASS |
| DTD/entity rejection | PASS |
| durable encrypted refresh state survives fresh store instance | PASS |
| usable refresh token absent from database ciphertext | PASS |
| durable token-family revocation survives fresh store instance | PASS |
| P1.2 durable health check | PASS |
| unauthenticated `/mcp` rejection | PASS — HTTP 401 |
| OAuth protected-resource discovery | PASS |
| authorization-server discovery + `offline_access` | PASS |
| DCR + authorization-code/PKCE lifecycle | PASS |
| secret-free tool-schema audit | PASS |
| authenticated generated-HWPX creation | PASS |
| signed artifact export + byte/hash receipt | PASS |
| exported known-good HWPX re-ingress | PASS |
| ingested SHA-256 preserved | PASS |
| owner-bound inspect | PASS |
| authenticated cleanup/delete | PASS |

An initial confirmatory run localized one PostgreSQL parameter-typing defect in the revocation query. The query was corrected by splitting subject-bound and subject-agnostic revocation into explicit SQL branches. The latest canonical run above is green after that correction.

## Render/public deployment receipt

Canonical deployment before the native continuity replay:

- service: `chatgpt-web-hwpx-mcp-p0`
- public base: `https://chatgpt-web-hwpx-mcp-p0.onrender.com`
- deploy: `dep-daipkvh594qs739n4ung`
- commit: `93afbd13ed2c905e4f572a9cfc2caaa98a3db54a`
- status: **live**
- finished: `2026-09-12T18:32:07.87117Z`

Canonical public-boundary run:

- workflow: `P1.2 Render durable OAuth boundary verification`
- run: `34711423707`
- conclusion: **SUCCESS**

The public run confirmed:

| Public boundary | Verdict |
|---|---|
| Render P1.2 health endpoint | PASS |
| durable state mode = `postgres-encrypted` | PASS |
| durable store reachable | PASS |
| protected-resource metadata | PASS |
| authorization-server metadata | PASS |
| `offline_access` advertised | PASS |
| unauthenticated MCP blocked before tool execution | PASS — HTTP 401 |

## Native transition and pre-restart receipts

The first native attempt after switching from P1.1 in-memory OAuth state to the P1.2 durable provider produced an expected transition discontinuity:

```text
LEGACY_P11_CLIENT_ID_PRESENT_IN_CHATGPT = YES
LEGACY_P11_CLIENT_ID_PRESENT_IN_P12_DATABASE = NO
AUTHORIZATION_RESULT = invalid_request / Client ID not found
FRESH_DCR_REQUIRED = YES
```

This does not test restart continuity because the legacy P1.1 client registration had never been persisted. The custom app was therefore re-created against the same MCP URL, causing a fresh P1.2 DCR registration and authorization.

Native pre-restart authenticated receipt after fresh P1.2 registration:

```text
NATIVE_PRE_RESTART_PROBE = PASS
PROJECT = ChatGPT Web HWPX MCP
VERSION = 0.2.2-p1.2
PROBE = read
MESSAGE = P1.2 pre-restart continuity receipt
AUTHENTICATED_SUBJECT = hwpx-owner
SERVER_RECEIPT_UTC = 2026-09-12T18:47:58.482110+00:00
SERVER_RECEIPT_KST = 2026-09-13 03:47:58
```

This ledger commit intentionally serves as the continuity-test redeploy trigger. OAuth database state and the state-encryption secret are not changed by this commit. A successful post-redeploy call from the same ChatGPT custom app without a new browser authorization closes the remaining P1.2 native continuity requirement.

## Current verdict

```text
DURABLE_OAUTH_STORE_IMPLEMENTATION = PASS
ENCRYPTED_OAUTH_STATE_AT_REST = PASS
RESTART_STYLE_STATE_RELOAD_CI = PASS
AUTHORIZATION_CODE_ONE_TIME_CONSUMPTION = PASS
REFRESH_ROTATION_SEMANTICS = PASS
DURABLE_TOKEN_FAMILY_REVOCATION = PASS
OFFLINE_ACCESS_DISCOVERY = PASS
BOUNDED_EXISTING_HWPX_INGRESS = PASS
MALICIOUS_PACKAGE_ADMISSION_REJECTION = PASS
OWNER_BOUND_INGRESS_CUSTODY = PASS
RENDER_P12_DEPLOYMENT = PASS
PUBLIC_DURABLE_STORE_HEALTH = PASS
PUBLIC_OAUTH_BOUNDARY = PASS
LEGACY_EPHEMERAL_CLIENT_MIGRATION = FAIL_EXPECTED / FRESH_DCR_REQUIRED
CHATGPT_NATIVE_PRE_RESTART_AUTHENTICATED_RECEIPT = PASS

CHATGPT_NATIVE_POST_RESTART_TOKEN_CONTINUITY = PENDING_NATIVE_RECEIPT
DURABLE_DOCUMENT_OBJECT_STORAGE = HOLD
LARGE_FILE_STREAMING_INGRESS = HOLD
RICH_HWPX_MUTATION = HOLD
HANCOM_RENDERER_FIDELITY_ORACLE = HOLD
```

## Promotion rule

P1.2 is **IMPLEMENTATION PASS / PUBLIC PASS / NATIVE PRE-RESTART PASS**, but not yet globally closed. The remaining world-contact receipt is deliberately narrow:

1. fresh-register/authorize the ChatGPT custom MCP under the P1.2 durable provider — **PASS**;
2. execute one authenticated tool call — **PASS**;
3. restart/redeploy the Render service without changing OAuth database state or the state-encryption secret — **TRIGGERED BY THIS LEDGER COMMIT**;
4. execute another authenticated tool call from the same ChatGPT app without repeating resource-owner authorization — **PENDING**.

If step 4 succeeds, native restart-safe client/token authority is certified and P1.2 may close.

## Deliberate holds

P1.2 does not make document bytes durable across Render restarts. It also does not admit arbitrary large files, fetch remote document URLs, expose filesystem paths, or claim fidelity against the native Hancom renderer.

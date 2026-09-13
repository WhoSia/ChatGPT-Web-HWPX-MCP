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

## Render/public deployment receipts

Canonical P1.2 deployment before the native continuity replay:

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

The native continuity redeploy was triggered by commit:

- `b8439f58b42aa227d82c037cb82849a03cd6b810`
- message: `P1.2-R1: seal pre-restart native receipt and trigger continuity redeploy`

Post-redeploy public-boundary verification:

- workflow: `P1.2 Render durable OAuth boundary verification`
- run: `34712332770`
- conclusion: **SUCCESS**

The post-redeploy public run confirmed durable health, protected-resource metadata, authorization-server metadata with `offline_access`, and unauthenticated `/mcp` rejection with HTTP 401.

## Native transition and continuity receipts

The first native attempt after switching from P1.1 in-memory OAuth state to the P1.2 durable provider produced an expected transition discontinuity:

```text
LEGACY_P11_CLIENT_ID_PRESENT_IN_CHATGPT = YES
LEGACY_P11_CLIENT_ID_PRESENT_IN_P12_DATABASE = NO
AUTHORIZATION_RESULT = invalid_request / Client ID not found
FRESH_DCR_REQUIRED = YES
```

This was not a restart-continuity failure: the legacy P1.1 client registration had never been persisted. The custom app was therefore re-created against the same MCP URL, causing a fresh P1.2 DCR registration and authorization.

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

After the forced Render redeploy, the same ChatGPT custom app executed the post-restart probe without another browser/resource-owner authorization.

Native post-restart authenticated receipt:

```text
NATIVE_POST_RESTART_PROBE = PASS
PROJECT = ChatGPT Web HWPX MCP
VERSION = 0.2.2-p1.2
PROBE = read
MESSAGE = P1.2 post-restart continuity receipt
AUTHENTICATED_SUBJECT = hwpx-owner
SERVER_RECEIPT_UTC = 2026-09-13T10:49:39.284028+00:00
SERVER_RECEIPT_KST = 2026-09-13 19:49:39
RESOURCE_OWNER_REAUTHORIZATION_REQUIRED = NO
```

This closes the native restart-safe authority claim:

```text
fresh durable DCR
→ authenticated pre-restart tool call
→ Render process replacement / redeploy
→ durable OAuth state retained outside process memory
→ same ChatGPT custom app
→ no new browser approval
→ authenticated post-restart tool call succeeds
```

## Final verdict

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
CHATGPT_NATIVE_POST_RESTART_TOKEN_CONTINUITY = PASS
RESOURCE_OWNER_REAUTHORIZATION_AFTER_RESTART = NOT_REQUIRED

P1.2 = CLOSED / PASS

DURABLE_DOCUMENT_OBJECT_STORAGE = HOLD
LARGE_FILE_STREAMING_INGRESS = HOLD
RICH_HWPX_MUTATION = HOLD
HANCOM_RENDERER_FIDELITY_ORACLE = HOLD
```

## Closure statement

P1.2 establishes that OAuth client/token authority is no longer process-memory-bound: a freshly registered ChatGPT client survives a real Render redeploy and resumes authenticated MCP access without repeating browser authorization. Existing HWPX ingress is admitted only through the bounded hostile-package gate described above.

P1.2 deliberately does **not** claim durable document-byte custody across restarts. Document-object durability remains a separate future phase so authentication authority and file-retention semantics are not conflated.
